"""
MCP Server: Analytics Server (Multi-Source)
Deskripsi:
  Server Model Context Protocol (MCP) untuk menyediakan tools analitik data:
  1. get_database_schema    : skema PostgreSQL (allowlist tabel) untuk acuan LLM.
  2. execute_analytics_query: eksekusi SQL SELECT ke PostgreSQL (guardrail).
  3. list_data_sources      : daftar SEMUA sumber (postgres + CSV/XLSX/JSON/Google Sheets).
  4. get_source_schema      : skema lengkap satu sumber (kolom, tipe, sampel nilai).
  5. execute_source_query   : eksekusi SQL SELECT ke sumber mana pun (guardrail seragam).

  Logika fetch/cache/DuckDB/allowlist terpusat di source_registry.py.
  Tools lama dipertahankan agar kompatibel dengan scripts/evaluate.py.
"""

import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_servers.source_registry import (
    get_pg_connection,
    execute_query,
    inspect_postgres_schema,
    inspect_source_schema,
    get_all_schemas_text,
    list_all_sources,
    get_source_status,
    PG_ALLOWED_TABLES,
)

# Load environment variables
load_dotenv()

# Kompatibilitas: main.py lama mengimpor simbol ini
get_db_connection = get_pg_connection

# Inisialisasi FastMCP Server
mcp = FastMCP("Analytics-Server")


@mcp.tool()
def get_database_schema() -> str:
    """
    Mengembalikan skema tabel PostgreSQL yang diizinkan (auto-inspect
    information_schema + sampel nilai) agar LLM dapat menyusun SQL akurat.
    """
    return inspect_postgres_schema()


@mcp.tool()
def execute_analytics_query(sql_query: str) -> dict:
    """
    Mengeksekusi query SQL analitik (Hanya SELECT) ke PostgreSQL.
    Guardrail: blocklist keyword manipulasi data + allowlist tabel + anti multi-statement.
    """
    return execute_query("postgres", sql_query)


@mcp.tool()
def list_data_sources() -> list[dict]:
    """
    Mengembalikan daftar semua sumber data yang tersedia untuk dianalisis:
    PostgreSQL, file CSV/XLSX/JSON dari URL, dan Google Sheets (per tab).
    Gunakan ini untuk memilih sumber yang paling cocok dengan pertanyaan user.
    """
    return list_all_sources()


@mcp.tool()
def get_source_schema(source_name: str) -> str:
    """
    Mengembalikan skema lengkap satu sumber data (kolom, tipe, sampel nilai,
    jumlah baris). source_name='postgres' untuk database utama.
    """
    if source_name.strip().lower() == "postgres":
        return inspect_postgres_schema()
    try:
        return inspect_source_schema(source_name)
    except Exception as e:
        return f"Sumber '{source_name}' tidak tersedia: {e}"


@mcp.tool()
def execute_source_query(source_name: str, sql_query: str) -> dict:
    """
    Mengeksekusi query SQL SELECT ke sumber data mana pun yang terdaftar
    (postgres / csv / xlsx / json / gsheet). Dialect SQL: PostgreSQL-compatible
    (DuckDB untuk file). Guardrail read-only berlaku untuk semua engine.
    """
    return execute_query(source_name, sql_query)


def get_all_sources_schema_text() -> str:
    """Helper non-tool: gabungan skema semua sumber untuk prompt planner."""
    return get_all_schemas_text()


if __name__ == "__main__":
    # Jalankan server FastMCP
    mcp.run()
