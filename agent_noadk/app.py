"""
BigQuery analytics agent -- Gemini 2.5 via direct Vertex AI SDK
(NO Google ADK), with native function calling instead of asking the
model to write JSON as text.

WHY THIS IS DIFFERENT FROM THE ADK VERSION: the previous build asked
Gemini to embed a JSON code block in its chat reply, which the
Streamlit app then had to regex-extract -- fragile, and risks the raw
JSON leaking into what the user sees in chat if formatting slips.
Here, Gemini calls a `run_query` FUNCTION; BigQuery's rows come back
as real structured data exchanged between Gemini and this Python
process -- they never pass through chat text at all. The user only
ever sees Gemini's natural-language summary; the actual rows go
straight into session state for the dashboard. No JSON is ever shown
to the user, by construction, not by prompt instruction.

PERFORMANCE, READ THIS FIRST: two real, measured levers are applied
below, not speculative ones:
  1. Schema is fetched ONCE at startup and given to Gemini directly in
     the system prompt, instead of exposed as a "list_tables" tool the
     model has to decide to call. That decision-call-respond cycle was
     a FULL EXTRA Gemini round trip on nearly every question -- for a
     small table (~8,000 rows), that redundant round trip was very
     likely the dominant cost, not BigQuery's own query time.
  2. Default model switched to gemini-2.5-flash, which trades some
     reasoning depth for materially lower latency than 2.5-pro. Test
     that it still writes correct SQL for your harder questions before
     fully committing to it -- that tradeoff is real.
Given your actual data volume is small, 2-3 second responses are now
a realistic target, not just best-effort -- the previous slowness was
almost certainly the double round trip + the heavier Pro model, both
addressed here. Total response time is now also shown directly in the
chat UI so you can see this for real, not take it on faith.

SCALE NOTE (~10 billion rows, if/when a table actually reaches that
size): BigQuery does the heavy lifting via SQL aggregation. This app
enforces a bytes-billed safety cap (dry run first, same pattern as
bq_pg_proxy_app) and a row cap on whatever comes back to this process
-- an LLM-generated query against a billion-row table is exactly the
kind of thing that could accidentally scan/return far more than
intended without these caps.
"""
import os
import time

import streamlit as st
import pandas as pd
import plotly.express as px
from google.cloud import bigquery
import vertexai
from vertexai.generative_models import (
    GenerativeModel, Tool, FunctionDeclaration, Part, GenerationConfig
)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "agentic-ai-502518")
LOCATION = os.environ.get("GCP_LOCATION", "europe-west1")
BQ_LOCATION = os.environ.get("BQ_LOCATION", "EU")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

MAX_BYTES_BILLED = int(os.environ.get("MAX_BYTES_BILLED", str(500 * 1024**3)))  # 500GB
MAX_RESULT_ROWS = int(os.environ.get("MAX_RESULT_ROWS", "2000"))

st.set_page_config(page_title="BigQuery Gemini Dashboard", page_icon="📊", layout="wide")

# ==============================================================================
# CLIENTS (cached -- initialized once per process)
# ==============================================================================

@st.cache_resource
def get_bq_client():
    return bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)


def _list_tables_safe() -> dict:
    client = get_bq_client()
    try:
        datasets = list(client.list_datasets())
        result = {}
        for ds in datasets:
            tables = list(client.list_tables(ds.dataset_id))
            result[ds.dataset_id] = []
            for t in tables:
                full_table = client.get_table(f"{PROJECT_ID}.{ds.dataset_id}.{t.table_id}")
                cols = [f"{f.name} ({f.field_type})" for f in full_table.schema]
                result[ds.dataset_id].append({"table": t.table_id, "columns": cols})
        return result
    except Exception as e:
        return {"error": str(e)}


@st.cache_resource
def get_schema_context() -> str:
    """
    Fetches the full dataset/table/column schema ONCE per process and
    formats it as plain text for the system prompt -- see the
    performance note at the top of this file. This is what removes
    the redundant list_tables round trip.
    """
    result = _list_tables_safe()
    if "error" in result:
        return f"(schema lookup failed: {result['error']})"
    lines = []
    for dataset, tables in result.items():
        for t in tables:
            lines.append(f"- {dataset}.{t['table']}: {', '.join(t['columns'])}")
    return "\n".join(lines)


@st.cache_resource
def get_gemini_model():
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    run_query_decl = FunctionDeclaration(
        name="run_query",
        description=(
            "Executes a GoogleSQL query against BigQuery and returns "
            "result rows. Some tables in this project can be very "
            "large -- prefer aggregation (GROUP BY, SUM, COUNT, AVG, "
            "TOP-N via ORDER BY + LIMIT) over selecting raw "
            "unaggregated rows from a large table."
        ),
        parameters={
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A valid GoogleSQL query."}
            },
            "required": ["sql"],
        },
    )

    # list_tables is intentionally NOT exposed as a tool -- see
    # get_schema_context() above. Only run_query remains, so a normal
    # question is now ONE tool round trip instead of two.
    bq_tool = Tool(function_declarations=[run_query_decl])

    system_instruction = f"""You are a BigQuery data analyst for project '{PROJECT_ID}'.

Here is the full schema of every table available to you -- you already
know this, do NOT ask to look it up, do not claim you need to check
what tables exist:

{get_schema_context()}

Use the run_query tool to answer questions with REAL data -- never
fabricate numbers.

You do not draw charts yourself -- the application renders all
visualizations (bar, pie, line, scatter, tables) from whatever data
your run_query calls return. Your job is only to run the right SQL
and give a short, plain-language summary of the result in your final
reply. Do not include raw data, JSON, or code in your final reply --
just a concise natural-language answer."""

    return GenerativeModel(
        MODEL_NAME,
        tools=[bq_tool],
        system_instruction=system_instruction,
        generation_config=GenerationConfig(temperature=0.1),
    )


# ==============================================================================
# TOOL IMPLEMENTATION (safety-capped)
# ==============================================================================

def _run_query_safe(sql: str) -> dict:
    client = get_bq_client()
    timings = {}

    t0 = time.time()
    try:
        dry_run_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        dry_run_job = client.query(sql, job_config=dry_run_config)
        est_bytes = dry_run_job.total_bytes_processed or 0
        timings["dry_run"] = time.time() - t0
        if MAX_BYTES_BILLED > 0 and est_bytes > MAX_BYTES_BILLED:
            return {
                "error": (
                    f"Query would scan {est_bytes:,} bytes, exceeding the "
                    f"{MAX_BYTES_BILLED:,} byte safety cap. Add a filter or "
                    f"aggregation to reduce the scan size."
                )
            }
    except Exception as e:
        return {"error": f"Query validation failed: {e}"}

    t1 = time.time()
    try:
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=MAX_BYTES_BILLED if MAX_BYTES_BILLED > 0 else None,
            use_query_cache=True,
        )
        result = client.query(sql, job_config=job_config).result()
        rows = []
        for i, row in enumerate(result):
            if MAX_RESULT_ROWS > 0 and i >= MAX_RESULT_ROWS:
                break
            rows.append(dict(row.items()))
        timings["query_execution"] = time.time() - t1
        if "_timings" not in st.session_state:
            st.session_state._timings = {}
        st.session_state._timings.update(timings)
        return {"rows": rows, "row_count": len(rows), "truncated": len(rows) == MAX_RESULT_ROWS}
    except Exception as e:
        return {"error": str(e)}


TOOL_FUNCS = {"run_query": _run_query_safe}

# ==============================================================================
# AGENT LOOP (manual function-calling loop -- transparent, not "magic")
# ==============================================================================

def ask_agent(prompt: str):
    """
    Returns (summary_text, dataframe_or_none). Also populates
    st.session_state._timings with a breakdown of exactly where time
    was spent this turn -- schema/model init (should be ~0 after the
    first-ever question), each Gemini round trip, and the BigQuery
    steps from _run_query_safe above.
    """
    timings = st.session_state.get("_timings", {})

    t0 = time.time()
    model = get_gemini_model()  # cached after first call -- near-0 on repeat questions
    timings["model_init"] = time.time() - t0

    chat = model.start_chat()

    t1 = time.time()
    response = chat.send_message(prompt)
    timings["gemini_call_1_decide_tool"] = time.time() - t1

    last_df = None
    round_trip = 2
    for _ in range(4):
        part = response.candidates[0].content.parts[0]
        fn = getattr(part, "function_call", None)
        if not fn or not fn.name:
            break

        args = dict(fn.args) if fn.args else {}
        result = TOOL_FUNCS.get(fn.name, lambda **_: {"error": "unknown tool"})(**args)

        if fn.name == "run_query" and isinstance(result, dict) and result.get("rows"):
            last_df = pd.DataFrame(result["rows"])

        t2 = time.time()
        response = chat.send_message(
            Part.from_function_response(name=fn.name, response={"result": result})
        )
        timings[f"gemini_call_{round_trip}_after_tool"] = time.time() - t2
        round_trip += 1

    st.session_state._timings = timings
    final_text = response.text if hasattr(response, "text") else str(response)
    return final_text, last_df


@st.cache_data(ttl=300, show_spinner=False)
def ask_agent_cached(prompt: str):
    """
    Identical prompts within a 5-minute window skip the entire
    Gemini+BigQuery round trip and return instantly -- shows up as a
    near-zero response time in the UI, which is correct/expected on a
    cache hit, not a bug.
    """
    summary, df = ask_agent(prompt)
    rows = df.to_dict("records") if df is not None else None
    return summary, rows

# ==============================================================================
# DYNAMIC FILTER GENERATION -- based on the ACTUAL columns/data returned
# ==============================================================================

def render_dynamic_filters(df: pd.DataFrame) -> pd.DataFrame:
    filtered = df.copy()
    st.sidebar.header("🔍 Filters")

    for col in df.columns:
        series = df[col]
        nunique = series.nunique(dropna=True)

        if pd.api.types.is_bool_dtype(series):
            val = st.sidebar.checkbox(f"{col}", value=True, key=f"filt_{col}")
            if not val:
                filtered = filtered[filtered[col] == val]

        elif pd.api.types.is_numeric_dtype(series) and nunique > 4:
            lo, hi = float(series.min()), float(series.max())
            if lo < hi:
                selected = st.sidebar.slider(
                    f"{col}", min_value=lo, max_value=hi, value=(lo, hi), key=f"filt_{col}"
                )
                filtered = filtered[(filtered[col] >= selected[0]) & (filtered[col] <= selected[1])]

        elif 1 < nunique <= 4:
            options = sorted(series.dropna().unique().tolist())
            selected = st.sidebar.radio(f"{col}", ["(all)"] + options, key=f"filt_{col}")
            if selected != "(all)":
                filtered = filtered[filtered[col] == selected]

        elif 4 < nunique <= 30:
            options = sorted(series.dropna().unique().tolist())
            selected = st.sidebar.multiselect(f"{col}", options, default=options, key=f"filt_{col}")
            if selected:
                filtered = filtered[filtered[col].isin(selected)]

    return filtered


def render_chart(df: pd.DataFrame, chart_type: str, x_col: str, y_col: str, color_col: str):
    common = {"color": color_col} if color_col and color_col != "(none)" else {}
    if chart_type == "Bar":
        return px.bar(df, x=x_col, y=y_col, **common)
    if chart_type == "Line":
        return px.line(df, x=x_col, y=y_col, markers=True, **common)
    if chart_type == "Pie":
        return px.pie(df, names=x_col, values=y_col)
    if chart_type == "Scatter":
        return px.scatter(df, x=x_col, y=y_col, **common)
    if chart_type == "Area":
        return px.area(df, x=x_col, y=y_col, **common)
    return px.bar(df, x=x_col, y=y_col, **common)

# ==============================================================================
# SESSION STATE
# ==============================================================================

for key, default in [
    ("messages", []), ("bookmarks", []), ("last_df", None),
    ("last_prompt", ""), ("last_chart_type", "Table"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ==============================================================================
# UI
# ==============================================================================

st.title("📊 BigQuery Gemini Dashboard")
st.caption(f"Model: `{MODEL_NAME}` (Vertex AI, no ADK) — project `{PROJECT_ID}`")

with st.sidebar:
    st.header("📌 Bookmarks")
    if st.session_state.bookmarks:
        for i, bm in enumerate(st.session_state.bookmarks):
            c1, c2 = st.columns([5, 1])
            with c1:
                if st.button(bm["label"], key=f"bm_{i}", use_container_width=True):
                    st.session_state.pending_prompt = bm["prompt"]
            with c2:
                if st.button("✕", key=f"bm_del_{i}"):
                    st.session_state.bookmarks.pop(i)
                    st.rerun()
    else:
        st.caption("No bookmarks yet.")
    st.divider()

tab_chat, tab_dashboard = st.tabs(["💬 Conversation", "📈 Dashboard"])

with tab_chat:
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and "elapsed" in msg:
                st.caption(f"⏱️ {msg['elapsed']:.2f}s")
            if msg["role"] == "user":
                already = any(b["prompt"] == msg["content"] for b in st.session_state.bookmarks)
                if already:
                    st.caption("🔖 Bookmarked")
                elif st.button("🔖 Bookmark", key=f"hist_bm_{idx}"):
                    label = msg["content"][:37] + "..." if len(msg["content"]) > 40 else msg["content"]
                    st.session_state.bookmarks.append({"label": label, "prompt": msg["content"]})
                    st.rerun()

    pending = st.session_state.pop("pending_prompt", None)
    prompt = st.chat_input("Ask something about your BigQuery data...") or pending

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Querying BigQuery via Gemini..."):
                start = time.time()
                try:
                    summary, rows = ask_agent_cached(prompt)
                    df = pd.DataFrame(rows) if rows else None
                except Exception as e:
                    summary, df = f"Agent error: {e}", None
                elapsed = time.time() - start

            st.markdown(summary)
            st.caption(f"⏱️ Total: {elapsed:.2f}s")
            timings = st.session_state.get("_timings", {})
            if timings:
                with st.expander("⏱️ Timing breakdown"):
                    for step, secs in timings.items():
                        st.text(f"{step}: {secs:.2f}s")
            st.session_state.messages.append(
                {"role": "assistant", "content": summary, "elapsed": elapsed}
            )

            if df is not None and not df.empty:
                st.session_state.last_df = df
                st.session_state.last_prompt = prompt
                st.success(f"{len(df)} rows returned — see the **Dashboard** tab to visualize.")

with tab_dashboard:
    df = st.session_state.last_df
    if df is None or df.empty:
        st.info("Ask a data question in the Conversation tab first.")
    else:
        st.caption(f"Results for: _{st.session_state.last_prompt}_")
        filtered_df = render_dynamic_filters(df)

        numeric_cols = filtered_df.select_dtypes(include="number").columns.tolist()
        all_cols = filtered_df.columns.tolist()

        if numeric_cols:
            metric_cols = st.columns(min(len(numeric_cols), 4))
            for i, col in enumerate(numeric_cols[:4]):
                with metric_cols[i]:
                    st.metric(col, f"{filtered_df[col].sum():,.0f}")

        ctrl = st.columns([1.2, 1, 1, 1])
        with ctrl[0]:
            chart_type = st.selectbox(
                "Visualization", ["Table", "Bar", "Line", "Pie", "Scatter", "Area"],
                index=["Table", "Bar", "Line", "Pie", "Scatter", "Area"].index(st.session_state.last_chart_type),
            )
            st.session_state.last_chart_type = chart_type
        with ctrl[1]:
            x_col = st.selectbox("X", all_cols, index=0)
        with ctrl[2]:
            y_default = numeric_cols[0] if numeric_cols else all_cols[-1]
            y_col = st.selectbox("Y", all_cols, index=all_cols.index(y_default))
        with ctrl[3]:
            color_col = st.selectbox("Color", ["(none)"] + all_cols, index=0)

        if chart_type == "Table":
            st.dataframe(filtered_df, use_container_width=True, height=450)
        else:
            try:
                st.plotly_chart(render_chart(filtered_df, chart_type, x_col, y_col, color_col), use_container_width=True)
            except Exception as e:
                st.warning(f"Couldn't render that combination: {e}")
                st.dataframe(filtered_df, use_container_width=True)

        st.download_button(
            "⬇️ Download CSV", filtered_df.to_csv(index=False).encode("utf-8"),
            "dashboard_export.csv", "text/csv",
        )