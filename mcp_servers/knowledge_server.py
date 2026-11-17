"""
MCP Server: Knowledge Server (Document RAG)
Deskripsi:
  Server Model Context Protocol (MCP) untuk pencarian semantik dokumen tidak terstruktur:
  - Membaca dan mengindeks file PDF, DOCX, dan TXT dari folder knowledge_base/
  - Menyimpan representasi vektor ke dalam ChromaDB (Local Vector Store)
  - Menyediakan tool: search_knowledge_base(query, top_k) untuk dipanggil oleh AI.
"""

import os
import glob
from pypdf import PdfReader
from docx import Document as DocxReader
import chromadb
from chromadb.utils import embedding_functions
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

# Inisialisasi FastMCP Server
mcp = FastMCP("Knowledge-Server")

# Path folder penyimpanan dokumen & vector database
KNOWLEDGE_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base")
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")

# Inisialisasi Persistent Client ChromaDB
chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

# Gunakan Default Embedding Function bawaan ChromaDB (all-MiniLM-L6-v2)
# Berjalan 100% lokal tanpa perlu kuota API
default_ef = embedding_functions.DefaultEmbeddingFunction()

collection = chroma_client.get_or_create_collection(
    name="operational_documents",
    embedding_function=default_ef
)


def extract_text_from_pdf(file_path: str) -> list[dict]:
    """Ekstraksi teks dari file PDF per halaman."""
    chunks = []
    try:
        reader = PdfReader(file_path)
        file_name = os.path.basename(file_path)
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                chunks.append({
                    "text": text,
                    "metadata": {
                        "source": file_name,
                        "file_type": "PDF",
                        "page": page_num
                    }
                })
    except Exception as e:
        print(f"❌ Gagal membaca PDF {file_path}: {e}")
    return chunks


def extract_text_from_docx(file_path: str) -> list[dict]:
    """Ekstraksi teks dari file DOCX per seksi/paragraf besar."""
    chunks = []
    try:
        doc = DocxReader(file_path)
        file_name = os.path.basename(file_path)
        full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

        # Potong menjadi beberapa chunk per 500 karakter
        chunk_size = 500
        for idx, i in enumerate(range(0, len(full_text), chunk_size), start=1):
            chunk_text = full_text[i:i + chunk_size].strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "source": file_name,
                        "file_type": "DOCX",
                        "section": f"Bagian {idx}"
                    }
                })
    except Exception as e:
        print(f"❌ Gagal membaca DOCX {file_path}: {e}")
    return chunks


def extract_text_from_txt(file_path: str) -> list[dict]:
    """Ekstraksi teks dari file TXT dan membaginya per bab/seksi."""
    chunks = []
    try:
        file_name = os.path.basename(file_path)
        with open(file_path, mode="r", encoding="utf-8") as f:
            content = f.read()

        # Bagi berdasarkan garis pembatas dokumen
        sections = [s.strip() for s in content.split("--------------------------------------------------------------------------------") if s.strip()]
        for idx, sec in enumerate(sections, start=1):
            chunks.append({
                "text": sec,
                "metadata": {
                    "source": file_name,
                    "file_type": "TXT",
                    "section": f"Seksi {idx}"
                }
            })
    except Exception as e:
        print(f"❌ Gagal membaca TXT {file_path}: {e}")
    return chunks


def index_knowledge_base():
    """Membaca semua file dokumen di folder knowledge_base dan menyimpannya ke ChromaDB."""
    all_chunks = []

    # 1. Baca semua PDF
    for pdf_file in glob.glob(os.path.join(KNOWLEDGE_BASE_DIR, "*.pdf")):
        all_chunks.extend(extract_text_from_pdf(pdf_file))

    # 2. Baca semua DOCX
    for docx_file in glob.glob(os.path.join(KNOWLEDGE_BASE_DIR, "*.docx")):
        all_chunks.extend(extract_text_from_docx(docx_file))

    # 3. Baca semua TXT
    for txt_file in glob.glob(os.path.join(KNOWLEDGE_BASE_DIR, "*.txt")):
        all_chunks.extend(extract_text_from_txt(txt_file))

    if not all_chunks:
        print("⚠️ Tidak ada dokumen yang ditemukan untuk diindeks.")
        return

    # Siapkan data untuk dimasukkan ke ChromaDB
    documents = [c["text"] for c in all_chunks]
    metadatas = [c["metadata"] for c in all_chunks]
    ids = [f"doc_{idx}" for idx in range(len(all_chunks))]

    # Masukkan ke ChromaDB (upsert untuk menghindari duplikasi)
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )
    print(f"✅ Berhasil mengindeks {len(all_chunks)} potongan teks dokumen ke ChromaDB.")


@mcp.tool()
def search_knowledge_base(query: str) -> list[dict]:
    """
    Melakukan pencarian semantik (Semantic Search) pada dokumen SOP, kebijakan refund,
    dan laporan insiden untuk menjawab pertanyaan terkait prosedur dan investigasi masalah.
    """
    top_k = 3
    try:
        # Jika collection masih kosong, lakukan auto-index
        if collection.count() == 0:
            index_knowledge_base()

        results = collection.query(
            query_texts=[query],
            n_results=top_k
        )

        formatted_results = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if "metadatas" in results else [{}] * len(docs)
            distances = results["distances"][0] if "distances" in results else [0.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, distances):
                formatted_results.append({
                    "content": doc,
                    "source": meta.get("source", "Unknown"),
                    "file_type": meta.get("file_type", "Unknown"),
                    "reference": meta.get("page") or meta.get("section") or "General",
                    "relevance_distance": round(float(dist), 4)
                })

        return formatted_results

    except Exception as e:
        return [{
            "content": f"Gagal melakukan pencarian dokumen: {str(e)}",
            "source": "Error",
            "file_type": "None",
            "reference": "N/A",
            "relevance_distance": 1.0
        }]


# Otomatis lakukan indeks awal saat file ini dijalankan atau diimpor
index_knowledge_base()

if __name__ == "__main__":
    mcp.run()
