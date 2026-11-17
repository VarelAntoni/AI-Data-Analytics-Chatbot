"""
FastAPI Server: main.py
Deskripsi:
  Server REST API utama untuk AI-Powered Data Analytics Chatbot.
  Menyediakan endpoint untuk:
  - POST /api/chat   : Endpoint utama percakapan & eksekusi AI Agent
  - GET  /api/health : Status pemeriksaan kesehatan database & ChromaDB
  - GET  /api/schema : Inspeksi skema tabel PostgreSQL
  - Melayani file web statis (HTML/JS/CSS) di root URL (/)
"""

import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Import agent runner
from backend.agent import run_agent_turn
from mcp_servers.analytics_server import get_db_connection, get_database_schema
from mcp_servers.knowledge_server import collection

load_dotenv()

# Inisialisasi FastAPI App dengan metadata profesional untuk Swagger UI (/docs)
app = FastAPI(
    title="AI-Powered Data Analytics Chatbot",
    description="REST API untuk Analisis Transaksi Terstruktur & Penelusuran Dokumen Operasional (Enterprise Analytics & RAG System)",
    version="1.0.0"
)

# Aktifkan CORS agar frontend dapat mengakses API secara aman
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Skema Pydantic untuk Request & Response ===
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default_session"


class DocumentCitation(BaseModel):
    source: Optional[str] = "Unknown"
    reference: Optional[str] = "N/A"
    snippet: Optional[str] = ""


class ChatResponse(BaseModel):
    answer: str
    intent: str
    executed_sql: Optional[str] = None
    sql_data: Optional[List[Dict[str, Any]]] = None
    chart_config: Optional[Dict[str, Any]] = None
    cited_documents: List[DocumentCitation] = []


# === API Endpoints ===

@app.get("/api/health", summary="Health Check Status Sistem")
def health_check():
    """Memeriksa kesiapan Database PostgreSQL, ChromaDB, dan Kunci API Gemini."""
    # 1. Cek PostgreSQL
    db_status = "Disconnected"
    total_transactions = 0
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM transactions;")
            total_transactions = cur.fetchone()["count"]
        conn.close()
        db_status = "Connected"
    except Exception as e:
        db_status = f"Error: {str(e)}"

    # 2. Cek ChromaDB
    chroma_status = "Ready"
    doc_count = 0
    try:
        doc_count = collection.count()
    except Exception as e:
        chroma_status = f"Error: {str(e)}"

    # 3. Cek API Key
    has_api_key = bool(os.getenv("GEMINI_API_KEY", "").strip())

    return {
        "status": "healthy" if db_status == "Connected" else "degraded",
        "database": {
            "status": db_status,
            "engine": "PostgreSQL (Docker)",
            "total_transactions": total_transactions
        },
        "vector_store": {
            "status": chroma_status,
            "engine": "ChromaDB (Local)",
            "indexed_chunks": doc_count
        },
        "gemini_api_configured": has_api_key
    }


@app.get("/api/test-agent", summary="Test Agent Models and Tools")
def test_agent_endpoint():
    """Menguji pemanggilan model secara langsung untuk mendiagnosis error."""
    from backend.agent import client
    import traceback

    if not client:
        return {"error": "Client belum terinisialisasi. Cek GEMINI_API_KEY di .env"}

    results = {}
    
    # 1. Test Interactions API dengan gemini-3.8-flash
    try:
        interaction = client.interactions.create(
            model="gemini-3.8-flash",
            input="Katakan 'Halo' saja untuk tes koneksi."
        )
        results["interactions_gemini-3.8-flash"] = {
            "status": "SUCCESS",
            "output": getattr(interaction, "output_text", str(interaction))
        }
    except Exception as e:
        results["interactions_gemini-3.8-flash"] = {"status": "FAILED", "error": str(e)}

    # 2. Test generate_content dengan gemini-3.8-flash
    try:
        resp = client.models.generate_content(
            model="gemini-3.8-flash",
            contents="Katakan 'Halo' saja untuk tes koneksi."
        )
        results["generate_content_gemini-3.8-flash"] = {
            "status": "SUCCESS",
            "text": resp.text
        }
    except Exception as e:
        results["generate_content_gemini-3.8-flash"] = {"status": "FAILED", "error": str(e)}

    return results


@app.post("/api/chat", summary="Kirim Pesan ke AI Analytics Chatbot")
def chat_endpoint(req: ChatRequest):
    """
    Endpoint utama percakapan.
    Menerima pertanyaan analitis, mengorkestrasi Text-to-SQL atau Document RAG via MCP,
    dan mengembalikan jawaban terstruktur beserta metadata SQL dan dokumen.
    """
    try:
        if not req.message.strip():
            raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

        result = run_agent_turn(user_message=req.message)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "answer": f"Terjadi kesalahan saat memproses data: {str(e)}",
            "intent": "ERROR",
            "executed_sql": None,
            "sql_data": None,
            "chart_config": None,
            "cited_documents": []
        }


# === Mount Web UI Statis ===
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount folder static untuk file asset jika ada
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", summary="Akses Tampilan Web Chatbot")
def serve_index():
    """Menampilkan halaman utama antarmuka chat pengguna."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": "AI-Powered Data Analytics Chatbot API is running.",
        "documentation": "/docs",
        "health_check": "/api/health"
    }
