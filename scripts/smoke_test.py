"""Smoke test multi-sumber (dijalankan manual, bukan bagian suite evaluasi)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_servers.source_registry import (
    execute_query, list_all_sources, inspect_source_schema,
)


def main():
    for s in list_all_sources():
        print("SRC:", s["name"], s.get("status"), s.get("row_counts"))

    r = execute_query("data_uji", "SELECT status, COUNT(*) AS n FROM data_uji GROUP BY status")
    print("DUCKDB CSV:", r)

    r2 = execute_query(
        "ringkasan_partner",
        "SELECT payment_partner, total FROM ringkasan_partner ORDER BY total DESC LIMIT 3",
    )
    print("DUCKDB CSV2:", r2.get("data"))

    print("SCHEMA:", inspect_source_schema("data_uji")[:300])

    # Guardrail di engine DuckDB juga
    bad = execute_query("data_uji", "DROP TABLE data_uji")
    print("GUARD DUCKDB:", bad["error"][:60])

    # Filter tanggal (kolom timestamp harus datetime, bukan string)
    r3 = execute_query(
        "data_uji",
        "SELECT COUNT(*) AS n FROM data_uji WHERE timestamp >= '2024-10-01' AND timestamp <= '2024-10-31 23:59:59'",
    )
    print("DATE FILTER:", r3)

    # Chat store
    from backend import chat_store
    ok = chat_store.save_turn("smoke-sess", "halo", "hai", metadata={"intent": "GENERAL"})
    print("CHAT SAVE:", ok)
    msgs = chat_store.load_recent("smoke-sess")
    print("CHAT LOAD:", len(msgs), "pesan")
    print("HISTORY TEXT:", chat_store.format_history_for_prompt(msgs)[:120])


if __name__ == "__main__":
    main()