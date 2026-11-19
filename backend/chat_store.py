"""
Chat Store: chat_store.py
Deskripsi:
  Memori percakapan persisten di PostgreSQL (pola checkpoint manual,
  tanpa LangGraph). Tabel:
  - chat_sessions : session_id, created_at, last_active
  - chat_messages : role, content, metadata JSONB (intent, sql, sources, sitasi)

  Jalur ini memakai koneksi TULIS terpisah dari jalur analitik read-only.
  Jika PostgreSQL mati, semua fungsi gagal dengan anggun (return kosong /
  no-op + warning) sehingga chatbot tetap bisa menjawab tanpa history.
"""

import os
import json
from typing import Dict, Any, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "analytics_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgrespassword")

HISTORY_WINDOW = 6          # jumlah pesan terakhir yang masuk prompt
ASSISTANT_SNIPPET = 500     # ringkasan jawaban assistant untuk prompt

_initialized = False
_warned = False


def _conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=RealDictCursor, connect_timeout=3,
    )


def init_store() -> bool:
    """Buat tabel jika belum ada. Return True jika store siap dipakai."""
    global _initialized, _warned
    if _initialized:
        return True
    try:
        conn = _conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id VARCHAR(64) PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_active TIMESTAMP NOT NULL DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id BIGSERIAL PRIMARY KEY,
                    session_id VARCHAR(64) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                    role VARCHAR(16) NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages(session_id, created_at);
            """)
        conn.close()
        _initialized = True
        return True
    except Exception as e:
        if not _warned:
            print(f"⚠️ Chat history nonaktif (PostgreSQL tidak tersedia): {e}")
            _warned = True
        return False


def save_turn(session_id: str, user_message: str, assistant_answer: str,
              metadata: Optional[Dict[str, Any]] = None) -> bool:
    """Simpan satu giliran percakapan (user + assistant). No-op jika store mati."""
    if not session_id or not init_store():
        return False
    try:
        conn = _conn()
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_sessions (session_id) VALUES (%s)
                ON CONFLICT (session_id) DO UPDATE SET last_active = NOW()
            """, (session_id,))
            cur.execute(
                "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, 'user', %s)",
                (session_id, user_message),
            )
            cur.execute(
                "INSERT INTO chat_messages (session_id, role, content, metadata) VALUES (%s, 'assistant', %s, %s)",
                (session_id, assistant_answer, Json(metadata or {})),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ Gagal menyimpan history chat: {e}")
        return False


def load_recent(session_id: str, limit: int = HISTORY_WINDOW) -> List[Dict[str, Any]]:
    """Ambil N pesan terakhir untuk sesi (urut kronologis). [] jika store mati."""
    if not session_id or not init_store():
        return []
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, content, metadata FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
            """, (session_id, limit))
            rows = cur.fetchall()
        conn.close()
        return list(reversed(rows))
    except Exception as e:
        print(f"⚠️ Gagal memuat history chat: {e}")
        return []


def get_session_messages(session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Semua pesan sesi untuk restore UI (urut kronologis)."""
    if not session_id or not init_store():
        return []
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, content, metadata, created_at FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at ASC, id ASC
                LIMIT %s
            """, (session_id, limit))
            rows = cur.fetchall()
        conn.close()
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return rows
    except Exception as e:
        print(f"⚠️ Gagal memuat sesi chat: {e}")
        return []


def format_history_for_prompt(messages: List[Dict[str, Any]]) -> str:
    """Ringkas history menjadi blok teks untuk prompt (hemat token)."""
    if not messages:
        return ""
    lines = []
    for m in messages:
        role = m.get("role", "")
        content = str(m.get("content", ""))
        if role == "assistant":
            content = content[:ASSISTANT_SNIPPET]
            meta = m.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            sql = meta.get("executed_sql")
            if sql:
                content += f"\n  [SQL yang dipakai: {str(sql)[:200]}]"
            lines.append(f"ASSISTANT: {content}")
        else:
            lines.append(f"USER: {content}")
    return "\n".join(lines)