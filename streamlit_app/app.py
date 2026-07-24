import streamlit as st
import vertexai
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

SERVICE_ACCOUNT_FILE = "runner_credentials.json"

USER_ID = "streamlit-user"

# ==============================================================================
# AUTHENTICATION
# ==============================================================================

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)

vertexai.init(
    project=PROJECT_ID,
    location=LOCATION,
    credentials=credentials,
)

# ==============================================================================
# LOAD REMOTE AGENT
# ==============================================================================

@st.cache_resource
def load_agent():
    return agent_engines.get(ENGINE_RESOURCE)

remote_agent = load_agent()

# ==============================================================================
# CREATE SESSION (ONLY ONCE)
# ==============================================================================

if "session_id" not in st.session_state:

    session = remote_agent.create_session(
        user_id=USER_ID
    )

    # Depending on SDK version, session may be dict or object
    if isinstance(session, dict):
        st.session_state.session_id = session.get("id")
    else:
        st.session_state.session_id = getattr(session, "id")

# ==============================================================================
# STREAMLIT UI
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

# Display previous conversation
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ==============================================================================
# CHAT
# ==============================================================================

prompt = st.chat_input("Ask something about your BigQuery data...")

if prompt:

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):

        placeholder = st.empty()

        answer = ""

        try:

            for event in remote_agent.stream_query(
                user_id=USER_ID,
                session_id=st.session_state.session_id,
                message=prompt,
            ):

                # Uncomment for debugging
                # st.write(event)

                if not isinstance(event, dict):
                    continue

                content = event.get("content")

                if not content:
                    continue

                parts = content.get("parts", [])

                for part in parts:

                    text = part.get("text")

                    if text:

                        answer += text

                        placeholder.markdown(answer)

            if answer.strip() == "":
                answer = "_No response returned from the agent._"
                placeholder.markdown(answer)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                }
            )

        except Exception as e:

            st.error("Agent Engine Error")
            st.exception(e)