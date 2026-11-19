"""
Core Agent: agent.py
Deskripsi:
  Orkestrator AI Chatbot multi-sumber dengan loop retry berbudget:
  Tahap 1 (Planning):
    - LLM menganalisis pertanyaan + RIWAYAT CHAT + skema SEMUA sumber data
      (PostgreSQL, CSV/XLSX/JSON dari URL, Google Sheets per tab) + indeks dokumen.
    - Menghasilkan rencana: {intent, steps: [{source, sql_query}], doc_query}.
  Tahap 2 (Execution Loop, maks 3 ronde):
    - Eksekusi SQL per sumber (guardrail SELECT-only + allowlist).
    - Percobaan gagal = error ATAU 0 baris; budget 3 percobaan per sumber
      di-enforce kode Python (bukan dipercaya dari LLM).
    - Judge LLM ringan menilai apakah hasil sudah cukup menjawab;
      jika belum, LLM menyusun query perbaikan / pindah sumber.
    - Budget habis tanpa data -> jawaban deterministik "tidak ditemukan".
  Tahap 3 (Synthesis & Visualization):
    - LLM merangkum hasil semua sumber + dokumen menjadi jawaban profesional.
    - Fallback deterministik (tabel markdown) jika LLM gagal (kuota, dll).
  Penanganan error LLM terpusat di llm_client (kuota habis -> pesan ramah).
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from google.genai import types

# LLM client terpusat (retry, rotasi model, klasifikasi error kuota/konteks)
from backend.llm_client import (
    get_client,
    generate_with_fallback,
    friendly_error_message,
    trim_context,
    is_truncated,
    LLMError,
    QuotaExhaustedError,
    ContextTooLongError,
)

# Import tools dari MCP Servers
from mcp_servers.analytics_server import (
    get_database_schema,
    execute_analytics_query,
    execute_source_query,
    get_all_sources_schema_text,
)
from mcp_servers.knowledge_server import search_knowledge_base

# Memori percakapan (checkpoint postgres manual)
from backend import chat_store

load_dotenv()

MAX_ROUNDS = 3                # jumlah ronde eksekusi maksimal per pertanyaan
MAX_ATTEMPTS_PER_SOURCE = 3   # budget percobaan SQL per sumber
MAX_STEPS_PER_ROUND = 3


# Kompatibilitas: main.py /api/test-agent mengimpor `client` dari modul ini.
def __getattr__(name):
    if name == "client":
        return get_client()
    raise AttributeError(name)


# ============================================================
# Prompt Planning & Judge
# ============================================================

def get_plan_prompt(user_query: str, history_text: str = "",
                    feedback: str = "") -> str:
    """Prompt Tahap 1: rencana multi-sumber (SQL per sumber + pencarian dokumen)."""
    schemas = get_all_sources_schema_text()
    history_block = ""
    if history_text:
        history_block = f"""
RIWAYAT PERCAKAPAN SEBELUMNYA (untuk memahami kata rujukan seperti "tersebut", "itu", "tadi"):
{history_text}

PENTING: Jika pertanyaan user mengandung kata rujukan, resolve rujukannya dari riwayat
dan tulis query yang SELF-CONTAINED (lengkap tanpa bergantung konteks luar).
"""
    feedback_block = ""
    if feedback:
        feedback_block = f"""
PERCOBAAN SEBELUMNYA GAGAL / BELUM CUKUP. Umpan balik:
{feedback}
Susun query PERBAIKAN (perbaiki filter/nilai kolom/agregasi) atau PINDAH ke sumber lain
yang skemanya lebih cocok. Jangan ulangi query yang sama persis.
"""
    return f"""Kamu adalah Query Planner untuk AI Analytics Chatbot multi-sumber.
Tugasmu: menganalisis pertanyaan pengguna dan memilih SUMBER DATA yang paling cocok,
lalu menyusun rencana eksekusi.

SUMBER DATA YANG TERSEDIA (skema hasil inspeksi otomatis):
{schemas}

DOKUMEN YANG TERSEDIA (untuk SOP/kebijakan/insiden, dicari via RAG):
- SOP_Penanganan_Transaksi_Gagal.pdf (Alur eskalasi L1/L2, penanganan status PENDING > 15 mnt, tabel kode error)
- Kebijakan_Refund_dan_Chargeback.docx (Batas waktu refund: VA 1x24 jam, E-Wallet real-time, Kartu Kredit 7-14 hari)
- Laporan_Insiden_BCA_VA_Oktober_2024.txt (Insiden SEV-1 pada 15-20 Okt 2024: migrasi switch gateway BCA v4.0 timeout)
{history_block}{feedback_block}
PERTANYAAN PENGGUNA: "{user_query}"

KEMBALIKAN HANYA JSON DENGAN FORMAT BERIKUT (TANPA TEKS LAIN):
{{
  "intent": "SQL_ANALYTICS" | "DOCUMENT_RAG" | "HYBRID_INVESTIGATION" | "GENERAL",
  "steps": [
    {{"source": "nama_sumber", "sql_query": "SELECT ..."}}
  ],
  "doc_query": "kata kunci pencarian dokumen (atau null jika tidak butuh dokumen)"
}}

ATURAN:
- "source" HARUS salah satu nama sumber yang terdaftar di atas (mis. "postgres").
- Pilih sumber yang kolomnya paling cocok dengan pertanyaan; boleh lebih dari satu step.
- Gunakan HANYA perintah SELECT (atau WITH ... SELECT). Dialect PostgreSQL-compatible.
- Untuk rentang tanggal: timestamp >= 'YYYY-MM-DD' AND timestamp <= 'YYYY-MM-DD 23:59:59'.
- Success rate: COUNT(*) FILTER (WHERE status = 'SUCCESS') * 100.0 / COUNT(*).
- Gunakan nilai kolom PERSIS seperti contoh nilai di skema (mis. 'VIRTUAL_ACCOUNT', bukan 'VA').
- Jika pertanyaan tidak butuh data (sapaan/umum), intent GENERAL dengan steps [] dan doc_query null.
- Jika data yang diminta TIDAK ADA di sumber mana pun, tetap pilih sumber terdekat;
  sistem akan mencoba dan melaporkan dengan jujur jika tidak ditemukan.
"""


def get_judge_prompt(user_query: str, results_text: str) -> str:
    """Prompt judge ringan: apakah hasil sudah cukup menjawab pertanyaan?"""
    return f"""Kamu adalah penilai hasil query untuk chatbot analitik.
PERTANYAAN USER: "{user_query}"

HASIL DATA YANG DIDAPAT:
{results_text}

Apakah data di atas SUDAH CUKUP untuk menjawab pertanyaan user secara faktual?
KEMBALIKAN HANYA JSON: {{"sufficient": true/false, "reason": "alasan singkat", "hint": "saran perbaikan query jika false, atau null"}}
Jangan minta data tambahan yang tidak diminta user. Jika angka utama yang diminta sudah ada, jawab true.
"""


def parse_json_response(text: str, default: Dict[str, Any]) -> Dict[str, Any]:
    """Ekstrak JSON dari respons LLM (toleran terhadap markdown fence)."""
    try:
        m = re.search(r"\{.*\}", (text or "").strip(), re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return default


# ============================================================
# Visualisasi (heuristik, tanpa LLM)
# ============================================================

def detect_chart_need(sql_data: List[Dict[str, Any]], user_query: str) -> Optional[Dict[str, Any]]:
    """Mendeteksi apakah data hasil query cocok divisualisasikan menjadi grafik Plotly."""
    if not sql_data or len(sql_data) < 2:
        return None

    first_row = sql_data[0]
    category_col = None
    numeric_col = None
    for k, v in first_row.items():
        if isinstance(v, (int, float)) and numeric_col is None:
            numeric_col = k
        elif isinstance(v, str) and category_col is None:
            category_col = k
    if not category_col or not numeric_col:
        return None

    query_lower = user_query.lower()
    chart_type = "bar"
    if any(w in query_lower for w in ["tren", "trend", "harian", "bulanan", "perkembangan"]):
        chart_type = "line"
    elif any(w in query_lower for w in ["proporsi", "persentase", "distribusi", "komposisi"]):
        chart_type = "pie"

    return {
        "type": chart_type,
        "x": [str(row[category_col]) for row in sql_data[:15]],
        "y": [float(row[numeric_col]) for row in sql_data[:15]],
        "x_label": category_col.replace("_", " ").title(),
        "y_label": numeric_col.replace("_", " ").title(),
        "title": f"Grafik Analisis: {numeric_col.replace('_', ' ').title()} berdasarkan {category_col.replace('_', ' ').title()}",
    }


# ============================================================
# Helper jawaban deterministik (tanpa LLM, anti-halusinasi)
# ============================================================

def render_data_fallback(sql_data: Optional[List[Dict[str, Any]]],
                         cited_documents: List[Dict[str, Any]],
                         sources_used: List[str]) -> str:
    """Render data yang sudah diambil menjadi markdown tanpa LLM."""
    parts = []
    if sql_data:
        src_label = ", ".join(sources_used) if sources_used else "database"
        parts.append(f"### 📊 Hasil Analisis Data\n\nBerdasarkan kueri ke {src_label}:\n")
        headers = list(sql_data[0].keys())
        parts.append("| " + " | ".join(h.replace("_", " ").title() for h in headers) + " |")
        parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in sql_data[:10]:
            parts.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
        if len(sql_data) > 10:
            parts.append(f"\n*(Menampilkan 10 dari {len(sql_data)} baris)*")
    if cited_documents:
        parts.append("\n### 📄 Referensi Dokumen\n")
        for d in cited_documents:
            parts.append(f"- **{d.get('source')}** ({d.get('reference')}): {d.get('snippet')}")
    return "\n".join(parts)


def render_not_found(attempt_log: List[Dict[str, Any]]) -> str:
    """Jawaban jujur saat semua budget percobaan habis tanpa hasil."""
    lines = [
        "### 🔍 Data Tidak Ditemukan\n",
        "Saya sudah mencoba mencari data yang Anda minta di sumber yang tersedia, "
        "namun tidak menemukan hasil yang relevan. **Saya tidak akan mengarang angka.**\n",
        "**Percobaan yang sudah dilakukan:**",
    ]
    for a in attempt_log:
        status = "error" if a.get("error") else f"{a.get('row_count', 0)} baris"
        sql_short = str(a.get("sql", ""))[:120]
        lines.append(f"- Sumber `{a.get('source')}`: {status} — `{sql_short}`")
        if a.get("error"):
            lines.append(f"  - Keterangan: {str(a['error'])[:160]}")
    lines.append(
        "\n**Saran:** periksa apakah data tersebut memang ada di sumber yang terdaftar, "
        "atau ubah kata kunci/rentang waktu pertanyaan Anda."
    )
    return "\n".join(lines)


def empty_result(intent: str = "GENERAL", answer: str = "", **extra) -> Dict[str, Any]:
    base = {
        "answer": answer,
        "intent": intent,
        "executed_sql": None,
        "sql_data": None,
        "chart_config": None,
        "cited_documents": [],
        "sources_used": [],
        "attempts": [],
    }
    base.update(extra)
    return base


def _collect_docs(doc_query: str, cited_documents: List[Dict[str, Any]]) -> str:
    """Jalankan RAG 1x, kumpulkan sitasi, return teks konteks dokumen."""
    ctx = ""
    results = search_knowledge_base(doc_query)
    valid = [d for d in results if d.get("source") not in ("Error", "Unknown")]
    if valid:
        ctx += "\nREFERENSI DOKUMEN RELEVAN:\n"
        for d in valid:
            ref_raw = str(d.get("reference", "General"))
            ref_label = f"Halaman {ref_raw}" if ref_raw.isdigit() else ref_raw
            cited_documents.append({
                "source": str(d.get("source", "Unknown")),
                "reference": ref_label,
                "snippet": str(d.get("content", ""))[:180] + "...",
            })
            ctx += f"- [Dokumen: {d.get('source')} | {ref_label}]:\n  {d.get('content')}\n"
    return ctx


# ============================================================
# Agent Utama
# ============================================================

def run_agent_turn(user_message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Menjalankan alur Agentic: Planning -> Execution Loop (retry budget) -> Synthesis."""
    if get_client() is None:
        return empty_result(
            "CONFIG_ERROR",
            "⚠️ **Kunci API Gemini belum diatur.**\n\nSilakan buka file `.env` di folder proyek, "
            "lalu masukkan kunci API Anda pada baris `GEMINI_API_KEY=...`.",
        )

    # Muat riwayat percakapan (aman jika PostgreSQL mati -> [])
    history_msgs = chat_store.load_recent(session_id) if session_id else []
    history_text = chat_store.format_history_for_prompt(history_msgs)

    executed_sql: Optional[str] = None
    sql_data: Optional[List[Dict[str, Any]]] = None
    cited_documents: List[Dict[str, Any]] = []
    sources_used: List[str] = []
    attempt_log: List[Dict[str, Any]] = []
    attempts_counter: Dict[str, int] = {}
    intent = "GENERAL"
    data_context = ""
    doc_attempted = False

    try:
        # === TAHAP 1: PLANNING AWAL ===
        plan = parse_json_response(
            generate_with_fallback(
                contents=get_plan_prompt(user_message, history_text),
                config=types.GenerateContentConfig(temperature=0.1),
            ).text,
            {"intent": "GENERAL", "steps": [], "doc_query": None},
        )
        intent = plan.get("intent", "GENERAL")
        steps = plan.get("steps") or []
        doc_query = plan.get("doc_query")

        # Kompatibilitas format lama {sql_query: ...}
        if not steps and plan.get("sql_query"):
            steps = [{"source": "postgres", "sql_query": plan["sql_query"]}]

        # === RAG (1x pencarian top-k) ===
        if doc_query:
            doc_attempted = True
            doc_ctx = _collect_docs(doc_query, cited_documents)
            if doc_ctx:
                data_context += doc_ctx
                sources_used.append("knowledge_base")

        # === TAHAP 2: EXECUTION LOOP dengan budget per sumber ===
        feedback = ""
        got_useful_data = False

        for round_no in range(MAX_ROUNDS):
            if not steps:
                break
            round_results_text = ""
            round_any_success = False

            for step in steps[:MAX_STEPS_PER_ROUND]:
                source = str(step.get("source", "postgres")).strip() or "postgres"
                sql = str(step.get("sql_query", "")).strip()
                if not sql:
                    continue

                used = attempts_counter.get(source, 0)
                if used >= MAX_ATTEMPTS_PER_SOURCE:
                    continue  # budget sumber ini habis (di-enforce kode, bukan LLM)
                attempts_counter[source] = used + 1

                res = execute_source_query(source, sql)
                attempt_log.append({
                    "source": source, "sql": sql,
                    "row_count": res.get("row_count", 0),
                    "error": res.get("error"),
                })
                executed_sql = sql

                if res.get("success") and res.get("data"):
                    round_any_success = True
                    got_useful_data = True
                    if sql_data is None:
                        sql_data = res["data"]
                    if source not in sources_used:
                        sources_used.append(source)
                    snippet = json.dumps(res["data"][:20], default=str, indent=1)
                    data_context += f"\nHASIL QUERY SQL (sumber: {source}):\n{snippet}\n"
                    round_results_text += f"[{source}] {res.get('row_count')} baris:\n{snippet[:1500]}\n"
                else:
                    err = res.get("error") or "0 baris (data kosong)"
                    data_context += f"\nPERCOBAAN GAGAL (sumber: {source}): {err}\n"
                    round_results_text += f"[{source}] GAGAL: {err}\n"

            if not round_results_text:
                break  # tidak ada step yang bisa dijalankan (budget habis semua)

            # Judge: cukup untuk menjawab? (hanya jika masih ada ronde tersisa)
            if round_any_success and round_no < MAX_ROUNDS - 1:
                try:
                    judge = parse_json_response(
                        generate_with_fallback(
                            contents=get_judge_prompt(user_message, trim_context(round_results_text, 6000)),
                            config=types.GenerateContentConfig(temperature=0.0),
                        ).text,
                        {"sufficient": True},
                    )
                    if judge.get("sufficient", True):
                        break
                    feedback = f"{judge.get('reason', '')} {judge.get('hint') or ''}".strip()
                except LLMError:
                    break  # judge gagal (kuota dll) -> pakai data yang ada
            elif round_any_success:
                break
            else:
                feedback = round_results_text[:1500]

            # Susun rencana perbaikan untuk ronde berikutnya
            if round_no < MAX_ROUNDS - 1:
                exhausted = [s for s, n in attempts_counter.items() if n >= MAX_ATTEMPTS_PER_SOURCE]
                fb = feedback
                if exhausted:
                    fb += f"\nSumber berikut SUDAH HABIS budget percobaannya, JANGAN dipakai lagi: {', '.join(exhausted)}."
                try:
                    replan = parse_json_response(
                        generate_with_fallback(
                            contents=get_plan_prompt(user_message, history_text, feedback=fb),
                            config=types.GenerateContentConfig(temperature=0.2),
                        ).text,
                        {"steps": []},
                    )
                    steps = [
                        s for s in (replan.get("steps") or [])
                        if attempts_counter.get(str(s.get("source", "")).strip(), 0) < MAX_ATTEMPTS_PER_SOURCE
                    ]
                    if replan.get("doc_query") and not doc_attempted:
                        doc_attempted = True
                        doc_ctx = _collect_docs(replan["doc_query"], cited_documents)
                        if doc_ctx:
                            data_context += doc_ctx
                            if "knowledge_base" not in sources_used:
                                sources_used.append("knowledge_base")
                except LLMError:
                    break

        # === BUDGET HABIS & TIDAK ADA DATA -> jawaban jujur deterministik ===
        needs_data = intent in ("SQL_ANALYTICS", "HYBRID_INVESTIGATION", "DOCUMENT_RAG")
        if needs_data and not got_useful_data and not cited_documents:
            result = empty_result(
                "NOT_FOUND",
                render_not_found(attempt_log),
                executed_sql=executed_sql,
                attempts=attempt_log,
                sources_used=sources_used,
            )
            if session_id:
                chat_store.save_turn(session_id, user_message, result["answer"],
                                     metadata={"intent": "NOT_FOUND", "attempts": attempt_log})
            return result

        # === TAHAP 3: SYNTHESIS ===
        history_synth = f"\nRIWAYAT SINGKAT:\n{history_text}\n" if history_text else ""
        context_trimmed = trim_context(data_context)
        synthesis_prompt = f"""Kamu adalah Data Analytics & Investigation Assistant di perusahaan pembayaran digital.
Pertanyaan Pengguna: "{user_message}"
{history_synth}
Konteks Data yang Berhasil Diambil dari Sistem:
{context_trimmed if context_trimmed else "Tidak ada data eksternal yang dibutuhkan untuk pertanyaan umum ini."}

INSTRUKSI JAWABAN:
1. Jawab pertanyaan pengguna secara akurat, lugas, dan profesional dalam Bahasa Indonesia.
2. Gunakan angka-angka riil dari HASIL QUERY SQL di atas. JANGAN MENGARANG ANGKA!
3. Sebutkan sumber datanya (mis. "berdasarkan database transaksi" atau nama sumber file/sheet).
4. Jika merujuk ke dokumen, sebutkan nama dokumennya (misal: SOP_Penanganan_Transaksi_Gagal.pdf).
5. Jika pertanyaannya investigasi ('mengapa gagal naik'), hubungkan anomali angka dengan laporan insiden.
6. Jika ada PERCOBAAN GAGAL di konteks dan data tidak lengkap, katakan terus terang bagian mana yang tidak ditemukan.
7. Format jawaban dengan markdown rapi (bullet points, bold untuk angka penting).
"""
        final_answer = ""
        try:
            synth_resp = generate_with_fallback(
                contents=synthesis_prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
            final_answer = synth_resp.text or "Analisis berhasil diselesaikan."
            if is_truncated(synth_resp):
                final_answer += "\n\n*(Jawaban terpotong oleh batas token output model.)*"
        except ContextTooLongError:
            # Trim agresif lalu coba sekali lagi
            try:
                smaller_prompt = synthesis_prompt.replace(context_trimmed, trim_context(data_context, 8000))
                synth_resp = generate_with_fallback(
                    contents=smaller_prompt,
                    config=types.GenerateContentConfig(temperature=0.2),
                )
                final_answer = synth_resp.text or "Analisis berhasil diselesaikan."
            except LLMError as e2:
                final_answer = friendly_error_message(e2) + "\n\n" + render_data_fallback(sql_data, cited_documents, sources_used)
        except LLMError as e:
            # Kuota habis / server sibuk: pesan RAMAH + data yang sudah diambil tetap tampil
            fallback_data = render_data_fallback(sql_data, cited_documents, sources_used)
            final_answer = friendly_error_message(e)
            if fallback_data:
                final_answer += "\n\n" + fallback_data
            if isinstance(e, QuotaExhaustedError):
                intent = "QUOTA_EXHAUSTED"

        chart_config = detect_chart_need(sql_data, user_message) if sql_data else None

        result = {
            "answer": final_answer,
            "intent": intent,
            "executed_sql": executed_sql,
            "sql_data": sql_data,
            "chart_config": chart_config,
            "cited_documents": cited_documents,
            "sources_used": sources_used,
            "attempts": attempt_log,
        }

    except LLMError as e:
        fallback_data = render_data_fallback(sql_data, cited_documents, sources_used)
        answer = friendly_error_message(e)
        if fallback_data:
            answer += "\n\n" + fallback_data
        result = empty_result(
            "QUOTA_EXHAUSTED" if isinstance(e, QuotaExhaustedError) else "ERROR",
            answer,
            executed_sql=executed_sql,
            sql_data=sql_data,
            cited_documents=cited_documents,
            sources_used=sources_used,
            attempts=attempt_log,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        result = empty_result(
            "ERROR",
            f"Terjadi kendala saat memproses analisis: {e}",
            executed_sql=executed_sql,
            cited_documents=cited_documents,
            sources_used=sources_used,
            attempts=attempt_log,
        )

    # Simpan giliran percakapan (no-op jika PostgreSQL mati)
    if session_id:
        chat_store.save_turn(
            session_id, user_message, result.get("answer", ""),
            metadata={
                "intent": result.get("intent"),
                "executed_sql": result.get("executed_sql"),
                "sources_used": result.get("sources_used"),
                "cited_documents": result.get("cited_documents"),
            },
        )
    return result