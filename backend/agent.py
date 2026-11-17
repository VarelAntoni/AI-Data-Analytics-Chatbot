"""
Core Agent: agent.py
Deskripsi:
  Orkestrator AI Chatbot menggunakan Pola Router-Synthesizer (Two-Stage Agent):
  Tahap 1 (Planning / Intent Routing):
    - LLM menganalisis pertanyaan user berdasarkan skema PostgreSQL dan indeks dokumen.
    - Menghasilkan rencana eksekusi terstruktur (SQL Query dan/atau Query Pencarian Dokumen).
  Tahap 2 (Execution via MCP Tools):
    - Mengeksekusi SQL ke PostgreSQL (dengan guardrail SELECT-only).
    - Mencari potongan dokumen relevan di ChromaDB.
  Tahap 3 (Synthesis & Visualization):
    - LLM merangkum data angka dan konteks dokumen menjadi jawaban profesional.
    - Otomatis menghasilkan konfigurasi grafik Plotly interaktif.
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Import Google GenAI SDK
from google import genai
from google.genai import types

# Import tools dari MCP Servers
from mcp_servers.analytics_server import get_database_schema, execute_analytics_query
from mcp_servers.knowledge_server import search_knowledge_base

load_dotenv()

# Inisialisasi client Google GenAI secara global
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

import time

# Daftar model cepat dan stabil untuk failover otomatis jika ada lonjakan traffic (503)
CANDIDATE_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest"
]

def generate_with_fallback(contents, config=None, retries=2):
    """Mencoba memanggil model Gemini dengan retry dan rotasi cadangan otomatis saat ada 503 (High Demand)."""
    global client
    if client is None:
        load_dotenv(override=True)
        key = os.getenv("GEMINI_API_KEY", "")
        if key:
            client = genai.Client(api_key=key)
        else:
            raise ValueError("Kunci API Gemini belum diatur di file .env")

    last_err = None

    for m in CANDIDATE_MODELS:
        for attempt in range(retries):
            try:
                return client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=config
                )
            except Exception as e:
                err_str = str(e)
                last_err = e
                # Jika terkena 503 (Spike demand), tunggu 1.5 detik lalu coba lagi
                if "503" in err_str:
                    time.sleep(1.5)
                    continue
                else:
                    break

    raise last_err


def get_plan_prompt(user_query: str) -> str:
    """Prompt untuk Tahap 1: Merencanakan query SQL dan pencarian dokumen."""
    schema = get_database_schema()
    return f"""Kamu adalah Query Planner untuk AI Analytics Chatbot.
Tugasmu adalah menganalisis pertanyaan pengguna dan menentukan apakah pertanyaan tersebut membutuhkan:
1. Kueri SQL ke PostgreSQL (untuk data angka, agregasi, volume, tren, persentase).
2. Pencarian Dokumen RAG (untuk SOP, kebijakan refund, aturan eskalasi, penjelasan insiden).
3. Keduanya (Hybrid - untuk investigasi akar masalah/mengapa kegagalan meningkat).

SKEMA DATABASE POSTGRESQL:
{schema}

DOKUMEN YANG TERSEDIA:
- SOP_Penanganan_Transaksi_Gagal.pdf (Alur eskalasi L1/L2, penanganan status PENDING > 15 mnt, tabel kode error)
- Kebijakan_Refund_dan_Chargeback.docx (Batas waktu refund: VA 1x24 jam, E-Wallet real-time, Kartu Kredit 7-14 hari)
- Laporan_Insiden_BCA_VA_Oktober_2024.txt (Insiden SEV-1 pada 15-20 Okt 2024: migrasi switch gateway BCA v4.0 timeout)

PERTANYAAN PENGGUNA: "{user_query}"

KEMBALIKAN HANYA JSON DENGAN FORMAT BERIKUT (TANPA TEKS LAIN):
```json
{{
  "intent": "SQL_ANALYTICS" | "DOCUMENT_RAG" | "HYBRID_INVESTIGATION" | "GENERAL",
  "sql_query": "SELECT ... (atau null jika tidak butuh SQL)",
  "doc_query": "kata kunci pencarian dokumen (atau null jika tidak butuh dokumen)"
}}
```
Catatan SQL:
- Gunakan HANYA perintah SELECT.
- Dialek PostgreSQL: untuk rentang tanggal gunakan timestamp >= 'YYYY-MM-DD' AND timestamp <= 'YYYY-MM-DD 23:59:59'.
"""


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
        "title": f"Grafik Analisis: {numeric_col.replace('_', ' ').title()} berdasarkan {category_col.replace('_', ' ').title()}"
    }


def run_agent_turn(user_message: str, chat_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """Menjalankan alur Agentic: Planning -> Execution -> Synthesis."""
    global client
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not client and api_key:
        client = genai.Client(api_key=api_key)

    if not client:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            return {
                "answer": "⚠️ **Kunci API Gemini belum diatur.**\n\nSilakan buka file `.env` di folder proyek, lalu masukkan kunci API Anda pada baris `GEMINI_API_KEY=...`.",
                "intent": "CONFIG_ERROR",
                "executed_sql": None,
                "sql_data": None,
                "chart_config": None,
                "cited_documents": []
            }

    executed_sql = None
    sql_data = None
    cited_documents = []
    intent = "GENERAL"

    try:
        # === TAHAP 1: PLANNING (Intent Routing) ===
        plan_prompt = get_plan_prompt(user_message)

        plan_resp = generate_with_fallback(
            contents=plan_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1
            )
        )

        plan_text = plan_resp.text.strip()
        # Ekstrak JSON dari teks
        json_match = re.search(r"\{.*\}", plan_text, re.DOTALL)
        if json_match:
            plan = json.loads(json_match.group(0))
        else:
            plan = {"intent": "GENERAL", "sql_query": None, "doc_query": None}

        intent = plan.get("intent", "GENERAL")
        sql_query = plan.get("sql_query")
        doc_query = plan.get("doc_query")

        # === TAHAP 2: EKSEKUSI DATA (MCP Tools) ===
        data_context = ""

        # 2A. Eksekusi SQL jika ada
        if sql_query:
            executed_sql = sql_query
            sql_res = execute_analytics_query(sql_query)
            if sql_res.get("success"):
                sql_data = sql_res.get("data")
                data_context += f"\nHASIL QUERY SQL (PostgreSQL):\n{json.dumps(sql_data, default=str, indent=2)}\n"
            else:
                data_context += f"\nERROR QUERY SQL: {sql_res.get('error')}\n"

        # 2B. Eksekusi Pencarian Dokumen jika ada
        if doc_query:
            doc_results = search_knowledge_base(doc_query)
            data_context += "\nREFERENSI DOKUMEN RELEVAN:\n"
            for d in doc_results:
                ref_raw = str(d.get("reference", "General"))
                ref_label = f"Halaman {ref_raw}" if ref_raw.isdigit() else ref_raw
                cited_documents.append({
                    "source": str(d.get("source", "Unknown")),
                    "reference": ref_label,
                    "snippet": str(d.get("content", ""))[:180] + "..."
                })
                data_context += f"- [Dokumen: {d.get('source')} | {ref_label}]:\n  {d.get('content')}\n"

        # === TAHAP 3: SYNTHESIS (Menyusun Jawaban Akhir) ===
        final_answer = ""
        try:
            synthesis_prompt = f"""Kamu adalah Data Analytics & Investigation Assistant di perusahaan pembayaran digital.
Pertanyaan Pengguna: "{user_message}"

Konteks Data yang Berhasil Diambil dari Sistem:
{data_context if data_context else "Tidak ada data eksternal yang dibutuhkan untuk pertanyaan umum ini."}

INSTRUKSI JAWABAN:
1. Jawab pertanyaan pengguna secara akurat, lugas, dan profesional dalam Bahasa Indonesia.
2. Gunakan angka-angka riil dari HASIL QUERY SQL di atas. JANGAN MENGARANG ANGKA!
3. Jika merujuk ke dokumen, sebutkan nama dokumennya (misal: SOP_Penanganan_Transaksi_Gagal.pdf).
4. Jika pertanyaannya investigasi ('mengapa gagal naik'), hubungkan anomali angka transaksi dengan informasi di laporan insiden.
5. Format jawaban dengan markdown rapi (gunakan bullet points, bold untuk angka penting).
"""

            synth_resp = generate_with_fallback(
                contents=synthesis_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2
                )
            )
            final_answer = synth_resp.text or "Analisis berhasil diselesaikan."

        except Exception as synth_err:
            print(f"⚠️ Gagal pada sintesis LLM: {synth_err}. Mengaktifkan Fallback Formatter Deterministik.")
            # Fallback deterministik: Tampilkan hasil query SQL langsung dalam bentuk tabel Markdown
            if sql_data:
                final_answer = "### 📊 Hasil Analisis Data Transaksi\n\nBerdasarkan kueri ke database PostgreSQL, berikut data yang berhasil dianalisis:\n\n"
                headers = list(sql_data[0].keys())
                final_answer += "| " + " | ".join([h.replace("_", " ").title() for h in headers]) + " |\n"
                final_answer += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                for row in sql_data[:10]:
                    final_answer += "| " + " | ".join([str(row.get(h, '')) for h in headers]) + " |\n"
                if len(sql_data) > 10:
                    final_answer += f"\n*(Menampilkan 10 dari total {len(sql_data)} baris data)*\n"
            elif cited_documents:
                final_answer = "### 📄 Rangkuman Dokumen SOP & Prosedur\n\nBerdasarkan penelusuran dokumen operasional:\n\n"
                for d in cited_documents:
                    final_answer += f"- **{d.get('source')}** ({d.get('reference')}):\n  {d.get('snippet')}\n\n"
            else:
                final_answer = f"Kueri berhasil diproses, namun server sedang sibuk: {str(synth_err)}"

        # Deteksi apakah data query perlu dibuatkan grafik interaktif
        chart_config = None
        if sql_data:
            chart_config = detect_chart_need(sql_data, user_message)

        return {
            "answer": final_answer,
            "intent": intent,
            "executed_sql": executed_sql,
            "sql_data": sql_data,
            "chart_config": chart_config,
            "cited_documents": cited_documents
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "answer": f"Terjadi kendala saat memproses analisis: {str(e)}",
            "intent": "ERROR",
            "executed_sql": executed_sql,
            "sql_data": None,
            "chart_config": None,
            "cited_documents": cited_documents
        }
