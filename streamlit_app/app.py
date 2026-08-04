import os
import re
import json
import uuid
import time
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
import vertexai
import google.auth
from google.oauth2 import service_account
from vertexai import agent_engines

# ==============================================================================
# CONFIGURATION
# ==============================================================================

PROJECT_ID = "agentic-ai-502518"
LOCATION = "europe-west1"

ENGINE_RESOURCE = (
    "projects/661224241135/"
    "locations/europe-west1/"
    "reasoningEngines/5739512269641875456"
)

SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "runner_credentials.json")
USER_ID = "streamlit-user"

st.set_page_config(
    page_title="BigQuery Analytics Dashboard",
    page_icon="📊",
    layout="wide",
)

# ==============================================================================
# STYLE
# ==============================================================================

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; }
    div[data-testid="stMetric"] {
        background: #12161c;
        border: 1px solid #262b33;
        border-radius: 10px;
        padding: 14px 18px;
    }
    .dash-card {
        background: #12161c;
        border: 1px solid #262b33;
        border-radius: 10px;
        padding: 16px 18px;
        margin-bottom: 14px;
    }
    .bookmark-pill {
        display: inline-block;
        background: #1c2128;
        border: 1px solid #30363d;
        border-radius: 999px;
        padding: 4px 12px;
        margin: 3px 4px 3px 0;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# AUTH
# ==============================================================================

@st.cache_resource
def initialize_vertex_context():
    try:
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=creds)
        else:
            os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=creds)
        return True
    except Exception as auth_err:
        st.error(f"Authentication Setup Failed: {auth_err}")
        return False


auth_status = initialize_vertex_context()


@st.cache_resource
def load_agent():
    if auth_status:
        return agent_engines.get(ENGINE_RESOURCE)
    return None


remote_agent = load_agent()

# ==============================================================================
# SESSION STATE
# ==============================================================================

if "messages" not in st.session_state:
    st.session_state.messages = []
if "bookmarks" not in st.session_state:
    st.session_state.bookmarks = []
if "last_df" not in st.session_state:
    st.session_state.last_df = None
if "last_chart_type" not in st.session_state:
    st.session_state.last_chart_type = "Table"

if remote_agent and "session_id" not in st.session_state:
    try:
        session = remote_agent.create_session(user_id=USER_ID)
        if isinstance(session, dict):
            st.session_state.session_id = session.get("id")
        else:
            st.session_state.session_id = getattr(session, "id", None) or session.name.split("/")[-1]
    except Exception as session_err:
        st.error(f"Failed to generate persistent session context parameters: {session_err}")

# ==============================================================================
# HELPERS: extracting structured data out of an agent's text response
# ==============================================================================


def extract_dataframe(answer_text: str):
    """
    Best-effort extraction of tabular data from the agent's reply.
    Tries, in order:
      1. A fenced ```json array-of-objects block
      2. A bare JSON array-of-objects anywhere in the text
      3. A markdown pipe table (| col | col | ... )
    Returns a pandas DataFrame, or None if nothing parseable was found.
    This is a best-effort bridge for an agent that currently returns
    prose -- if the agent is updated to emit structured JSON
    consistently (recommended), this becomes a straightforward parse
    instead of a heuristic one.
    """
    # 1 & 2: JSON array of objects, fenced or bare
    json_candidates = re.findall(r"```json\s*(\[.*?\])\s*```", answer_text, re.DOTALL)
    json_candidates += re.findall(r"(\[\s*\{.*?\}\s*\])", answer_text, re.DOTALL)
    for candidate in json_candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return pd.DataFrame(data)
        except (json.JSONDecodeError, ValueError):
            continue

    # 1b: a single fenced JSON object (not array-wrapped) -- can happen
    # with single-row aggregate results. Wrap it into a one-row frame
    # rather than failing to parse it at all.
    single_obj_candidates = re.findall(r"```json\s*(\{.*?\})\s*```", answer_text, re.DOTALL)
    for candidate in single_obj_candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and data:
                return pd.DataFrame([data])
        except (json.JSONDecodeError, ValueError):
            continue

    # 3: markdown pipe table
    lines = [l for l in answer_text.splitlines() if l.strip().startswith("|")]
    if len(lines) >= 2:
        try:
            header = [c.strip() for c in lines[0].strip("|").split("|")]
            data_lines = [l for l in lines[1:] if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", l)]
            rows = []
            for line in data_lines:
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) == len(header):
                    rows.append(cells)
            if rows:
                df = pd.DataFrame(rows, columns=header)
                for col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="ignore")
                return df
        except Exception:
            return None

    return None


def render_chart(df: pd.DataFrame, chart_type: str, x_col: str, y_col: str, color_col: str | None):
    common = dict(color=color_col if color_col and color_col != "(none)" else None)
    if chart_type == "Bar":
        fig = px.bar(df, x=x_col, y=y_col, **common)
    elif chart_type == "Line":
        fig = px.line(df, x=x_col, y=y_col, markers=True, **common)
    elif chart_type == "Pie":
        fig = px.pie(df, names=x_col, values=y_col)
    elif chart_type == "Scatter":
        fig = px.scatter(df, x=x_col, y=y_col, **common)
    else:
        fig = px.bar(df, x=x_col, y=y_col, **common)
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=420,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e6e6e6"),
    )
    return fig


def query_agent(prompt: str) -> str:
    answer = ""
    for event in remote_agent.stream_query(
        user_id=USER_ID,
        session_id=st.session_state.session_id,
        message=prompt,
    ):
        content = getattr(event, "content", None) if not isinstance(event, dict) else event.get("content")
        if content:
            parts = content.get("parts", []) if isinstance(content, dict) else getattr(content, "parts", [])
            for part in parts:
                text = part.get("text") if isinstance(part, dict) else getattr(part, "text", "")
                if text:
                    answer += text
    return answer.strip()


# ==============================================================================
# SIDEBAR: filters + bookmarks
# ==============================================================================

with st.sidebar:
    st.header("📌 Bookmarks")
    if st.session_state.bookmarks:
        for i, bm in enumerate(st.session_state.bookmarks):
            cols = st.columns([5, 1])
            with cols[0]:
                if st.button(bm["label"], key=f"bm_{i}", use_container_width=True):
                    st.session_state.pending_prompt = bm["prompt"]
            with cols[1]:
                if st.button("✕", key=f"bm_del_{i}"):
                    st.session_state.bookmarks.pop(i)
                    st.rerun()
    else:
        st.caption("No bookmarks yet. Save a question after asking it.")

    st.divider()
    st.header("🔍 Result Filters")
    st.caption("Applies to the most recent data result below.")

    active_df = st.session_state.last_df
    filtered_df = active_df

    if active_df is not None and not active_df.empty:
        filter_col = st.selectbox(
            "Filter column", ["(none)"] + list(active_df.columns), key="filter_col"
        )
        if filter_col != "(none)":
            unique_vals = sorted(active_df[filter_col].dropna().unique().tolist())
            selected_vals = st.multiselect(
                f"Values for {filter_col}", unique_vals, default=unique_vals, key="filter_vals"
            )
            if selected_vals:
                filtered_df = active_df[active_df[filter_col].isin(selected_vals)]
    else:
        st.caption("Ask a data question to enable filters.")

# ==============================================================================
# HEADER
# ==============================================================================

st.title("📊 BigQuery Analytics Dashboard")
st.caption("Powered by Vertex AI Agent Engine + Google ADK")

tab_chat, tab_dashboard = st.tabs(["💬 Conversation", "📈 Dashboard"])

# ==============================================================================
# CHAT TAB
# ==============================================================================

with tab_chat:
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "user":
                already_bookmarked = any(
                    bm["prompt"] == message["content"] for bm in st.session_state.bookmarks
                )
                if already_bookmarked:
                    st.caption("🔖 Bookmarked")
                elif st.button("🔖 Bookmark this question", key=f"hist_bookmark_{idx}"):
                    label = message["content"] if len(message["content"]) <= 40 else message["content"][:37] + "..."
                    st.session_state.bookmarks.append(
                        {"label": label, "prompt": message["content"], "saved_at": datetime.now().isoformat()}
                    )
                    st.rerun()

    pending = st.session_state.pop("pending_prompt", None)
    prompt = st.chat_input("Ask something about your BigQuery data...") or pending

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            if remote_agent and "session_id" in st.session_state:
                try:
                    answer = query_agent(prompt)
                    if not answer:
                        answer = "_No response returned from the agent._"
                    placeholder.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})

                    df = extract_dataframe(answer)
                    if df is not None and not df.empty:
                        st.session_state.last_df = df
                        st.session_state.last_prompt = prompt
                        st.success(
                            f"Parsed {len(df)} rows × {len(df.columns)} columns — "
                            "open the **Dashboard** tab to visualize and filter."
                        )

                    # FIX: use a stable id captured once (not a live
                    # len() computed on every rerun) so this button's
                    # key doesn't shift out from under it, and check
                    # against a set of already-bookmarked prompts so
                    # clicking doesn't silently no-op on a rerun.
                    turn_id = st.session_state.get("_turn_counter", 0)
                    st.session_state["_turn_counter"] = turn_id + 1
                    already_bookmarked = any(
                        bm["prompt"] == prompt for bm in st.session_state.bookmarks
                    )
                    bm_cols = st.columns([1, 5])
                    with bm_cols[0]:
                        if already_bookmarked:
                            st.caption("🔖 Bookmarked")
                        elif st.button("🔖 Bookmark this", key=f"bookmark_{turn_id}"):
                            label = prompt if len(prompt) <= 40 else prompt[:37] + "..."
                            st.session_state.bookmarks.append(
                                {"label": label, "prompt": prompt, "saved_at": datetime.now().isoformat()}
                            )
                            st.rerun()

                except Exception as e:
                    st.error("Agent Engine Execution Crash Detected")
                    st.exception(e)
            else:
                st.error("Cannot query agent engine: Client connection context not established.")

# ==============================================================================
# DASHBOARD TAB
# ==============================================================================

with tab_dashboard:
    df = filtered_df if "filtered_df" in dir() else st.session_state.last_df

    if df is None or df.empty:
        st.info(
            "No structured data yet. Ask something like "
            "*\"get me sales by store as a table\"* or "
            "*\"top 5 products by revenue\"* in the Conversation tab first."
        )
    else:
        st.caption(f"Showing results for: _{st.session_state.get('last_prompt', '')}_")

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        all_cols = df.columns.tolist()

        if numeric_cols:
            metric_cols = st.columns(min(len(numeric_cols), 4))
            for i, col in enumerate(numeric_cols[:4]):
                with metric_cols[i]:
                    st.metric(col, f"{df[col].sum():,.0f}")

        st.markdown('<div class="dash-card">', unsafe_allow_html=True)
        ctrl_cols = st.columns([1.2, 1, 1, 1])

        # Prefer an obviously time-like column as the default X-axis
        # (year, date, month, period, etc.) over just picking column 0
        # -- this makes results like a year-over-year breakdown chart
        # sensibly on first render, without the user needing to
        # manually swap the X-axis dropdown every time.
        time_like_pattern = re.compile(r"(year|date|month|period|quarter|week|day)", re.IGNORECASE)
        time_like_cols = [c for c in all_cols if time_like_pattern.search(c)]
        default_x = time_like_cols[0] if time_like_cols else all_cols[0]

        with ctrl_cols[0]:
            chart_type = st.selectbox(
                "Visualization", ["Table", "Bar", "Line", "Pie", "Scatter"],
                index=["Table", "Bar", "Line", "Pie", "Scatter"].index(st.session_state.last_chart_type),
            )
            st.session_state.last_chart_type = chart_type
        with ctrl_cols[1]:
            x_col = st.selectbox("X / Category", all_cols, index=all_cols.index(default_x))
        with ctrl_cols[2]:
            y_candidates = [c for c in numeric_cols if c != default_x] or numeric_cols
            y_default = y_candidates[0] if y_candidates else all_cols[-1]
            y_col = st.selectbox("Y / Value", all_cols, index=all_cols.index(y_default))
        with ctrl_cols[3]:
            color_col = st.selectbox("Color / Group by", ["(none)"] + all_cols, index=0)

        st.markdown("</div>", unsafe_allow_html=True)

        if chart_type == "Table":
            st.dataframe(df, use_container_width=True, height=460)
        else:
            try:
                fig = render_chart(df, chart_type, x_col, y_col, color_col)
                st.plotly_chart(fig, use_container_width=True)
            except Exception as chart_err:
                st.warning(f"Couldn't render that chart combination: {chart_err}")
                st.dataframe(df, use_container_width=True)

        with st.expander("View raw data table"):
            st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download CSV", csv, "dashboard_export.csv", "text/csv")