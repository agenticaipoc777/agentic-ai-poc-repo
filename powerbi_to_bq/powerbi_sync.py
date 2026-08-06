"""
Syncs an ENTIRE Power BI semantic model into BigQuery -- discovers
every table in the model automatically (via INFO.TABLES()) and loads
each one, instead of requiring one hardcoded table name.

Still the same "polling, not true real-time CDC" pattern as
everything else in this project -- see powerbi_client.py's module
docstring for why that's inherent to Power BI semantic models, not a
limitation of this script specifically.

KEY COLUMN NOTE: since this now discovers tables dynamically, there's
no single hardcoded PBI_KEY_COLUMNS that could possibly be right for
every table -- each table has its own unique-key column(s), and this
script can't know those without either (a) you telling it per table,
or (b) a full-refresh strategy that doesn't need a key at all. This
version uses a full-refresh (WRITE_TRUNCATE) load for every table by
default -- simpler, always correct, but re-loads the whole table
every run instead of an incremental upsert. If you want true
per-table upsert/MERGE behavior (matching what sync_engine.py in
bigquery_streaming/ does), you need to supply a per-table key mapping
-- see PBI_TABLE_KEYS below for how to opt specific tables into that.

Usage:
    python powerbi_sync.py
"""
import os
import time
import json
from dotenv import load_dotenv

from powerbi_client import execute_dax_query, list_model_tables
from bq_loader import load_dataframe_to_bigquery, full_refresh_load

load_dotenv()

WORKSPACE_ID = os.environ.get("PBI_WORKSPACE_ID", "")
DATASET_ID = os.environ.get("PBI_DATASET_ID", "")

TARGET_DATASET = os.environ.get("PBI_TARGET_DATASET", "analytics_v3")
TABLE_PREFIX = os.environ.get("PBI_TARGET_TABLE_PREFIX", "pbi_")

# Optional: JSON mapping of {"TableName": "KeyColumnName"} for any
# table you want upserted (MERGE) instead of full-refreshed. Example:
#   $env:PBI_TABLE_KEYS = '{"Sales": "OrderID", "Customers": "CustomerID"}'
# Tables NOT listed here are full-refreshed (WRITE_TRUNCATE) every run.
TABLE_KEYS = json.loads(os.environ.get("PBI_TABLE_KEYS", "{}"))

# Optional: comma-separated list to sync only specific tables instead
# of the whole model, e.g. "Sales,Customers". Leave unset to sync
# every table discovered in the model.
TABLE_FILTER = [
    t.strip() for t in os.environ.get("PBI_TABLE_FILTER", "").split(",") if t.strip()
]

POLL_INTERVAL_SECONDS = int(os.environ.get("PBI_POLL_INTERVAL_SECONDS", "300"))
RUN_ONCE = os.environ.get("PBI_RUN_ONCE", "false").lower() == "true"


def sync_table(table_name: str):
    bq_table_name = TABLE_PREFIX + "".join(
        c if c.isalnum() or c == "_" else "_" for c in table_name
    )
    dax_query = f"EVALUATE '{table_name}'"
    print(f"  [{table_name}] querying...")
    df = execute_dax_query(WORKSPACE_ID, DATASET_ID, dax_query)
    print(f"  [{table_name}] {len(df)} rows, {len(df.columns)} columns")

    if df.empty:
        print(f"  [{table_name}] empty result, skipping")
        return

    if table_name in TABLE_KEYS:
        key_col = TABLE_KEYS[table_name]
        result = load_dataframe_to_bigquery(
            df, TARGET_DATASET, bq_table_name, [key_col]
        )
        if result.get("target_table_created"):
            print(f"  [{table_name}] target table created, loaded {result['rows_loaded']} rows")
        else:
            stats = result["dml_stats"]
            print(f"  [{table_name}] MERGE: inserted={stats['inserted']} updated={stats['updated']}")
    else:
        rows_loaded = full_refresh_load(df, TARGET_DATASET, bq_table_name)
        print(f"  [{table_name}] full refresh: {rows_loaded} rows")


def run_once():
    if not (WORKSPACE_ID and DATASET_ID):
        raise RuntimeError("PBI_WORKSPACE_ID and PBI_DATASET_ID must both be set.")

    print(f"[{time.strftime('%H:%M:%S')}] Discovering tables in the semantic model...")
    all_tables = list_model_tables(WORKSPACE_ID, DATASET_ID)
    print(f"  -> found {len(all_tables)} tables: {all_tables}")

    tables_to_sync = (
        [t for t in all_tables if t in TABLE_FILTER] if TABLE_FILTER else all_tables
    )
    if not tables_to_sync:
        print("  -> no tables matched PBI_TABLE_FILTER, nothing to sync")
        return

    for table_name in tables_to_sync:
        try:
            sync_table(table_name)
        except Exception as e:
            print(f"  [{table_name}] FAILED: {e}")


if __name__ == "__main__":
    if RUN_ONCE:
        run_once()
    else:
        print(f"Polling every {POLL_INTERVAL_SECONDS}s. Ctrl+C to stop.")
        while True:
            try:
                run_once()
            except Exception as e:
                print(f"Sync run failed: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)