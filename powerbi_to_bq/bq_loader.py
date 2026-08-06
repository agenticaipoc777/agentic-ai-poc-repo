"""
Loads a DataFrame (from a Power BI DAX query result) into BigQuery,
creating the target table on first run and upserting via MERGE on
subsequent runs -- same pattern as bigquery_streaming/sync_engine.py,
so anything you already learned/tested there (MERGE semantics, the
"polling, not true CDC" caveat, the same-location requirement) applies
here too.
"""
import os
from google.cloud import bigquery

PROJECT_ID = os.environ.get("PBI_TARGET_PROJECT", "agentic-ai-502518")
LOCATION = os.environ.get("PBI_TARGET_LOCATION", "EU")


def full_refresh_load(df, dataset_id: str, table_id: str) -> int:
    """
    Simple full-table replace -- used for any table that doesn't have
    a declared key column (see PBI_TABLE_KEYS in powerbi_sync.py).
    Always correct regardless of schema/row changes since it just
    overwrites the whole table every run, at the cost of not being a
    true incremental upsert.
    """
    client = bigquery.Client(project=PROJECT_ID)
    target_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    load_job = client.load_table_from_dataframe(df, target_ref, job_config=job_config)
    load_job.result()
    return len(df)


def load_dataframe_to_bigquery(
    df, dataset_id: str, table_id: str, key_columns: list[str]
) -> dict:
    """
    key_columns: column(s) that uniquely identify a row, used for the
    MERGE match condition (upsert). If the DataFrame has no reliable
    unique key, pass a full-refresh approach instead (see
    write_disposition="WRITE_TRUNCATE" note below) rather than forcing
    a MERGE with a key that doesn't actually uniquely identify rows.
    """
    client = bigquery.Client(project=PROJECT_ID)
    target_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"
    staging_ref = f"{PROJECT_ID}.{dataset_id}._staging_{table_id}"

    # Load into a staging table first (simple full load of THIS
    # query's result), then MERGE staging -> target. This keeps the
    # MERGE logic simple and avoids re-deriving BigQuery types from
    # pandas dtypes by hand -- load_table_from_dataframe infers them.
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    load_job = client.load_table_from_dataframe(
        df, staging_ref, job_config=job_config
    )
    load_job.result()

    # Create target table on first run, matching the staging schema.
    try:
        client.get_table(target_ref)
        target_existed = True
    except Exception:
        client.copy_table(staging_ref, target_ref).result()
        target_existed = False

    if not target_existed:
        return {"target_table_created": True, "rows_loaded": len(df)}

    columns = list(df.columns)
    on_clause = " AND ".join(f"T.`{k}` = S.`{k}`" for k in key_columns)
    non_key_cols = [c for c in columns if c not in key_columns]
    update_clause = ""
    if non_key_cols:
        set_clause = ", ".join(f"T.`{c}` = S.`{c}`" for c in non_key_cols)
        update_clause = f"WHEN MATCHED THEN UPDATE SET {set_clause}"
    insert_cols = ", ".join(f"`{c}`" for c in columns)
    insert_vals = ", ".join(f"S.`{c}`" for c in columns)

    merge_sql = f"""
    MERGE `{target_ref}` AS T
    USING `{staging_ref}` AS S
    ON {on_clause}
    {update_clause}
    WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
    """
    job = client.query(merge_sql, location=LOCATION)
    job.result()

    return {
        "target_table_created": False,
        "dml_stats": {
            "inserted": job.dml_stats.inserted_row_count if job.dml_stats else None,
            "updated": job.dml_stats.updated_row_count if job.dml_stats else None,
        },
    }