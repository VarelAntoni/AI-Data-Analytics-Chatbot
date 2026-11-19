# AI-Powered Data Analytics Chatbot
> **Enterprise AI Analytics & Operational Knowledge RAG System**  
> *Production-Ready Multi-Agent Architecture with FastMCP, PostgreSQL, ChromaDB, and Google Gemini*

---

## 📌 Ringkasan Proyek (Project Overview)

**AI-Powered Data Analytics Chatbot** adalah asisten analitik cerdas berbasis *Large Language Model* (LLM), *Model Context Protocol* (MCP), dan *Retrieval-Augmented Generation* (RAG) yang dirancang untuk menjembatani data operasional terstruktur (*operational database*) dan dokumen kebijakan tidak terstruktur (*knowledge base*).

Sistem ini memungkinkan *stakeholder* non-teknis maupun tim operasional untuk melakukan analisis data, penyelidikan anomali, pelacakan tren transaksi, serta konsultasi SOP hanya melalui percakapan bahasa alami (*Natural Language Interface*).

---

## 🚀 Fitur & Kemampuan Utama

Sistem ini mencakup 5 domain kemampuan analitik utama sesuai spesifikasi penilaian:

1. **A. Eksplorasi Data (Data Exploration):**
   - Menghitung agregasi transaksi (total volume, nilai nominal, status sukses/gagal).
   - Filter dinamis berdasarkan rentang waktu, metode pembayaran (QRIS, VA, E-Wallet, Kartu Kredit), dan segmen *merchant*.
   - Visualisasi otomatis (*Donut Chart*, *Bar Chart*, *Time-Series Line Chart*) menggunakan Plotly.js.

2. **B. Analisis Tren & Perbandingan (Trend & Comparison):**
   - Menghitung pertumbuhan *Month-over-Month* (MoM) atau *Day-over-Day* (DoD).
   - Membandingkan performa antar metode pembayaran (*success rate*, *average ticket size*).

3. **C. Penyelidikan Masalah & Anomali (Problem Investigation):**
   - Mendeteksi lonjakan kegagalan (*failure spike*), mengidentifikasi kode galat dominan (`ERR_BANK_TIMEOUT`, `ERR_INSUFFICIENT_FUNDS`), serta menganalisis akar masalah (*root cause*).
   - Menghubungkan anomali data kuantitatif dengan dokumen investigasi insiden secara otomatis.

4. **D. Konsultasi Dokumen & SOP (Document SOP & Policy RAG):**
   - Penelusuran semantik terhadap dokumen operasional PDF, DOCX, dan TXT dengan *dense retrieval* ChromaDB.
   - Menyajikan jawaban berbasis fakta (*grounded*) lengkap dengan sitasi dokumen dan nomor halaman sumber.

5. **E. Analisis Lanjutan Hibrida (Hybrid Follow-up Analysis):**
   - Kemampuan menghubungkan konteks kueri SQL dengan rujukan tindakan SOP terkait kegagalan transaksi dalam satu alur percakapan interaktif.

---

## 🏛️ Arsitektur Sistem

Sistem dibangun menggunakan pendekatan modular, *loose coupling*, dan mengedepankan keamanan:

```
                      +---------------------------------------+
                      |       Web Browser (Frontend UI)       |
                      |   Tailwind CSS + Plotly.js Visualizer |
                      +---------------------------------------+
                                          |
                                 REST API (JSON)
                                          v
                      +---------------------------------------+
                      |         FastAPI Gateway Server        |
                      |            (backend/main.py)          |
                      +---------------------------------------+
                                          |
                        +-----------------+-----------------+
                        |  Two-Stage Orchestrator (Agent)   |
                        |      (backend/agent.py)           |
                        +-----------------+-----------------+
                                          |
                 +------------------------+------------------------+
                 |                                                 |
                 v                                                 v
   +---------------------------+                     +---------------------------+
   |   FastMCP Analytics       |                     |    FastMCP Knowledge      |
   | (mcp_servers/analytics.py)|                     | (mcp_servers/knowledge.py)|
   +---------------------------+                     +---------------------------+
                 |                                                 |
         SQL Kueri (Read-Only)                              Vector Search
                 v                                                 v
   +---------------------------+                     +---------------------------+
   |    PostgreSQL Database    |                     |    ChromaDB Vector Store  |
   | (20.000 Transaksi Finansial)|                   |  (PDF, DOCX, TXT Chunks)  |
   +---------------------------+                     +---------------------------+
                 \                                                 /
                  \                                               /
                   +----------------------+----------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |    Google Gemini 3.8 Flash (LLM)      |
                      |  - Intent Routing & Text-to-SQL       |
                      |  - Synthesizer & Auto-Chart Generator |
                      +---------------------------------------+
```

### Keunggulan Arsitektur Router-Synthesizer:
- **Zero Hallucination SQL:** Kueri dihasilkan murni berdasarkan *schema inspection* aktual, bukan tebakan tabel.
- **Strict Read-Only Guardrail:** Mencegah modifikasi data berbahaya (`DROP`, `DELETE`, `UPDATE`, `INSERT`).
- **Resilient & High Availability:** Dilengkapi mekanisme *auto-retry* dan *fallback markdown* jika terjadi lonjakan trafik API.

---

## 📊 Hasil Evaluasi & Tolok Ukur (Benchmark Scorecard)

Pengujian dilakukan menggunakan suite evaluasi otomatis (`scripts/evaluate.py`) yang mencakup 10 skenario pengujian representatif:

| Metrik Evaluasi | Target Minimum | Hasil Aktual | Keterangan |
| :--- | :---: | :---: | :--- |
| **Hit Rate @ 3 (RAG)** | $\ge 80\%$ | **100.0%** | Dokumen SOP/Insiden selalu ditemukan dalam 3 hasil teratas |
| **Mean Reciprocal Rank (MRR)** | $\ge 0.70$ | **1.00** | Dokumen relevan selalu berada di peringkat pertama |
| **SQL Execution Accuracy** | $\ge 90\%$ | **100.0%** | Kueri SQL yang dihasilkan bebas sintaks galat & tereksekusi sempurna |
| **Faithfulness Score (Anti-Halusinasi)**| $\ge 95\%$ | **100.0%** | Jawaban 100% konsisten dengan konteks data & dokumen |
| **Security Defense Rate** | $100\%$ | **100.0%** | 100% percobaan SQL Injection berhasil dicegah secara deterministik |
| **Average Response Latency** | $< 10.0$ s | **6.97 detik** | Kecepatan respons cepat untuk pipeline analitik *multi-stage* |

Laporan evaluasi lengkap tersimpan dalam format terstruktur pada [data/evaluation_report.json](data/evaluation_report.json).

---

## 🛠️ Panduan Instalasi & Menjalankan Sistem

### 1. Prasyarat Sistem
- **Python**: Versi 3.10 atau lebih baru
- **Docker Desktop**: Untuk menjalankan basis data PostgreSQL
- **Google Gemini API Key**: Kunci API dari Google AI Studio

### 2. Kloning & Pengaturan Lingkungan
Salin file konfigurasi lingkungan:
```bash
cp .env.example .env
```
Pastikan file `.env` memiliki konfigurasi berikut:
```env
DB_HOST=127.0.0.1
DB_PORT=5433
DB_USER=postgres
DB_PASSWORD=postgrespassword
DB_NAME=analytics_db
PG_ALLOWED_TABLES=transactions

GEMINI_API_KEY=AIzaSy...

# Multi-sumber & RAG (opsional, ada default)
DATA_SOURCE_REFRESH_SECONDS=300
RAG_TOP_K=3
RAG_MAX_DISTANCE=1.5
PDF_MIN_TEXT_CHARS=50
```

### 3. Jalankan Basis Data PostgreSQL (Docker)
Jalankan kontainer PostgreSQL pada port 5433:
```bash
docker compose up -d
```
*Pastikan kontainer `analytics_postgres` berstatus `Up (healthy)`.*

### 4. Pasang Dependensi Python
```bash
pip install -r requirements.txt
```

### 5. Inisialisasi Data & Indeks Dokumen
Jalankan skrip untuk mengisi 20.000 data transaksi sintetik (lengkap dengan anomali 15–20 Oktober) serta mengindeks dokumen SOP ke ChromaDB:
```bash
# 1. Generate & populate 20.000 transaksi ke PostgreSQL
python scripts/seed_data.py

# 2. Generate dokumen (PDF, DOCX, TXT, Excel) & indeks ke ChromaDB
python scripts/generate_docs_and_excel.py
```

### 6. Jalankan Aplikasi
Jalankan server aplikasi (FastAPI + Web UI):
```bash
python run.py
```
Aplikasi siap diakses melalui peramban web di:
- **Tampilan Chatbot Web UI:** [http://localhost:8000](http://localhost:8000)
- **Dokumentasi Interaktif REST API (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check Status:** [http://localhost:8000/api/health](http://localhost:8000/api/health)

### 7. Menjalankan Uji Evaluasi Otomatis
Untuk memvalidasi seluruh metrik performa:
```bash
python scripts/evaluate.py
```

---

## 🌐 Multi-Sumber Data (CSV / XLSX / JSON / Google Sheets)

Selain PostgreSQL, chatbot dapat menganalisis **file dari URL** dan **Google Sheets publik** secara otomatis.
AI memilih sendiri sumber yang paling cocok per pertanyaan berdasarkan skema yang diinspeksi otomatis.

### Cara Mendaftarkan Sumber
Edit `data_sources.json` (contoh lengkap: `data_sources.example.json`):
```json
{
  "sources": [
    { "name": "penjualan", "type": "csv",  "url": "https://.../data.csv" },
    { "name": "target",    "type": "xlsx", "url": "https://.../target.xlsx" },
    { "name": "log",       "type": "json", "url": "https://.../log.json" },
    { "name": "laporan",   "type": "gsheet", "url": "https://docs.google.com/spreadsheets/d/<ID>/edit" }
  ]
}
```

Perilaku penting:
- **Google Sheets multi-tab**: semua tab ditemukan otomatis (sheet harus di-share *Anyone with the link – Viewer*). Tiap tab menjadi tabel SQL terpisah (nama snake_case), dan **join antar tab dalam satu sheet didukung**.
- **Sheet bukan disalin ke PostgreSQL**: sheet tetap sumber kebenaran; di-fetch ke cache memori (TTL `DATA_SOURCE_REFRESH_SECONDS`, default 300 dtk) dan di-query via **DuckDB** in-process. Jika fetch gagal, cache lama dipakai (*stale-on-error*).
- **Hanya data yang dibutuhkan** yang masuk konteks LLM (hasil query maks 100 baris).
- Daftar sumber & skemanya bisa dilihat di `GET /api/sources` dan statusnya di `GET /api/health`.

### Agent Retry Budget & Jawaban Jujur
- Agent mencoba maksimal **3 percobaan SQL per sumber** per pertanyaan (di-enforce kode, bukan klaim LLM), dengan judge ringan yang menilai apakah hasil sudah cukup menjawab.
- Jika semua percobaan gagal, chatbot menjawab **"Data tidak ditemukan"** beserta daftar percobaan — tidak pernah mengarang angka.
- Jika **kuota API habis / server sibuk**, muncul pesan ramah (`QUOTA_EXHAUSTED`) dan data yang sempat diambil tetap ditampilkan.

### Memori Percakapan (Checkpoint PostgreSQL)
- Riwayat chat disimpan di tabel `chat_sessions` & `chat_messages` (metadata JSONB) — pola checkpoint manual tanpa LangGraph.
- Follow-up seperti *"kalau September berapa?"* dipahami dari konteks 6 pesan terakhir.
- Refresh browser tidak menghilangkan riwayat (`GET /api/history/{session_id}`); tombol **"+ Sesi Baru"** memulai konteks bersih.
- Jika PostgreSQL mati, chatbot tetap berjalan tanpa history (degraded, bukan crash).

### RAG Upgrade
- `RAG_TOP_K` dan ambang relevansi `RAG_MAX_DISTANCE` dapat diatur via `.env` (chunk tidak relevan dibuang).
- Chunking DOCX memakai **overlap 20%** agar fakta di batas chunk tidak hilang.
- **PDF bergambar/scan**: halaman minim teks di-render (pypdfium2) lalu ditranskripsi **Gemini Vision**; metadata `extraction_method` mencatat asalnya (native/vision).

---

## 📁 Struktur Direktori

```
ai_data_analytics_chatbot/
├── backend/
│   ├── agent.py               # Multi-source agent: planning -> retry loop -> synthesis
│   ├── llm_client.py          # Gerbang LLM terpusat: retry, failover, klasifikasi error kuota
│   ├── chat_store.py          # Memori percakapan (checkpoint PostgreSQL manual)
│   └── main.py                # Server FastAPI: /chat /health /sources /history
├── data/
│   ├── transactions.csv       # Ekspor data 20.000 transaksi
│   ├── partner_settlement_directory.xlsx # Data operasional Excel
│   └── evaluation_report.json # Laporan hasil benchmark metrik evaluasi
├── knowledge_base/
│   ├── SOP_Penanganan_Transaksi_Gagal.pdf    # Dokumen SOP operasional
│   ├── Kebijakan_Refund_dan_Chargeback.docx  # Kebijakan refund internal
│   └── Laporan_Insiden_BCA_VA_Oktober_2024.txt # Post-mortem anomali
├── mcp_servers/
│   ├── source_registry.py     # Registry multi-sumber: fetch URL, cache TTL, DuckDB, allowlist
│   ├── analytics_server.py    # FastMCP Tools: schema, SQL postgres & multi-sumber
│   └── knowledge_server.py    # FastMCP Tool: RAG (overlap, threshold, PDF vision)
├── scripts/
│   ├── seed_data.py           # Generator data transaksi sintetis
│   ├── generate_docs_and_excel.py # Generator dokumen & populator ChromaDB
│   ├── evaluate.py            # Suite tolok ukur evaluasi RAG & SQL
│   └── smoke_test.py          # Uji cepat multi-sumber & chat store
├── static/
│   ├── index.html             # Web UI (sessionId, restore history, badge sumber)
│   └── vendor/plotly-basic.min.js # Plotly basic self-host (lazy-load, ~1MB)
├── data_sources.json          # Daftar sumber CSV/XLSX/JSON/gsheet (URL)
├── data_sources.example.json  # Contoh konfigurasi sumber
├── docker-compose.yml         # Konfigurasi container PostgreSQL 16
├── requirements.txt           # Daftar pustaka & dependensi sistem
├── run.py                     # Entrypoint runner aplikasi
└── README.md                  # Dokumentasi teknis proyek
```

---

## 🔒 Tata Kelola Keamanan (Security Governance)
1. **Prinsip Hak Akses Minimal (*Least Privilege*):** Semua engine (PostgreSQL & DuckDB) hanya menerima kueri `SELECT`/`WITH`. Mutasi data (`UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, dll), multi-statement, dan perintah berbahaya DuckDB (`ATTACH`, `COPY`, `INSTALL`, ...) ditolak guardrail terpusat.
2. **Allowlist Sumber & Tabel:** AI hanya boleh menyentuh sumber terdaftar di registry dan tabel PostgreSQL pada `PG_ALLOWED_TABLES` (default: `transactions`). Tabel riwayat chat sengaja dikecualikan dari jangkauan text-to-SQL. Skema yang dilihat LLM pun difilter allowlist.
3. **Koneksi Read-Only:** sesi PostgreSQL analitik di-set `readonly=True` di level driver, di luar guardrail regex.
4. **Karantina Data Sensitif:** Data yang disajikan ke LLM difilter dari informasi rahasia *credentials*, hanya menyajikan metadata skema dan hasil agregat.
5. **Robust Sanitization:** Penanganan tipe data numerik presisi (`Decimal`, `DateTime`) dilakukan sebelum serialisasi JSON untuk mencegah galat runtime.
6. **Anti-Halusinasi Saat Gagal:** budget retry habis -> jawaban deterministik "tidak ditemukan" tanpa panggilan LLM; kuota habis -> pesan ramah + data yang sudah diambil, bukan error mentah.

---

## 👤 Author & Architecture Highlights
- **Role:** AI Engineer
- **Project Type:** Production-Grade AI Engineering Portfolio
