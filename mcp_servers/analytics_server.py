"""
MCP Server: Analytics Server (PostgreSQL)
Deskripsi:
  Server Model Context Protocol (MCP) untuk menyediakan tools analitik data transaksi:
  1. get_database_schema: Mengembalikan skema tabel & nilai sampel untuk acuan LLM.
  2. execute_analytics_query: Mengeksekusi query SQL SELECT dengan guardrail keamanan.
"""

import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "analytics_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgrespassword")

# Inisialisasi FastMCP Server
mcp = FastMCP("Analytics-Server")

def get_db_connection():
    """Membuka koneksi ke PostgreSQL."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor
    )


@mcp.tool()
def get_database_schema() -> str:
    """
    Mengembalikan skema tabel database 'transactions' dan informasi nilai unik
    agar LLM dapat menyusun query SQL yang akurat dan valid.
    """
    schema_info = """
Tabel: transactions
Deskripsi: Menyimpan riwayat transaksi multi-channel dari 1 Mei 2024 hingga 31 Oktober 2024.

Kolom-kolom:
- transaction_id (VARCHAR): ID unik transaksi (contoh: 'TRX-2024-000123')
- timestamp (TIMESTAMP): Waktu transaksi (contoh: '2024-10-18 14:30:00')
- channel (VARCHAR): Saluran pembayaran. Nilai yang valid: 'VIRTUAL_ACCOUNT', 'QRIS', 'CREDIT_CARD', 'E_WALLET'
- payment_partner (VARCHAR): Mitra bank/penyedia. Nilai yang valid: 'BCA', 'MANDIRI', 'BNI', 'BRI', 'GOPAY', 'OVO', 'DANA', 'SHOPEEPAY', 'VISA', 'MASTERCARD', 'JCB'
- merchant_category (VARCHAR): Kategori bisnis merchant. Nilai: 'E_COMMERCE', 'GAMING', 'TRAVEL', 'UTILITY', 'FOOD_BEVERAGE'
- amount (NUMERIC): Nominal transaksi dalam Rupiah (IDR)
- status (VARCHAR): Status akhir transaksi. Nilai yang valid: 'SUCCESS', 'FAILED', 'PENDING'
- error_code (VARCHAR): Kode alasan jika transaksi gagal (NULL jika sukses/pending). Nilai: 'ERR_BANK_TIMEOUT', 'ERR_INSUFFICIENT_FUNDS', 'ERR_INVALID_PIN', 'ERR_CARD_DECLINED', 'ERR_USER_CANCELLED', 'ERR_SYSTEM_DOWNTIME'
- response_time_ms (INTEGER): Durasi pemrosesan sistem dalam milidetik (normal: 150-800 ms, timeout: >15000 ms)

Panduan Penulisan Query:
- Gunakan sintaks SQL standar PostgreSQL (ANSI SQL).
- Untuk filter rentang bulan, gunakan strftime atau EXTRACT/DATE_TRUNC atau perbandingan tanggal:
  Contoh: timestamp >= '2024-10-01' AND timestamp <= '2024-10-31 23:59:59'
- Untuk menghitung Success Rate: (COUNT(*) FILTER (WHERE status = 'SUCCESS') * 100.0 / COUNT(*))
"""
    return schema_info.strip()


@mcp.tool()
def execute_analytics_query(sql_query: str) -> dict:
    """
    Mengeksekusi query SQL analitik (Hanya SELECT) ke PostgreSQL dan mengembalikan hasilnya dalam bentuk JSON/List.
    Memiliki guardrail keamanan untuk menolak perintah manipulasi data (DROP, DELETE, UPDATE, INSERT, ALTER).
    """
    cleaned_query = sql_query.strip()

    # 1. Guardrail Keamanan: Cegah SQL Injection & Manipulasi Data
    forbidden_keywords = [
        r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b",
        r"\bALTER\b", r"\bTRUNCATE\b", r"\bCREATE\b", r"\bGRANT\b", r"\bREVOKE\b"
    ]
    for pattern in forbidden_keywords:
        if re.search(pattern, cleaned_query, re.IGNORECASE):
            return {
                "success": False,
                "error": "Akses Ditolak: Hanya query analitik SELECT (Read-Only) yang diizinkan demi keamanan database.",
                "data": []
            }

    if not cleaned_query.upper().startswith("SELECT") and not cleaned_query.upper().startswith("WITH"):
        return {
            "success": False,
            "error": "Format query tidak valid. Query harus diawali dengan SELECT atau WITH.",
            "data": []
        }

    # 2. Eksekusi Query ke PostgreSQL
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(cleaned_query)
            rows = cursor.fetchall()

            # Konversi tipe data PostgreSQL (Decimal, DateTime) ke tipe Python murni (float, int, str)
            import decimal, datetime
            clean_rows = []
            for r in rows[:100]:
                d = {}
                for k, v in dict(r).items():
                    if isinstance(v, decimal.Decimal):
                        d[k] = float(v) if '.' in str(v) else int(v)
                    elif isinstance(v, (datetime.datetime, datetime.date)):
                        d[k] = v.isoformat()
                    else:
                        d[k] = v
                clean_rows.append(d)

            data_sample = clean_rows

        conn.close()

        return {
            "success": True,
            "row_count": len(rows),
            "data": data_sample,
            "truncated": len(rows) > 100
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error eksekusi SQL: {str(e)}",
            "data": []
        }


if __name__ == "__main__":
    # Jalankan server FastMCP
    mcp.run()
