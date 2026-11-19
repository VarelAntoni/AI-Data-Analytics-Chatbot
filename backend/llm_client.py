"""
LLM Client Terpusat: llm_client.py
Deskripsi:
  Satu-satunya gerbang panggilan Google Gemini untuk seluruh sistem
  (planner, judge, sintesis, vision PDF). Menangani:
  - Retry + rotasi model cadangan saat 503 (high demand).
  - Klasifikasi error: kuota habis (429), konteks kepanjangan (400 token),
    API key invalid, dan error umum -> exception bertipe agar pemanggil
    bisa memberi pesan ramah, BUKAN error mentah.
  - Deteksi respons terpotong (finish_reason MAX_TOKENS).
"""

import os
import re
import time
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Daftar model cepat dan stabil untuk failover otomatis jika ada lonjakan traffic (503)
CANDIDATE_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
]

client: Optional[genai.Client] = None

# Status kesehatan key terakhir (untuk /api/health)
last_llm_status = {"state": "unknown", "detail": ""}


class LLMError(Exception):
    """Error LLM umum yang sudah diklasifikasi."""


class QuotaExhaustedError(LLMError):
    """Kuota / rate limit API habis (429 RESOURCE_EXHAUSTED)."""


class ContextTooLongError(LLMError):
    """Prompt melebihi context window model (400 token limit)."""


class InvalidKeyError(LLMError):
    """API key tidak valid / belum diatur."""


def get_client() -> Optional[genai.Client]:
    """Inisialisasi client secara lazy dari .env (mendukung key diisi setelah start)."""
    global client
    if client is None:
        load_dotenv(override=True)
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if key and key != "your_gemini_api_key_here":
            client = genai.Client(api_key=key)
    return client


def classify_llm_error(e: Exception) -> LLMError:
    """Ubah exception mentah SDK menjadi exception bertipe yang ramah ditangani."""
    s = str(e)
    low = s.lower()
    if "429" in s or "resource_exhausted" in low or "quota" in low or "rate limit" in low:
        return QuotaExhaustedError(s)
    if ("400" in s and ("token" in low or "context" in low or "too large" in low or "exceeds" in low)):
        return ContextTooLongError(s)
    if "api_key_invalid" in low or "api key not valid" in low or ("401" in s) or ("403" in s and "permission" in low):
        return InvalidKeyError(s)
    return LLMError(s)


def _parse_retry_delay(err_str: str) -> float:
    """Ambil saran retryDelay dari pesan error 429 jika ada (mis. 'retryDelay': '32s')."""
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", err_str)
    if m:
        return min(float(m.group(1)), 15.0)  # batasi agar UX tidak terlalu lama
    return 5.0


def is_truncated(resp) -> bool:
    """Deteksi respons terpotong karena batas token output."""
    try:
        for cand in getattr(resp, "candidates", []) or []:
            fr = getattr(cand, "finish_reason", None)
            if fr is not None and "MAX_TOKENS" in str(fr):
                return True
    except Exception:
        pass
    return False


def generate_with_fallback(contents, config=None, retries: int = 2):
    """
    Panggil Gemini dengan retry & rotasi model, SADAR JENIS ERROR:
    - 503 (sibuk)      : tidur 1.5s, retry, lalu rotasi model.
    - 429 (kuota)      : hormati retryDelay, rotasi terbatas; jika semua model
                         kena kuota -> QuotaExhaustedError (berhenti cepat).
    - 400 token limit  : langsung ContextTooLongError (rotasi percuma).
    - key invalid      : langsung InvalidKeyError.
    Semua exception yang keluar adalah subclass LLMError (bukan error mentah).
    """
    global last_llm_status
    c = get_client()
    if c is None:
        raise InvalidKeyError("Kunci API Gemini belum diatur di file .env")

    last_err: Optional[Exception] = None
    quota_hits = 0

    for m in CANDIDATE_MODELS:
        for attempt in range(retries):
            try:
                resp = c.models.generate_content(model=m, contents=contents, config=config)
                last_llm_status = {"state": "ok", "detail": f"model={m}"}
                return resp
            except Exception as e:
                typed = classify_llm_error(e)
                last_err = typed
                err_str = str(e)

                if isinstance(typed, ContextTooLongError):
                    last_llm_status = {"state": "context_too_long", "detail": err_str[:200]}
                    raise typed from e
                if isinstance(typed, InvalidKeyError):
                    last_llm_status = {"state": "invalid_key", "detail": err_str[:200]}
                    raise typed from e
                if isinstance(typed, QuotaExhaustedError):
                    quota_hits += 1
                    last_llm_status = {"state": "quota_exhausted", "detail": err_str[:200]}
                    # Kuota umumnya per-key: jika 2 model berturut-turut kena, berhenti cepat.
                    if quota_hits >= 2:
                        raise typed from e
                    time.sleep(_parse_retry_delay(err_str))
                    break  # pindah model, jangan habiskan retry di model yang sama
                if "503" in err_str or "unavailable" in err_str.lower():
                    time.sleep(1.5)
                    continue
                # Error lain: coba model berikutnya
                break

    last_llm_status = {"state": "error", "detail": str(last_err)[:200]}
    raise last_err if last_err else LLMError("Semua model gagal tanpa detail error.")


def friendly_error_message(e: LLMError) -> str:
    """Pesan markdown ramah untuk ditampilkan ke user saat LLM gagal."""
    if isinstance(e, QuotaExhaustedError):
        return (
            "⚠️ **Kuota API AI sedang habis.**\n\n"
            "Semua model Gemini menolak permintaan karena batas kuota/rate limit tercapai. "
            "Silakan coba lagi beberapa menit lagi, atau periksa/ganti `GEMINI_API_KEY` di file `.env`.\n\n"
            "Data yang sempat berhasil diambil tetap ditampilkan di bawah ini."
        )
    if isinstance(e, ContextTooLongError):
        return (
            "⚠️ **Konteks analisis terlalu besar untuk diproses AI.**\n\n"
            "Coba persempit pertanyaan (misalnya satu bulan atau satu kanal saja). "
            "Data mentah yang berhasil diambil tetap ditampilkan di bawah ini."
        )
    if isinstance(e, InvalidKeyError):
        return (
            "⚠️ **Kunci API Gemini belum valid.**\n\n"
            "Buka file `.env` di folder proyek dan isi `GEMINI_API_KEY` dengan kunci dari "
            "https://aistudio.google.com/, lalu restart server."
        )
    return (
        "⚠️ **Server AI sedang sibuk atau mengalami gangguan.**\n\n"
        "Silakan coba lagi sebentar lagi. Data yang sempat berhasil diambil tetap ditampilkan di bawah ini."
    )


MAX_CONTEXT_CHARS = 30000


def trim_context(text: str, budget: int = MAX_CONTEXT_CHARS) -> str:
    """Potong konteks agar tidak melebihi budget karakter (pencegahan token limit)."""
    if len(text) <= budget:
        return text
    return text[:budget] + "\n\n[... konteks dipotong otomatis karena terlalu panjang ...]"