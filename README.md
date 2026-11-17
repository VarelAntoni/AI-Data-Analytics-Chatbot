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
DB_PASSWORD=postgres
DB_NAME=analytics_db

GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-3.8-flash
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

## 📁 Struktur Direktori

```
ai_data_analytics_chatbot/
├── backend/
│   ├── __init__.py
│   ├── agent.py               # Two-Stage Router & Synthesizer Orchestrator
│   └── main.py                # Server FastAPI & endpoint REST API
├── data/
│   ├── transactions.csv       # Ekspor data 20.000 transaksi
│   ├── partner_settlement_directory.xlsx # Data operasional Excel
│   └── evaluation_report.json # Laporan hasil benchmark metrik evaluasi
├── knowledge_base/
│   ├── SOP_Penanganan_Transaksi_Gagal.pdf    # Dokumen SOP operasional
│   ├── Kebijakan_Refund_dan_Chargeback.docx  # Kebijakan refund internal
│   └── Laporan_Insiden_BCA_VA_Oktober_2024.txt # Post-mortem anomali
├── mcp_servers/
│   ├── analytics_server.py    # FastMCP Tool: Schema & SQL Query Runner
│   └── knowledge_server.py    # FastMCP Tool: Semantic RAG Retrieval
├── scripts/
│   ├── seed_data.py           # Generator data transaksi sintetis
│   ├── generate_docs_and_excel.py # Generator dokumen & populator ChromaDB
│   └── evaluate.py            # Suite tolok ukur evaluasi RAG & SQL
├── static/
│   └── index.html             # Antarmuka web responsif (Tailwind + Plotly)
├── docker-compose.yml         # Konfigurasi container PostgreSQL 16
├── requirements.txt           # Daftar pustaka & dependensi sistem
├── run.py                     # Entrypoint runner aplikasi
└── README.md                  # Dokumentasi teknis proyek
```

---

## 🔒 Tata Kelola Keamanan (Security Governance)
1. **Prinsip Hak Akses Minimal (*Least Privilege*):** Server analitik hanya menerima kueri `SELECT`. Segala bentuk mutasi data (`UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`) langsung ditolak di tingkat validasi AST/Regex.
2. **Karantina Data Sensitif:** Data yang disajikan ke LLM difilter dari informasi rahasia *credentials*, hanya menyajikan metadata skema dan hasil agregat.
3. **Robust Sanitization:** Penanganan tipe data numerik presisi (`Decimal`, `DateTime`) dari PostgreSQL dilakukan sebelum serialisasi JSON untuk mencegah galat runtime.

---

## 👤 Author & Architecture Highlights
- **Role:** AI Engineer
- **Project Type:** Production-Grade AI Engineering Portfolio
