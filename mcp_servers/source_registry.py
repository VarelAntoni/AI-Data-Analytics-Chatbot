"""
Source Registry: Multi-Source Data Layer
Deskripsi:
  Registry terpusat untuk semua sumber data analitik chatbot:
  1. PostgreSQL  : database transaksi existing (via psycopg2, read-only).
  2. CSV/XLSX/JSON dari URL : di-fetch, di-cache (TTL), lalu di-query via DuckDB.
  3. Google Sheets (publik) : discovery semua tab otomatis, tiap tab = tabel DuckDB.

  Semua sumber di-inspeksi skemanya secara otomatis (kolom, tipe, sampel nilai)
  agar LLM Planner dapat memilih sumber & menulis SQL yang akurat.

  Keamanan berlapis:
  - Allowlist sumber  : hanya sumber terdaftar di data_sources.json + 'postgres'.
  - Allowlist tabel   : query postgres hanya boleh menyentuh tabel yang diizinkan.
  - Guardrail SQL     : hanya SELECT/WITH, blocklist keyword manipulasi data.

Konfigurasi:
  data_sources.json (root proyek):
    [{"name": "penjualan", "type": "csv", "url": "https://.../file.csv"},
     {"name": "laporan", "type": "gsheet", "url": "https://docs.google.com/spreadsheets/d/<ID>/edit"}]
  .env:
    DATA_SOURCE_REFRESH_SECONDS=300   (TTL cache fetch)
    PG_ALLOWED_TABLES=transactions    (allowlist tabel postgres, pisahkan koma)
"""

import os
import io
import re
import json
import time
import threading
from typing import Dict, Any, List, Optional

import requests
import pandas as pd
import duckdb
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_SOURCES_FILE = os.path.join(ROOT_DIR, "data_sources.json")

# Konfigurasi PostgreSQL (sama dengan analytics_server)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "analytics_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgrespassword")

REFRESH_SECONDS = int(os.getenv("DATA_SOURCE_REFRESH_SECONDS", "300"))
PG_ALLOWED_TABLES = [
    t.strip() for t in os.getenv("PG_ALLOWED_TABLES", "transactions").split(",") if t.strip()
]
MAX_ROWS_RETURNED = 100
FETCH_TIMEOUT = 30

_lock = threading.Lock()
# Cache per sumber: {name: {"loaded_at": ts, "tables": {table_name: DataFrame},
#                          "status": "ok"|"degraded"|"error", "error": str|None,
#                          "type": str, "url": str}}
_sources_cache: Dict[str, Dict[str, Any]] = {}


# ============================================================
# Utilitas
# ============================================================

def normalize_name(raw: str) -> str:
    """Normalisasi nama sumber/tab menjadi identifier SQL aman (snake_case)."""
    name = re.sub(r"[^0-9a-zA-Z]+", "_", str(raw).strip().lower()).strip("_")
    if not name:
        name = "sumber"
    if name[0].isdigit():
        name = "t_" + name
    return name


def check_sql_guardrail(sql_query: str) -> Optional[str]:
    """
    Guardrail SQL terpusat untuk SEMUA engine.
    Return pesan error jika ditolak, None jika aman.
    """
    cleaned = (sql_query or "").strip()
    if not cleaned:
        return "Query SQL kosong."

    forbidden = [
        r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b",
        r"\bALTER\b", r"\bTRUNCATE\b", r"\bCREATE\b", r"\bGRANT\b",
        r"\bREVOKE\b", r"\bATTACH\b", r"\bCOPY\b", r"\bEXPORT\b",
        r"\bIMPORT\b", r"\bINSTALL\b", r"\bLOAD\b", r"\bPRAGMA\b",
        r"\bCALL\b", r"\bSET\b", r"\bVACUUM\b",
    ]
    for pattern in forbidden:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return ("Akses Ditolak: Hanya query analitik SELECT (Read-Only) "
                    "yang diizinkan demi keamanan database.")

    upper = cleaned.upper()
    if not upper.startswith("SELECT") and not upper.startswith("WITH"):
        return "Format query tidak valid. Query harus diawali dengan SELECT atau WITH."

    # Tolak multi-statement (cegah 'SELECT 1; SELECT ...' penyelundupan)
    stripped = re.sub(r"'[^']*'", "", cleaned)  # abaikan ';' di dalam string literal
    if ";" in stripped.rstrip().rstrip(";"):
        return "Akses Ditolak: Multi-statement SQL tidak diizinkan."

    return None


def _check_pg_table_allowlist(sql_query: str) -> Optional[str]:
    """Pastikan query postgres hanya menyentuh tabel yang diizinkan."""
    tables_referenced = re.findall(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", sql_query, re.IGNORECASE
    )
    allowed_lower = {t.lower() for t in PG_ALLOWED_TABLES}
    for t in tables_referenced:
        base = t.split(".")[-1].lower()
        # CTE (WITH ... AS) dianggap aman: nama CTE tidak ada di information_schema,
        # tapi kita hanya izinkan jika nama itu didefinisikan sebagai CTE di query.
        cte_names = {
            m.lower() for m in re.findall(
                r"\bWITH\s+(?:RECURSIVE\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(",
                sql_query, re.IGNORECASE)
        }
        cte_names |= {
            m.lower() for m in re.findall(
                r",\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", sql_query, re.IGNORECASE)
        }
        if base not in allowed_lower and base not in cte_names:
            return (f"Akses Ditolak: Tabel '{t}' tidak termasuk sumber yang diizinkan. "
                    f"Tabel yang boleh diakses: {', '.join(PG_ALLOWED_TABLES)}.")
    return None


def _clean_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalisasi tipe (Decimal/datetime/Timestamp) ke tipe JSON-friendly."""
    import decimal
    import datetime

    clean = []
    for r in rows[:MAX_ROWS_RETURNED]:
        d = {}
        for k, v in dict(r).items():
            if isinstance(v, decimal.Decimal):
                d[k] = float(v) if "." in str(v) else int(v)
            elif isinstance(v, (datetime.datetime, datetime.date)):
                d[k] = v.isoformat()
            elif pd.isna(v) if not isinstance(v, (list, dict)) else False:
                d[k] = None
            else:
                d[k] = v
        clean.append(d)
    return clean


def get_pg_connection():
    """Koneksi PostgreSQL read-only untuk jalur analitik."""
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
        connect_timeout=5,
    )


# ============================================================
# Konfigurasi & Fetch Sumber File / Google Sheets
# ============================================================

def load_source_config() -> List[Dict[str, Any]]:
    """Baca data_sources.json. Return [] jika tidak ada / rusak."""
    if not os.path.exists(DATA_SOURCES_FILE):
        return []
    try:
        with open(DATA_SOURCES_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        sources = cfg.get("sources", cfg) if isinstance(cfg, dict) else cfg
        valid = []
        for s in sources:
            if not isinstance(s, dict):
                continue
            if s.get("name") and s.get("url") and s.get("type") in ("csv", "xlsx", "json", "gsheet"):
                valid.append(s)
        return valid
    except Exception as e:
        print(f"⚠️ Gagal membaca data_sources.json: {e}")
        return []


def _extract_gsheet_id(url: str) -> Optional[str]:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", url.strip()):
        return url.strip()
    return None


def _discover_gsheet_tabs(sheet_id: str) -> List[Dict[str, str]]:
    """
    Discovery tab Google Sheets publik tanpa API key:
    parse halaman /edit untuk daftar {name, gid}.
    Fallback: tab pertama gid=0.
    """
    tabs: List[Dict[str, str]] = []
    try:
        resp = requests.get(
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        html = resp.text
        # Pola umum di halaman sheets: {"name":"TabName",...,"gid":"123"} atau
        # struktur items dengan pasangan name & gid berdekatan.
        pairs = re.findall(
            r'\{\s*"name"\s*:\s*"((?:[^"\\]|\\.)*)"[^{}]*?"gid"\s*:\s*"?(\d+)"?',
            html,
        )
        seen = set()
        for name, gid in pairs:
            if gid in seen:
                continue
            seen.add(gid)
            try:
                name = json.loads(f'"{name}"')
            except Exception:
                pass
            tabs.append({"name": name, "gid": gid})
    except Exception as e:
        print(f"⚠️ Discovery tab Google Sheets gagal ({e}); fallback gid=0.")

    if not tabs:
        tabs = [{"name": "sheet1", "gid": "0"}]
    return tabs


def _fetch_dataframe(url: str, file_type: str) -> pd.DataFrame:
    """Fetch URL dan parse menjadi DataFrame sesuai tipe."""
    resp = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    content = resp.content

    if file_type == "csv":
        df = pd.read_csv(io.BytesIO(content))
    elif file_type == "xlsx":
        df = pd.read_excel(io.BytesIO(content))
    elif file_type == "json":
        text = content.decode("utf-8-sig")
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                # cari array pertama di dalam object
                arr = next((v for v in data.values() if isinstance(v, list)), None)
                data = arr if arr is not None else [data]
            df = pd.DataFrame(data)
        except json.JSONDecodeError:
            # fallback JSON Lines
            df = pd.read_json(io.StringIO(text), lines=True)
    else:
        raise ValueError(f"Tipe file tidak dikenal: {file_type}")

    df.columns = [normalize_name(c) for c in df.columns]
    # Tebak kolom waktu & numerik agar SQL tanggal berfungsi.
    # pandas 3.x memakai dtype 'str' (bukan object) untuk kolom teks.
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_datetime64_any_dtype(df[col]):
            sample = df[col].dropna().astype(str).head(5)
            if len(sample) and sample.str.match(r"^\d{4}-\d{2}-\d{2}").all():
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _refresh_source(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch + parse satu sumber menjadi dict {table_name: DataFrame}."""
    name = normalize_name(cfg["name"])
    stype = cfg["type"]
    url = cfg["url"]
    tables: Dict[str, pd.DataFrame] = {}

    if stype == "gsheet":
        sheet_id = _extract_gsheet_id(url)
        if not sheet_id:
            raise ValueError(f"URL Google Sheets tidak valid: {url}")
        tabs = cfg.get("tabs") or _discover_gsheet_tabs(sheet_id)
        errors = []
        for tab in tabs:
            tab_name = normalize_name(tab["name"])
            gid = str(tab.get("gid", "0"))
            csv_url = (f"https://docs.google.com/spreadsheets/d/{sheet_id}"
                       f"/export?format=csv&gid={gid}")
            try:
                tables[tab_name] = _fetch_dataframe(csv_url, "csv")
            except Exception as e:
                errors.append(f"tab '{tab['name']}': {e}")
        if not tables:
            raise ValueError("Semua tab gagal di-fetch: " + "; ".join(errors))
        if errors:
            print(f"⚠️ Sumber '{name}' degraded: {'; '.join(errors)}")
    else:
        tables[name] = _fetch_dataframe(url, stype)

    return tables


def _get_source(name: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Ambil sumber dari cache; refresh jika TTL habis.
    Stale-on-error: jika refresh gagal tapi cache lama ada, pakai cache lama.
    """
    with _lock:
        entry = _sources_cache.get(name)
        now = time.time()
        if entry and not force_refresh and now - entry["loaded_at"] < REFRESH_SECONDS:
            return entry

        cfg = next((s for s in load_source_config()
                    if normalize_name(s["name"]) == name), None)
        if cfg is None:
            raise KeyError(f"Sumber '{name}' tidak terdaftar di data_sources.json.")

        try:
            tables = _refresh_source(cfg)
            entry = {
                "loaded_at": now, "tables": tables, "status": "ok",
                "error": None, "type": cfg["type"], "url": cfg["url"],
                "description": cfg.get("description", ""),
            }
            _sources_cache[name] = entry
            return entry
        except Exception as e:
            if entry and entry.get("tables"):
                entry["status"] = "degraded"
                entry["error"] = f"Refresh gagal, memakai cache lama: {e}"
                print(f"⚠️ {entry['error']} (sumber: {name})")
                return entry
            entry = {
                "loaded_at": now, "tables": {}, "status": "error",
                "error": str(e), "type": cfg["type"], "url": cfg["url"],
                "description": cfg.get("description", ""),
            }
            _sources_cache[name] = entry
            raise


# ============================================================
# Inspeksi Skema (untuk LLM Planner)
# ============================================================

def _describe_dataframe(df: pd.DataFrame, table_name: str) -> str:
    lines = [f"Tabel: {table_name} ({len(df)} baris)"]
    for col in df.columns:
        dtype = str(df[col].dtype)
        sample_vals = df[col].dropna().unique()[:6]
        sample_str = ", ".join(repr(v) for v in sample_vals)
        if len(sample_str) > 160:
            sample_str = sample_str[:160] + "..."
        lines.append(f"- {col} ({dtype}): contoh nilai: {sample_str}")
    return "\n".join(lines)


def inspect_postgres_schema() -> str:
    """Skema postgres dari information_schema, terfilter allowlist tabel."""
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ANY(%s)
                ORDER BY table_name, ordinal_position
                """,
                (PG_ALLOWED_TABLES,),
            )
            cols = cur.fetchall()

            parts = []
            for table in PG_ALLOWED_TABLES:
                tcols = [c for c in cols if c["table_name"] == table]
                if not tcols:
                    continue
                cur.execute(f'SELECT COUNT(*) AS n FROM "{table}"')
                n = cur.fetchone()["n"]
                lines = [f"Tabel: {table} ({n} baris)"]
                for c in tcols:
                    cur.execute(
                        f'SELECT DISTINCT "{c["column_name"]}" FROM "{table}" '
                        f'WHERE "{c["column_name"]}" IS NOT NULL LIMIT 6'
                    )
                    samples = [str(r[c["column_name"]]) for r in cur.fetchall()]
                    sample_str = ", ".join(samples)
                    if len(sample_str) > 160:
                        sample_str = sample_str[:160] + "..."
                    lines.append(f'- {c["column_name"]} ({c["data_type"]}): contoh: {sample_str}')
                parts.append("\n".join(lines))
        conn.close()
        if parts:
            return "\n\n".join(parts)
    except Exception as e:
        print(f"⚠️ Inspeksi skema PostgreSQL gagal: {e}")
    return "Tabel: transactions (skema tidak tersedia saat ini, database mungkin belum aktif)"


def inspect_source_schema(name: str) -> str:
    """Skema satu sumber file/gsheet (semua tabelnya)."""
    entry = _get_source(name)
    parts = [_describe_dataframe(df, tname) for tname, df in entry["tables"].items()]
    return "\n\n".join(parts)


def list_all_sources() -> List[Dict[str, Any]]:
    """Daftar semua sumber terdaftar beserta statusnya (untuk health & UI)."""
    result = [{
        "name": "postgres",
        "type": "postgresql",
        "description": "Database transaksi utama (PostgreSQL Docker)",
        "tables": PG_ALLOWED_TABLES,
    }]
    for cfg in load_source_config():
        name = normalize_name(cfg["name"])
        item = {
            "name": name,
            "type": cfg["type"],
            "url": cfg["url"],
            "description": cfg.get("description", ""),
            "tables": [],
            "status": "not_loaded",
        }
        try:
            entry = _get_source(name)
            item["tables"] = list(entry["tables"].keys())
            item["status"] = entry["status"]
            item["error"] = entry.get("error")
            item["row_counts"] = {t: len(df) for t, df in entry["tables"].items()}
        except Exception as e:
            item["status"] = "error"
            item["error"] = str(e)
        result.append(item)
    return result


def get_all_schemas_text() -> str:
    """Gabungan skema semua sumber untuk prompt planner."""
    parts = [f"### Sumber: postgres (PostgreSQL)\n{inspect_postgres_schema()}"]
    for cfg in load_source_config():
        name = normalize_name(cfg["name"])
        try:
            schema = inspect_source_schema(name)
            desc = cfg.get("description", "")
            header = f"### Sumber: {name} ({cfg['type']})"
            if desc:
                header += f" - {desc}"
            parts.append(f"{header}\n{schema}")
        except Exception as e:
            parts.append(f"### Sumber: {name} ({cfg['type']}) - TIDAK TERSEDIA: {e}")
    return "\n\n".join(parts)


# ============================================================
# Eksekusi Query (dispatch per engine)
# ============================================================

def _execute_postgres(sql_query: str) -> Dict[str, Any]:
    allow_err = _check_pg_table_allowlist(sql_query)
    if allow_err:
        return {"success": False, "error": allow_err, "data": []}
    try:
        conn = get_pg_connection()
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(sql_query)
            rows = cur.fetchall()
        conn.close()
        return {
            "success": True,
            "row_count": len(rows),
            "data": _clean_rows(rows),
            "truncated": len(rows) > MAX_ROWS_RETURNED,
        }
    except Exception as e:
        return {"success": False, "error": f"Error eksekusi SQL: {e}", "data": []}


def _execute_duckdb(name: str, sql_query: str) -> Dict[str, Any]:
    try:
        entry = _get_source(name)
    except Exception as e:
        return {"success": False, "error": f"Sumber tidak tersedia: {e}", "data": []}

    try:
        conn = duckdb.connect()
        for tname, df in entry["tables"].items():
            conn.register(f"_df_{tname}", df)
            conn.execute(f'CREATE VIEW "{tname}" AS SELECT * FROM "_df_{tname}"')
        result = conn.execute(sql_query)
        columns = [d[0] for d in result.description]
        rows = result.fetchall()
        conn.close()
        dict_rows = [dict(zip(columns, r)) for r in rows]
        return {
            "success": True,
            "row_count": len(dict_rows),
            "data": _clean_rows(dict_rows),
            "truncated": len(dict_rows) > MAX_ROWS_RETURNED,
        }
    except Exception as e:
        return {"success": False, "error": f"Error eksekusi SQL (DuckDB): {e}", "data": []}


def execute_query(source_name: str, sql_query: str) -> Dict[str, Any]:
    """
    Eksekusi SQL ke sumber mana pun dengan guardrail seragam.
    Return: {success, data, row_count, truncated} atau {success: False, error, data: []}
    """
    guard_err = check_sql_guardrail(sql_query)
    if guard_err:
        return {"success": False, "error": guard_err, "data": []}

    name = normalize_name(source_name)
    if name == "postgres":
        return _execute_postgres(sql_query)

    registered = {normalize_name(s["name"]) for s in load_source_config()}
    if name not in registered:
        return {
            "success": False,
            "error": (f"Akses Ditolak: Sumber '{source_name}' tidak terdaftar. "
                      f"Sumber tersedia: postgres, {', '.join(sorted(registered)) or '(tidak ada file)'}."),
            "data": [],
        }
    return _execute_duckdb(name, sql_query)


def get_source_status() -> Dict[str, Any]:
    """Status ringkas semua sumber untuk /api/health."""
    sources = list_all_sources()
    pg_ok = False
    total_rows = 0
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) AS n FROM "{PG_ALLOWED_TABLES[0]}"')
            total_rows = cur.fetchone()["n"]
        conn.close()
        pg_ok = True
    except Exception:
        pass

    for s in sources:
        if s["name"] == "postgres":
            s["status"] = "ok" if pg_ok else "error"
            s["row_counts"] = {PG_ALLOWED_TABLES[0]: total_rows} if pg_ok else {}

    healthy = pg_ok or any(s.get("status") == "ok" for s in sources if s["name"] != "postgres")
    return {"healthy": healthy, "postgres_connected": pg_ok, "sources": sources}