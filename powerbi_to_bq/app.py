"""
Power BI semantic model -> BigQuery, as a click-driven screen.

Everything (Power BI tenant/client/workspace/dataset, BigQuery
project/dataset) is entered on this screen -- nothing hardcoded.
Table discovery is fully dynamic: click "Discover Tables" and it
queries the semantic model itself for its table list via
INFO.TABLES(), rather than any table name being baked into the code.
"""
import os
import time
import streamlit as st

from powerbi_client import execute_dax_query, list_model_tables
from bq_loader import load_dataframe_to_bigquery, full_refresh_load

st.set_page_config(page_title="Power BI -> BigQuery", page_icon="🔄", layout="wide")
st.title("🔄 Power BI Semantic Model -> BigQuery")
st.caption(
    "Discovers tables dynamically from your semantic model -- nothing is "
    "hardcoded. Sign-in uses device code (MFA-compatible)."
)

if "signin_message" not in st.session_state:
    st.session_state.signin_message = None
if "discovered_tables" not in st.session_state:
    st.session_state.discovered_tables = []
if "continuous_running" not in st.session_state:
    st.session_state.continuous_running = False


def show_device_code(message: str):
    # Called from inside get_access_token() the moment a sign-in is
    # needed -- shown on-screen instead of only printing to a
    # terminal the user of this UI likely isn't watching.
    st.session_state.signin_message = message
    st.warning(message)


# ============================================================== CONNECTION INPUTS
st.subheader("1. Power BI connection")
pbi_cols = st.columns(4)
with pbi_cols[0]:
    tenant_id = st.text_input("Tenant ID", value="ad12c024-e320-4b19-aa0b-b0c36c136e70", key="tenant_id")
with pbi_cols[1]:
    client_id = st.text_input("Client ID (app registration)", value="a632fbf6-f1cd-4abb-a50d-7cc305010c8b", key="client_id")
with pbi_cols[2]:
    workspace_id = st.text_input("Workspace ID", value="16940f82-f828-4117-9608-2c39f221d389", key="workspace_id")
with pbi_cols[3]:
    dataset_id = st.text_input("Dataset ID", value="e482f8c5-e7fa-430a-9749-95aeed186631", key="dataset_id")

# powerbi_client.py reads these from environment variables -- set
# them here so the on-screen fields are the actual source of truth,
# not something pre-set outside the UI.
os.environ["PBI_TENANT_ID"] = tenant_id
os.environ["PBI_CLIENT_ID"] = client_id

st.subheader("2. BigQuery target")
bq_cols = st.columns(3)
with bq_cols[0]:
    bq_project = st.text_input("BigQuery project ID", value="agentic-ai-502518", key="bq_project")
with bq_cols[1]:
    bq_dataset = st.text_input("BigQuery dataset", value="analytics_v3", key="bq_dataset")
with bq_cols[2]:
    table_prefix = st.text_input("Target table prefix", value="pbi_", key="table_prefix")

os.environ["PBI_TARGET_PROJECT"] = bq_project
bq_location = st.text_input(
    "BigQuery location", value="EU", key="bq_location",
    help="Must match your dataset's actual location.",
)
os.environ["PBI_TARGET_LOCATION"] = bq_location

st.divider()

# ============================================================== TABLE DISCOVERY
st.subheader("3. Tables")
pbi_ready = bool(tenant_id and client_id and workspace_id and dataset_id)

disc_cols = st.columns([1, 4])
with disc_cols[0]:
    if st.button("🔍 Discover Tables", disabled=not pbi_ready, type="primary"):
        with st.spinner("Querying semantic model for its table list..."):
            try:
                tables = list_model_tables(
                    workspace_id, dataset_id, on_device_code=show_device_code
                )
                st.session_state.discovered_tables = tables
                st.success(f"Found {len(tables)} tables.")
            except Exception as e:
                st.error(f"Discovery failed: {e}")

if not pbi_ready:
    st.info("Fill in all four Power BI fields above to enable discovery.")

selected_tables = []
table_keys = {}
if st.session_state.discovered_tables:
    selected_tables = st.multiselect(
        "Tables to sync",
        st.session_state.discovered_tables,
        default=st.session_state.discovered_tables,
    )
    with st.expander("Optional: set a unique-key column per table for upsert (MERGE) instead of full refresh"):
        st.caption(
            "Any table left blank here gets a full-table replace every run "
            "instead of an incremental upsert -- simpler and always correct, "
            "but not incremental."
        )
        for t in selected_tables:
            key_col = st.text_input(f"Key column for '{t}'", key=f"key_{t}", value="")
            if key_col.strip():
                table_keys[t] = key_col.strip()

st.divider()

# ============================================================== IMPORT / SYNC
st.subheader("4. Run")
bq_ready = bool(bq_project and bq_dataset)
run_ready = pbi_ready and bq_ready and selected_tables


def sync_selected_tables():
    for table_name in selected_tables:
        bq_table_name = table_prefix + "".join(
            c if c.isalnum() or c == "_" else "_" for c in table_name
        )
        st.write(f"**{table_name}** -> `{bq_dataset}.{bq_table_name}`")
        try:
            df = execute_dax_query(
                workspace_id, dataset_id, f"EVALUATE '{table_name}'",
                on_device_code=show_device_code,
            )
        except Exception as e:
            st.error(f"  Query failed: {e}")
            continue

        if df.empty:
            st.caption("  empty result, skipped")
            continue

        try:
            if table_name in table_keys:
                result = load_dataframe_to_bigquery(
                    df, bq_dataset, bq_table_name, [table_keys[table_name]]
                )
                if result.get("target_table_created"):
                    st.success(f"  table created, loaded {result['rows_loaded']} rows")
                else:
                    stats = result["dml_stats"]
                    st.success(f"  MERGE: inserted={stats['inserted']} updated={stats['updated']}")
            else:
                rows = full_refresh_load(df, bq_dataset, bq_table_name)
                st.success(f"  full refresh: {rows} rows")
        except Exception as e:
            st.error(f"  BigQuery load failed: {e}")


run_cols = st.columns(3)
with run_cols[0]:
    if st.button("📥 Import (one-time)", disabled=not run_ready, type="primary"):
        with st.spinner("Syncing selected tables..."):
            sync_selected_tables()

with run_cols[1]:
    if st.button("▶ Start Synchronize (polling)", disabled=not run_ready):
        st.session_state.continuous_running = True

with run_cols[2]:
    if st.button("■ Stop"):
        st.session_state.continuous_running = False

if not run_ready:
    st.info("Complete steps 1-3 and select at least one table to enable Import/Synchronize.")

if st.session_state.continuous_running:
    poll_interval = st.slider("Polling interval (seconds)", 30, 1800, 300)
    st.warning(
        "Runs on a timer inside this Streamlit session -- stops if you close "
        "the tab. For real always-on operation, move this to a Cloud Run Job "
        "or Kubernetes CronJob instead, same as the BigQuery-to-BigQuery "
        "sync tool built earlier in this project."
    )
    st.write(f"[{time.strftime('%H:%M:%S')}] Running sync...")
    sync_selected_tables()
    time.sleep(poll_interval)
    st.rerun()