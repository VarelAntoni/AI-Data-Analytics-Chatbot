# HANDOVER PROMPT — AI-Data-Analytics-Chatbot (Multi-Source Upgrade)

> Salin seluruh isi bagian "Prompt" di bawah ke sesi AI/developer baru untuk melanjutkan pekerjaan dengan konteks penuh.

---

## Prompt

Kamu melanjutkan pekerjaan pada proyek **AI-Powered Data Analytics Chatbot** di repo `https://github.com/VarelAntoni/AI-Data-Analytics-Chatbot` (branch `main`). Ini adalah **laptop/mesin baru** yang belum pernah menjalankan proyek ini. Baca seluruh konteks ini sebelum mengubah apa pun.

### 0. Setup cepat di mesin baru (lakukan pertama kali)

```powershell
git clone https://github.com/VarelAntoni/AI-Data-Analytics-Chatbot.git
cd AI-Data-Analytics-Chatbot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env: isi GEMINI_API_KEY asli (dari https://aistudio.google.com/), pastikan DB_PORT=5433
docker compose up -d
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe scripts\seed_data.py
.\.venv\Scripts\python.exe scripts\generate_docs_and_excel.py
.\.venv\Scripts\python.exe run.py   # buka http://localhost:8000
```

Prasyarat mesin: Python 3.10+ (diverifikasi di 3.14.5), Docker Desktop, dan **VC++ Redistributable x64** (wajib untuk chromadb; jika import chromadb gagal "DLL load failed", instal dari https://aka.ms/vs/17/release/vc_redist.x64.exe).
Catatan: `.env` TIDAK ada di repo (gitignored, berisi API key). Harus dibuat manual dari `.env.example`. Data transaksi & ChromaDB juga tidak di repo; dihasilkan oleh dua script di atas. Angka transaksi akan berbeda dari laptop asal karena seeding memakai random tanpa seed tetap (normal).

### 1. Apa sistem ini

Chatbot analitik finansial berbahasa Indonesia: user bertanya bahasa alami → AI merencanakan SQL dan/atau pencarian dokumen → eksekusi → jawaban markdown + grafik Plotly + sitasi dokumen. Stack: **FastAPI + Google Gemini (SDK `google-genai`) + MCP tools in-process (`mcp` 1.x FastMCP) + PostgreSQL 16 (Docker) + DuckDB + ChromaDB**. **Tanpa LangChain/LangGraph** — orkestrasi agent ditulis manual (pola ReAct sederhana dengan loop retry).

### 2. Upgrade besar yang baru selesai (jangan di-regress)

Sistem di-upgrade dari single-source PostgreSQL stateless menjadi:

1. **Multi-sumber auto-routing** — `mcp_servers/source_registry.py`:
   - Sumber: `postgres` + CSV/XLSX/JSON/Google Sheets dari URL, didaftarkan di `data_sources.json` (contoh: `data_sources.example.json`).
   - Google Sheets publik multi-tab: discovery tab otomatis (parse HTML halaman sheet → fetch `export?format=csv&gid=N` per tab). Tiap tab = view DuckDB terpisah (snake_case). Join antar tab satu sheet didukung. Sheet TIDAK disalin ke PostgreSQL.
   - Fetch + cache memori TTL `DATA_SOURCE_REFRESH_SECONDS` (default 300s), stale-on-error.
   - Skema semua sumber di-inspeksi otomatis (kolom, tipe, sampel nilai) untuk prompt planner; postgres via `information_schema` terfilter allowlist.
2. **Agent loop retry berbudget** — `backend/agent.py`:
   - Planning JSON `{intent, steps:[{source, sql_query}], doc_query}` → eksekusi maks 3 ronde, **budget 3 percobaan per sumber di-enforce kode Python** (`attempts_counter`), judge LLM ringan menilai kecukupan hasil.
   - Budget habis tanpa data → jawaban deterministik `NOT_FOUND` + log percobaan, TANPA panggilan LLM (anti-halusinasi).
   - Respons API punya `sources_used` dan `attempts`.
3. **Penanganan error LLM terpusat** — `backend/llm_client.py`:
   - SATU-SATUNYA gerbang panggilan Gemini (`generate_with_fallback`). Exception bertipe: `QuotaExhaustedError` (429), `ContextTooLongError` (400 token), `InvalidKeyError`.
   - Kuota habis → pesan markdown ramah + data yang sudah diambil tetap dirender deterministik; konteks kepanjangan → trim (budget 30rb karakter) bukan rotasi model; failover 4 model saat 503.
   - Jangan panggil `client.models.generate_content` langsung di luar modul ini (kecuali endpoint diagnostik `/api/test-agent`).
4. **Memori percakapan (checkpoint-postgres manual)** — `backend/chat_store.py`:
   - Tabel `chat_sessions` + `chat_messages` (metadata JSONB) di PostgreSQL yang sama, dibuat saat startup. Window 6 pesan masuk prompt planning & sintesis (resolve kata "tersebut/tadi").
   - Frontend: UUID sesi di localStorage, restore via `GET /api/history/{session_id}`, tombol "+ Sesi Baru". PostgreSQL mati → chat tetap jalan tanpa history (graceful).
5. **Keamanan berlapis**:
   - Guardrail terpusat `check_sql_guardrail` untuk SEMUA engine: SELECT/WITH only, blocklist keyword (termasuk perintah DuckDB: ATTACH/COPY/INSTALL/PRAGMA...), anti multi-statement.
   - Allowlist sumber (hanya terdaftar di registry) + allowlist tabel postgres (`PG_ALLOWED_TABLES`, default `transactions`). Tabel chat history sengaja DI LUAR allowlist.
   - Sesi postgres analitik `readonly=True`.
6. **RAG upgrade** — `mcp_servers/knowledge_server.py`:
   - Collection `operational_documents_v2` (nama baru agar chunk lama tidak stale). `RAG_TOP_K` (default 3) & `RAG_MAX_DISTANCE` (default 1.5, buang chunk tak relevan) via .env.
   - DOCX chunk 500 karakter **overlap 20%** (step 400). PDF per halaman; halaman teks < `PDF_MIN_TEXT_CHARS` (50) di-render pypdfium2 → transkripsi **Gemini Vision**; metadata `extraction_method: native|vision`.
7. **Frontend ringan** — `static/index.html` + `static/vendor/plotly-basic.min.js`:
   - Plotly basic ~1MB self-host, **lazy-load saat chart pertama** (bukan page load), purge instance lama (maks 8 hidup), fallback tabel markdown jika library gagal. Badge sumber/percobaan/kuota/NOT_FOUND.

### 3. Peta file

| File | Peran |
|---|---|
| `run.py` | Entrypoint uvicorn port 8000 (auto-reload) |
| `backend/main.py` | API: POST /api/chat, GET /api/health (per sumber), /api/sources, /api/history/{id}, /api/test-agent |
| `backend/agent.py` | Loop planning→execution→judge→synthesis; `run_agent_turn(user_message, session_id)` |
| `backend/llm_client.py` | Gerbang Gemini + klasifikasi error + trim_context |
| `backend/chat_store.py` | History percakapan PostgreSQL |
| `mcp_servers/source_registry.py` | Registry multi-sumber, DuckDB, cache, guardrail, allowlist |
| `mcp_servers/analytics_server.py` | MCP tools (list_data_sources, get_source_schema, execute_source_query + tools lama delegate) |
| `mcp_servers/knowledge_server.py` | RAG ChromaDB (top-k, threshold, overlap, PDF vision) |
| `data_sources.json` | Daftar sumber aktif (sekarang kosong `{"sources": []}`) |
| `scripts/evaluate.py` | Suite 10 kasus (TIDAK diubah, kompatibel via tools lama) |
| `scripts/smoke_test.py` | Uji cepat registry + guardrail + chat store |
| `scripts/seed_data.py` | Generate 20rb transaksi + anomali BCA VA 15-20 Okt 2024 |
| `scripts/generate_docs_and_excel.py` | Generate PDF/DOCX/TXT knowledge base + Excel |

### 4. Environment (Windows, sudah terverifikasi)

- Python 3.14.5, venv proyek `.venv`. Jalankan: `.\.venv\Scripts\python.exe` dari root proyek.
- **Set `$env:PYTHONIOENCODING="utf-8"`** sebelum script yang print emoji (default cp1252 crash).
- Dependensi: `requirements.txt` pakai `>=` (kompatibel Py 3.14), KECUALI **`mcp>=1.3.0,<2`** (mcp 2.x me-rename FastMCP → MCPServer, breaking).
- chromadb 1.5.x butuh **VC++ Redistributable x64** (sudah terinstal di mesin ini).
- PostgreSQL: `docker compose up -d` → container `analytics_postgres`, port **5433**, db `analytics_db`, user `postgres`/`postgrespassword`. `.env` lokal (gitignored) berisi `DB_PORT=5433` + `GEMINI_API_KEY` asli.
- Seed: `python scripts/seed_data.py` lalu `python scripts/generate_docs_and_excel.py`.
- Server: `python run.py` → http://localhost:8000.
- Model Gemini utama `gemini-3.8-flash` sering 503; failover `gemini-3.1-flash-lite` works. Saat badai 503, latensi chat bisa >60-160s; client HTTP mungkin timeout tapi server lanjut proses — hasil bisa diambil via `/api/history/{session_id}`.

### 5. Status verifikasi (semua lulus saat implementasi)

- SQL analitik Oktober per status (angka riil dari DB).
- Follow-up "kalau September? bandingkan dengan yang tadi" → history resolve konteks, query September benar.
- Auto-routing: pertanyaan ringkasan partner → agent pilih sumber CSV, bukan postgres.
- NOT_FOUND jujur: pertanyaan tabel `employee_salary` (tidak ada) → ditolak allowlist, jawaban "tidak ditemukan" + log percobaan, tanpa angka karangan.
- Injection `DROP TABLE`/`DELETE` via chat → ditolak; 20.000 transaksi utuh; guardrail multi-statement/sumber-tak-terdaftar aktif.
- RAG sitasi 3 dokumen (PDF halaman, TXT seksi, DOCX bagian).
- Chart pie lazy-load dari vendor lokal; restore history setelah refresh browser.
- Suite `evaluate.py`: **8/10 PASS**, security 100%, Hit Rate@3 80%, MRR 0.8, faithfulness 75%, SQL EX 80%, latensi rata-rata 82s (akibat badai 503, bukan kode). EVAL-05 WARN karena suite memanggil agent tanpa session_id sehingga kata "tersebut" tak punya rujukan — by design, bukan bug. Laporan: `data/evaluation_report.json`.

### 6. Status git

- Remote `origin` = repo GitHub di atas. Commit utama: `9749316` (feat: multi-source...), `cea6bcc` (Changes) — keduanya SUDAH di GitHub.
- Commit `0f53910` (chore: evaluation report) saat handover ditulis masih lokal di laptop asal (ahead 1). Jika di clone baru `data/evaluation_report.json` masih versi lama, itu sebabnya; minta pemilik push, atau abaikan (laporan bisa di-regenerate via `scripts/evaluate.py`).
- Catatan kredensial laptop asal: sempat 403 karena Git memakai akun `varelantoni99` padahal repo milik `VarelAntoni`; sudah dibereskan. Di mesin baru, login Git sebagai akun yang punya akses tulis ke repo.
- `.env`, `chroma_db/`, dan `data/test_sources/` ter-ignore. Jangan pernah commit `.env`.

### 7. Utang teknis / langkah lanjutan yang disepakati tapi belum dikerjakan

1. **README masih mengklaim benchmark lama 100%** — perlu update tabel skor ke hasil terbaru + catatan kondisi 503 (atau re-run evaluasi saat API stabil).
2. **EVAL-05**: suite evaluasi tidak memakai session_id; opsi perbaikan: buat pertanyaan self-contained, atau beri session_id berurutan untuk kasus hybrid.
3. **Role PostgreSQL read-only khusus** (`analytics_reader`, GRANT SELECT saja) belum dibuat di docker-compose; saat ini read-only di level sesi driver + allowlist. Enhancement keamanan yang direncanakan.
4. **Discovery tab Google Sheets via parse HTML tidak resmi** — bisa rusak jika Google ubah struktur; fallback manual `tabs: [{name, gid}]` per sumber sudah didukung di config. Alternatif resmi: Sheets API v4 + API key.
5. **Tailwind masih CDN runtime** — idealnya build statis untuk produksi.
6. **Uji gsheet multi-tab end-to-end belum dilakukan dengan sheet publik sungguhan** (baru CSV via HTTP lokal); perlu sheet contoh untuk validasi discovery tab.
7. Faithfulness evaluate.py masih keyword-matching longgar (bukan LLM-as-judge); metrik "OOD 100%" di cetak hardcoded. Perbaikan kualitas evaluasi = pekerjaan terpisah.

### 8. Aturan kerja

- Jangan regress: guardrail terpusat, budget retry Python-enforced, jawaban NOT_FOUND deterministik, semua panggilan LLM lewat `llm_client`, history graceful-degradation.
- Tanpa LangChain/LangGraph (keputusan sadar pemilik proyek).
- Bahasa jawaban chatbot & komentar kode: Indonesia. Jangan pakai em dash dalam respons ke user.
- Uji perubahan dengan `scripts/smoke_test.py` + endpoint API; suite penuh `python scripts/evaluate.py` dari root proyek (butuh Docker + API key aktif).