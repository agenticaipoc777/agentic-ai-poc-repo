"""
Core BigQuery-to-BigQuery table sync engine.

Builds and executes a MERGE statement that mirrors selected fields from
a source table into a target table, handling insert, update, and
(optionally) delete in a single operation -- this is BigQuery's own
MERGE semantics, not a custom row-by-row diffing algorithm.

IMPORTANT ARCHITECTURE NOTE, READ FIRST:
BigQuery has no native change-data-capture stream you can subscribe to
for "table X changed, here's the delta" the way Postgres logical
replication or a message queue does. What this module implements as
"continuous streaming" (in app.py) is POLLING: re-running this same
MERGE on a timer. This is a legitimate, commonly-used pattern for
BigQuery-to-BigQuery sync, but it is NOT sub-second real-time --
latency is bounded by your polling interval plus however long the
MERGE itself takes to run (which scales with table size). If you
eventually need genuine low-latency CDC, that requires a different
architecture entirely (e.g. Dataflow reading a change stream from the
ORIGINAL source system before it lands in BigQuery) -- a polling
MERGE between two BigQuery tables cannot provide that, no matter how
short the polling interval is set.

Also note: source and target datasets must be in the SAME BigQuery
location (e.g. both "EU") for a single MERGE query to reference both --
BigQuery does not allow a query job to read/write across two different
dataset locations in one statement.
"""
import os
from google.cloud import bigquery

# Safety cap on bytes scanned per sync run, same pattern used
# elsewhere in this project's BigQuery-facing services -- protects
# against an unexpectedly expensive MERGE (e.g. a huge source table
# with no filtering) running unbounded. Set to "0" to disable.
MAX_BYTES_BILLED = int(os.environ.get("SYNC_MAX_BYTES_BILLED", str(200 * 1024**3)))


def get_client(project_id: str) -> bigquery.Client:
    return bigquery.Client(project=project_id)


def list_datasets(client: bigquery.Client) -> list[str]:
    return [d.dataset_id for d in client.list_datasets()]


def list_tables(client: bigquery.Client, dataset_id: str) -> list[str]:
    return [t.table_id for t in client.list_tables(dataset_id)]


def list_fields(client: bigquery.Client, dataset_id: str, table_id: str) -> list[str]:
    table_ref = f"{client.project}.{dataset_id}.{table_id}"
    table = client.get_table(table_ref)
    return [field.name for field in table.schema]


def ensure_target_table(
    client: bigquery.Client,
    source_project: str,
    source_dataset: str,
    source_table: str,
    target_project: str,
    target_dataset: str,
    target_table: str,
    fields: list[str],
    location: str,
) -> bool:
    """
    Creates the target table if it doesn't exist yet, with a schema
    matching the selected source fields. Never alters an EXISTING
    target table's schema -- silently adding/changing columns on a
    live table is a separate, riskier operation than initial creation,
    and is deliberately not done automatically here.
    Returns True if the table was created, False if it already existed.
    """
    target_ref = f"{target_project}.{target_dataset}.{target_table}"
    try:
        client.get_table(target_ref)
        return False
    except Exception:
        pass

    field_list = ", ".join(f"`{f}`" for f in fields)
    ddl = f"""
    CREATE TABLE `{target_ref}` AS
    SELECT {field_list}
    FROM `{source_project}.{source_dataset}.{source_table}`
    WHERE FALSE
    """
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=(MAX_BYTES_BILLED if MAX_BYTES_BILLED > 0 else None)
    )
    job = client.query(ddl, job_config=job_config, location=location)
    job.result()
    return True


def build_merge_sql(
    source_project: str,
    source_dataset: str,
    source_table: str,
    target_project: str,
    target_dataset: str,
    target_table: str,
    fields: list[str],
    key_fields: list[str],
    sync_deletes: bool,
) -> str:
    if not key_fields:
        raise ValueError(
            "At least one key field is required to match rows between "
            "source and target."
        )
    if not all(k in fields for k in key_fields):
        raise ValueError(
            "Every key field must also be included in the selected fields list."
        )

    non_key_fields = [f for f in fields if f not in key_fields]

    source_ref = f"{source_project}.{source_dataset}.{source_table}"
    target_ref = f"{target_project}.{target_dataset}.{target_table}"

    field_list = ", ".join(f"`{f}`" for f in fields)
    on_clause = " AND ".join(f"T.`{k}` = S.`{k}`" for k in key_fields)

    update_clause = ""
    if non_key_fields:
        set_clause = ", ".join(f"T.`{f}` = S.`{f}`" for f in non_key_fields)
        update_clause = f"WHEN MATCHED THEN UPDATE SET {set_clause}"

    insert_cols = ", ".join(f"`{f}`" for f in fields)
    insert_vals = ", ".join(f"S.`{f}`" for f in fields)
    insert_clause = f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"

    delete_clause = "WHEN NOT MATCHED BY SOURCE THEN DELETE" if sync_deletes else ""

    sql = f"""
MERGE `{target_ref}` AS T
USING (SELECT {field_list} FROM `{source_ref}`) AS S
ON {on_clause}
{update_clause}
{insert_clause}
{delete_clause}
""".strip()
    return sql


def run_sync(
    client: bigquery.Client,
    source_project: str,
    source_dataset: str,
    source_table: str,
    target_project: str,
    target_dataset: str,
    target_table: str,
    fields: list[str],
    key_fields: list[str],
    sync_deletes: bool,
    location: str,
) -> dict:
    created = ensure_target_table(
        client, source_project, source_dataset, source_table,
        target_project, target_dataset, target_table, fields, location,
    )
    sql = build_merge_sql(
        source_project, source_dataset, source_table,
        target_project, target_dataset, target_table,
        fields, key_fields, sync_deletes,
    )
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=(MAX_BYTES_BILLED if MAX_BYTES_BILLED > 0 else None)
    )
    job = client.query(sql, job_config=job_config, location=location)
    job.result()

    dml_stats = job.dml_stats
    return {
        "target_table_created": created,
        "dml_stats": {
            "inserted": dml_stats.inserted_row_count if dml_stats else None,
            "updated": dml_stats.updated_row_count if dml_stats else None,
            "deleted": dml_stats.deleted_row_count if dml_stats else None,
        },
        "bytes_processed": job.total_bytes_processed,
        "sql": sql,
    }