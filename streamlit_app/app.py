import streamlit as st
from google.cloud import aiplatform

# Configure your explicit Google Cloud platform locations
PROJECT_ID = "66122424135"
LOCATION = "europe-west1"
REASONING_ENGINE_ID = "5739512269641875456"

# Initialize Vertex AI SDK context 
aiplatform.init(project=PROJECT_ID, location=LOCATION)

st.set_page_config(page_title="BigQuery AI Assistant", page_icon="📊", layout="centered")
st.title("📊 BigQuery Analytics Assistant")
st.caption("Powered by Vertex AI Agent Runtime Reasoning Engine (ADK)")

# Initialize session history state array
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display prior chat bubbles
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Process incoming user prompts
if user_input := st.chat_input("Ask a question about your datasets..."):
    st.chat_message("user").markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        response_box = st.empty()
        with st.spinner("Analyzing BigQuery data structures..."):
            try:
                # Target resource tracking link path
                engine_path = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{REASONING_ENGINE_ID}"
                agent_engine = aiplatform.ReasoningEngine(engine_path)
                
                # ADK engines execute queries mapping input payloads to flat dictionary results
                response = agent_engine.query(input=user_input)
                
                # Extract text output safely from the response structure
                output_text = response.get("output") if isinstance(response, dict) else str(response)
                
                response_box.markdown(output_text)
                st.session_state.messages.append({"role": "assistant", "content": output_text})
                
            except Exception as e:
                response_box.error(f"⚠️ Runtime Query Failed: {str(e)}")
