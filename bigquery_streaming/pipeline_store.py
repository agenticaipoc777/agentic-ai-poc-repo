"""
Pipeline persistence: named sync configurations + run history, stored
in a local SQLite file (bigquery_streaming/pipelines.db).

This is intentionally simple for now -- a single-file local database
is fine while this runs as one Streamlit process on your machine. Once
this moves to Kubernetes (multiple pods, no shared local disk), swap
PipelineStore's storage backend for something shared -- Firestore is
the natural fit here (serverless, no separate DB to run), or Cloud SQL
if you'd rather stay relational. The public methods on PipelineStore
below (save_pipeline, list_pipelines, record_run, etc.) are the
interface the rest of the app talks to -- only this file needs to
change to swap backends, nothing in app.py should need to.
"""
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "pipelines.db"

# Status thresholds, in plain terms:
#   green  -- last run succeeded
#   yellow -- last run succeeded but with a notable condition (e.g.
#             zero rows changed, which often means nothing to sync but
#             occasionally means a misconfigured filter/key)
#   red    -- last run failed outright
STATUS_GREEN = "green"
STATUS_YELLOW = "yellow"
STATUS_RED = "red"
STATUS_UNKNOWN = "unknown"  # never run yet


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pipelines (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            pipeline_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            inserted INTEGER,
            updated INTEGER,
            deleted INTEGER,
            bytes_processed INTEGER,
            error_message TEXT,
            FOREIGN KEY (pipeline_id) REFERENCES pipelines (id)
        )
        """
    )
    conn.commit()
    conn.close()


def save_pipeline(name: str, config: dict, pipeline_id: str | None = None) -> str:
    """Create a new pipeline, or overwrite config if pipeline_id is given."""
    conn = _connect()
    if pipeline_id is None:
        pipeline_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO pipelines (id, name, config_json, created_at) VALUES (?, ?, ?, ?)",
            (pipeline_id, name, json.dumps(config), datetime.utcnow().isoformat()),
        )
    else:
        conn.execute(
            "UPDATE pipelines SET name = ?, config_json = ? WHERE id = ?",
            (name, json.dumps(config), pipeline_id),
        )
    conn.commit()
    conn.close()
    return pipeline_id


def delete_pipeline(pipeline_id: str):
    conn = _connect()
    conn.execute("DELETE FROM runs WHERE pipeline_id = ?", (pipeline_id,))
    conn.execute("DELETE FROM pipelines WHERE id = ?", (pipeline_id,))
    conn.commit()
    conn.close()


def list_pipelines() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM pipelines ORDER BY created_at DESC").fetchall()
    conn.close()
    pipelines = []
    for row in rows:
        p = dict(row)
        p["config"] = json.loads(p.pop("config_json"))
        latest = get_latest_run(p["id"])
        p["status"] = latest["status"] if latest else STATUS_UNKNOWN
        p["last_run"] = latest
        pipelines.append(p)
    return pipelines


def get_pipeline(pipeline_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
    conn.close()
    if not row:
        return None
    p = dict(row)
    p["config"] = json.loads(p.pop("config_json"))
    return p


def start_run(pipeline_id: str) -> str:
    run_id = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO runs (id, pipeline_id, started_at, status) VALUES (?, ?, ?, ?)",
        (run_id, pipeline_id, datetime.utcnow().isoformat(), "running"),
    )
    conn.commit()
    conn.close()
    return run_id


def complete_run(
    run_id: str, inserted: int, updated: int, deleted: int, bytes_processed: int
):
    total_changed = (inserted or 0) + (updated or 0) + (deleted or 0)
    status = STATUS_GREEN if total_changed > 0 else STATUS_YELLOW
    conn = _connect()
    conn.execute(
        """
        UPDATE runs
        SET finished_at = ?, status = ?, inserted = ?, updated = ?, deleted = ?,
            bytes_processed = ?
        WHERE id = ?
        """,
        (
            datetime.utcnow().isoformat(), status, inserted, updated, deleted,
            bytes_processed, run_id,
        ),
    )
    conn.commit()
    conn.close()


def fail_run(run_id: str, error_message: str):
    conn = _connect()
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, error_message = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), STATUS_RED, error_message, run_id),
    )
    conn.commit()
    conn.close()


def get_latest_run(pipeline_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM runs WHERE pipeline_id = ? ORDER BY started_at DESC LIMIT 1",
        (pipeline_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_run_history(pipeline_id: str, limit: int = 20) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM runs WHERE pipeline_id = ? ORDER BY started_at DESC LIMIT ?",
        (pipeline_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


init_db()