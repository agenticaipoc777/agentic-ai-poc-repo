import os
import streamlit as st
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

# Relative path targeting your local JSON key profile instance
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "runner_credentials.json")
USER_ID = "streamlit-user"

# ==============================================================================
# DUAL-MODE LOGICAL AUTHENTICATION
# ==============================================================================

@st.cache_resource
def initialize_vertex_context():
    try:
        # Strategy A: If running locally and credentials file exists on disk
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            vertexai.init(
                project=PROJECT_ID,
                location=LOCATION,
                credentials=creds,
            )
        # Strategy B: If running on Cloud Run, fetch credentials implicitly via the environment service account
        else:
            # Set the default project variable context Google's SDK expects natively
            os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            vertexai.init(
                project=PROJECT_ID,
                location=LOCATION,
                credentials=creds,
            )
        return True
    except Exception as auth_err:
        st.error(f"Authentication Setup Failed: {auth_err}")
        return False

# Initialize authentication setup context
auth_status = initialize_vertex_context()

# ==============================================================================
# LOAD REMOTE AGENT
# ==============================================================================

@st.cache_resource
def load_agent():
    if auth_status:
        # The SDK internally maps the resource string layout automatically
        return agent_engines.get(ENGINE_RESOURCE)
    return None

remote_agent = load_agent()

# ==============================================================================
# STREAMLIT UI LAYOUT STRUCTURE
# ==============================================================================

st.set_page_config(
    page_title="BigQuery Analytics Agent",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 BigQuery Analytics Agent")
st.caption("Powered by Vertex AI Agent Engine + Google ADK")

if "messages" not in st.session_state:
    st.session_state.messages = []

# ==============================================================================
# CREATE CONVERSATIONAL SESSION (DEFERRED UNTIL REASONING ENGINE LOADS)
# ==============================================================================

if remote_agent and "session_id" not in st.session_state:
    try:
        session = remote_agent.create_session(user_id=USER_ID)
        
        # Safe extraction based on runtime object typing boundaries
        if isinstance(session, dict):
            st.session_state.session_id = session.get("id")
        else:
            st.session_state.session_id = getattr(session, "id", None) or session.name.split("/")[-1]
    except Exception as session_err:
        st.error(f"Failed to generate persistent session context parameters: {session_err}")

# Display previous conversation logs
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==============================================================================
# CHAT PROCESSING PIPELINE
# ==============================================================================

prompt = st.chat_input("Ask something about your BigQuery data...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        answer = ""

        if remote_agent and "session_id" in st.session_state:
            try:
                # Execute streaming call utilizing explicit keyword argument parameters matching ADK
                for event in remote_agent.stream_query(
                    user_id=USER_ID,
                    session_id=st.session_state.session_id,
                    message=prompt,
                ):
                    # Robust parsing to catch variations in how chunks surface (dict vs schema objects)
                    content = getattr(event, "content", None) if not isinstance(event, dict) else event.get("content")
                    
                    if content:
                        parts = content.get("parts", []) if isinstance(content, dict) else getattr(content, "parts", [])
                        for part in parts:
                            text = part.get("text") if isinstance(part, dict) else getattr(part, "text", "")
                            if text:
                                answer += text
                                placeholder.markdown(answer + "▌")

                if answer.strip() == "":
                    answer = "_No response returned from the agent._"
                
                placeholder.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})

            except Exception as e:
                st.error("Agent Engine Execution Crash Detected")
                st.exception(e)
        else:
            st.error("Cannot query agent engine: Client connection context not established.")
