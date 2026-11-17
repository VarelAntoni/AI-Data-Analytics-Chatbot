"""
Entrypoint Runner: run.py
Deskripsi:
  Menjalankan server FastAPI menggunakan Uvicorn di port 8000 dengan fitur auto-reload.
  
Cara menjalankan:
  python run.py
"""

import uvicorn

if __name__ == "__main__":
    print("🚀 Menjalankan AI-Powered Data Analytics Chatbot...")
    print("👉 Buka di browser: http://localhost:8000")
    print("📚 Dokumentasi Swagger API: http://localhost:8000/docs\n")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
