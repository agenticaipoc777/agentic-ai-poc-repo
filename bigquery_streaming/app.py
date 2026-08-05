"""
BigQuery -> BigQuery table sync UI, with saved pipelines and monitoring.

Two views:
  - Pipelines: list of saved sync configs, each showing a status dot
    (green = last run succeeded with changes, yellow = succeeded with
    nothing to sync, red = last run failed, grey = never run) and the
    captured error message for any failed run.
  - Configure / Run: pick source, target, fields, keys, and mode --
    same as before -- with a "Save pipeline" option so you don't have
    to re-enter this every time.
"""
import time
import streamlit as st

from sync_engine import get_client, list_datasets, list_tables, list_fields, run_sync
import pipeline_store as store

st.set_page_config(page_title="BigQuery Table Sync", page_icon="🔄", layout="wide")

DEFAULT_PROJECT = "agentic-ai-502518"
DEFAULT_LOCATION = "EU"

STATUS_DOT = {
    store.STATUS_GREEN: "🟢",
    store.STATUS_YELLOW: "🟡",
    store.STATUS_RED: "🔴",
    store.STATUS_UNKNOWN: "⚪",
}

if "view" not in st.session_state:
    st.session_state.view = "pipelines"
if "editing_pipeline_id" not in st.session_state:
    st.session_state.editing_pipeline_id = None


def go_to_configure(pipeline_id: str | None = None):
    st.session_state.view = "configure"
    st.session_state.editing_pipeline_id = pipeline_id


def go_to_pipelines():
    st.session_state.view = "pipelines"
    st.session_state.editing_pipeline_id = None


def run_pipeline_now(pipeline: dict):
    cfg = pipeline["config"]
    run_id = store.start_run(pipeline["id"])
    try:
        client = get_client(cfg["target_project"])
        result = run_sync(
            client, cfg["source_project"], cfg["source_dataset"], cfg["source_table"],
            cfg["target_project"], cfg["target_dataset"], cfg["target_table"],
            cfg["fields"], cfg["key_fields"], cfg["sync_deletes"], cfg["location"],
        )
        stats = result["dml_stats"]
        store.complete_run(
            run_id, stats["inserted"], stats["updated"], stats["deleted"],
            result["bytes_processed"],
        )
        return True, result
    except Exception as e:
        store.fail_run(run_id, str(e))
        return False, str(e)


# ============================================================== PIPELINES VIEW
def render_pipelines_view():
    st.title("🔄 BigQuery Sync Pipelines")
    st.caption("Saved sync pipelines, their last run status, and monitoring history.")

    top_cols = st.columns([1, 5])
    with top_cols[0]:
        if st.button("➕ New pipeline", type="primary"):
            go_to_configure()
            st.rerun()

    pipelines = store.list_pipelines()

    if not pipelines:
        st.info("No pipelines saved yet. Click **New pipeline** to create one.")
        return

    for p in pipelines:
        cfg = p["config"]
        dot = STATUS_DOT.get(p["status"], "⚪")
        with st.container(border=True):
            header_cols = st.columns([0.4, 3, 1.2, 1.2, 1])
            with header_cols[0]:
                st.markdown(f"### {dot}")
            with header_cols[1]:
                st.markdown(f"**{p['name']}**")
                st.caption(
                    f"{cfg['source_project']}.{cfg['source_dataset']}.{cfg['source_table']} "
                    f"→ {cfg['target_project']}.{cfg['target_dataset']}.{cfg['target_table']}"
                )
            with header_cols[2]:
                if p["last_run"]:
                    st.caption("Last run")
                    st.write(p["last_run"]["started_at"][:19].replace("T", " "))
                else:
                    st.caption("Never run")
            with header_cols[3]:
                if st.button("▶ Run now", key=f"run_{p['id']}"):
                    with st.spinner(f"Running {p['name']}..."):
                        ok, result = run_pipeline_now(p)
                    if ok:
                        st.success("Run complete.")
                    else:
                        st.error(f"Run failed: {result}")
                    st.rerun()
            with header_cols[4]:
                if st.button("⚙ Details", key=f"details_{p['id']}"):
                    go_to_configure(p["id"])
                    st.rerun()

            # Captured error message for a red status, surfaced right
            # on the list -- monitoring shouldn't require clicking in
            # to find out why something's failing.
            if p["status"] == store.STATUS_RED and p["last_run"] and p["last_run"].get("error_message"):
                st.error(f"Last error: {p['last_run']['error_message']}")

            with st.expander("Run history"):
                history = store.get_run_history(p["id"])
                if not history:
                    st.caption("No runs yet.")
                else:
                    for run in history:
                        run_dot = STATUS_DOT.get(run["status"], "⚪")
                        line = f"{run_dot} {run['started_at'][:19].replace('T', ' ')} — "
                        if run["status"] == store.STATUS_RED:
                            line += f"FAILED: {run.get('error_message', 'unknown error')}"
                        else:
                            line += (
                                f"inserted={run['inserted']} updated={run['updated']} "
                                f"deleted={run['deleted']}"
                            )
                        st.text(line)


# ============================================================== CONFIGURE VIEW
def render_configure_view():
    editing = st.session_state.editing_pipeline_id
    existing = store.get_pipeline(editing) if editing else None

    top_cols = st.columns([1, 5])
    with top_cols[0]:
        if st.button("← Back to pipelines"):
            go_to_pipelines()
            st.rerun()

    st.title("⚙ Configure pipeline" if not existing else f"⚙ {existing['name']}")

    default_cfg = existing["config"] if existing else {}
    pipeline_name = st.text_input(
        "Pipeline name", value=existing["name"] if existing else "",
        placeholder="e.g. auth-to-retail-sales",
    )

    with st.sidebar:
        st.header("Connection")
        location = st.text_input(
            "BigQuery location", value=default_cfg.get("location", DEFAULT_LOCATION),
            help="Source and target datasets must be in the SAME location.",
        )

    col_src, col_tgt = st.columns(2)

    with col_src:
        st.subheader("Source")
        source_project = st.text_input(
            "Source project ID", value=default_cfg.get("source_project", DEFAULT_PROJECT), key="src_proj"
        )
        src_client = get_client(source_project)
        try:
            source_datasets = list_datasets(src_client)
        except Exception as e:
            st.error(f"Couldn't list datasets: {e}")
            source_datasets = []

        src_ds_default = default_cfg.get("source_dataset")
        src_ds_index = source_datasets.index(src_ds_default) if src_ds_default in source_datasets else 0
        source_dataset = st.selectbox("Source dataset", source_datasets, index=src_ds_index, key="src_ds") if source_datasets else None

        source_tables = []
        if source_dataset:
            try:
                source_tables = list_tables(src_client, source_dataset)
            except Exception as e:
                st.error(f"Couldn't list tables: {e}")

        src_tbl_default = default_cfg.get("source_table")
        src_tbl_index = source_tables.index(src_tbl_default) if src_tbl_default in source_tables else 0
        source_table = st.selectbox("Source table", source_tables, index=src_tbl_index, key="src_tbl") if source_tables else None

        source_fields = []
        if source_table:
            try:
                source_fields = list_fields(src_client, source_dataset, source_table)
            except Exception as e:
                st.error(f"Couldn't read schema: {e}")

    with col_tgt:
        st.subheader("Target")
        target_project = st.text_input(
            "Target project ID", value=default_cfg.get("target_project", DEFAULT_PROJECT), key="tgt_proj"
        )
        tgt_client = get_client(target_project)
        try:
            target_datasets = list_datasets(tgt_client)
        except Exception as e:
            st.error(f"Couldn't list datasets: {e}")
            target_datasets = []

        tgt_ds_default = default_cfg.get("target_dataset")
        tgt_ds_index = target_datasets.index(tgt_ds_default) if tgt_ds_default in target_datasets else 0
        target_dataset = st.selectbox("Target dataset", target_datasets, index=tgt_ds_index, key="tgt_ds") if target_datasets else None
        target_table = st.text_input(
            "Target table name", value=default_cfg.get("target_table", ""), key="tgt_tbl",
            help="Created automatically if it doesn't already exist.",
        )

    st.divider()

    if source_fields:
        st.subheader("Fields to sync")
        default_fields = default_cfg.get("fields", source_fields)
        selected_fields = st.multiselect(
            "Select fields", source_fields,
            default=[f for f in default_fields if f in source_fields] or source_fields,
            key="fields_sel",
        )
        default_keys = default_cfg.get("key_fields", [])
        key_fields = st.multiselect(
            "Key field(s) — used to match rows between source and target",
            selected_fields,
            default=[k for k in default_keys if k in selected_fields],
            key="key_sel",
        )
    else:
        selected_fields, key_fields = [], []
        st.info("Pick a source table above to see its fields.")

    st.divider()

    st.subheader("Sync mode")
    mode_options = ["One-time import", "Continuous sync (polling)"]
    mode_default = default_cfg.get("mode", mode_options[0])
    mode = st.radio("Mode", mode_options, index=mode_options.index(mode_default), horizontal=True)

    sync_deletes = st.checkbox(
        "Mirror deletes (rows removed from source will also be removed from target)",
        value=default_cfg.get("sync_deletes", True),
    )

    poll_interval = default_cfg.get("poll_interval", 60)
    if mode == "Continuous sync (polling)":
        poll_interval = st.slider("Polling interval (seconds)", min_value=10, max_value=600, value=poll_interval)
        st.warning(
            "Continuous mode inside Streamlit only runs while this session "
            "stays open — see 'About continuous mode' at the bottom for the "
            "production deployment path (Cloud Run Job / K8s CronJob)."
        )

    st.divider()

    ready = bool(
        pipeline_name and source_dataset and source_table and target_dataset
        and target_table and selected_fields and key_fields
    )

    if not ready:
        st.info("Fill in a pipeline name, source, target, fields, and at least one key field.")
    else:
        config = {
            "source_project": source_project, "source_dataset": source_dataset, "source_table": source_table,
            "target_project": target_project, "target_dataset": target_dataset, "target_table": target_table,
            "fields": selected_fields, "key_fields": key_fields,
            "sync_deletes": sync_deletes, "location": location,
            "mode": mode, "poll_interval": poll_interval,
        }

        save_cols = st.columns([1, 1, 3])
        with save_cols[0]:
            if st.button("💾 Save pipeline", type="primary"):
                pid = store.save_pipeline(pipeline_name, config, pipeline_id=editing)
                st.success(f"Saved pipeline '{pipeline_name}'.")
                st.session_state.editing_pipeline_id = pid
                st.rerun()
        with save_cols[1]:
            if st.button("▶ Run once now"):
                with st.spinner("Running MERGE..."):
                    try:
                        result = run_sync(
                            tgt_client, source_project, source_dataset, source_table,
                            target_project, target_dataset, target_table,
                            selected_fields, key_fields, sync_deletes, location,
                        )
                        st.success("Sync complete.")
                        st.json(result["dml_stats"])
                        with st.expander("View generated SQL"):
                            st.code(result["sql"], language="sql")
                    except Exception as e:
                        st.error(f"Sync failed: {e}")

        if mode == "Continuous sync (polling)" and editing:
            st.divider()
            run_key = f"continuous_running_{editing}"
            if run_key not in st.session_state:
                st.session_state[run_key] = False
            c1, c2 = st.columns(2)
            with c1:
                if st.button("▶ Start continuous sync"):
                    st.session_state[run_key] = True
            with c2:
                if st.button("■ Stop"):
                    st.session_state[run_key] = False

            status_area = st.empty()
            if st.session_state[run_key]:
                pipeline = store.get_pipeline(editing)
                ok, result = run_pipeline_now(pipeline)
                if ok:
                    stats = result["dml_stats"]
                    status_area.success(
                        f"Last sync: {time.strftime('%H:%M:%S')} — "
                        f"inserted={stats['inserted']} updated={stats['updated']} deleted={stats['deleted']}"
                    )
                else:
                    status_area.error(f"Sync failed: {result}")
                time.sleep(poll_interval)
                st.rerun()
            else:
                status_area.info("Continuous sync is stopped.")

    st.divider()
    with st.expander("ℹ️ About continuous mode and production deployment"):
        st.markdown(
            """
            "Continuous sync" works by re-running the MERGE on a timer inside
            this Streamlit process. Fine for **local testing**, not for
            permanent operation — a page reload, browser close, or pod
            restart stops it.

            For real always-on operation, move `sync_engine.run_sync()` (and
            the `pipeline_store` calls that record status) into a standalone
            script and run it as a **Cloud Run Job** on a Cloud Scheduler
            trigger, or a **Kubernetes CronJob** — either can call
            `pipeline_store.start_run()` / `complete_run()` / `fail_run()`
            exactly as this UI does, so the same pipeline list and status
            dots you see here keep working once execution moves off
            Streamlit entirely.
            """
        )


# ============================================================================
if st.session_state.view == "pipelines":
    render_pipelines_view()
else:
    render_configure_view()