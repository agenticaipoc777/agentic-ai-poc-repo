import os
import vertexai
from vertexai.preview import reasoning_engines
from agent import BigQueryAnalyticsAgent

PROJECT_ID = "agentic-ai-502518"
LOCATION = "europe-west1"
ENGINE_ID = "5739512269641875456"

# Initialize backend connection
vertexai.init(project=PROJECT_ID, location=LOCATION)

print("Fetching active engine metadata from Vertex AI...")
remote_agent = reasoning_engines.ReasoningEngine(
    f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}"
)

print("\n==============================================")
print("===     ADK AGENT LIVE DEPLOYMENT STATE    ===")
print("==============================================")

# 1. Extract the Gemini Model directly from the instantiated code class
try:
    local_agent_instance = BigQueryAnalyticsAgent()
    # Read the explicit model parameter bound inside your class structure
    print(f"Gemini Model:   {local_agent_instance.model}")
except Exception as e:
    print(f"Could not read local file variables: {str(e)}")

# 2. Extract the Live Server Update Timestamp from the raw Google API proto resource
try:
    raw_resource = remote_agent._gca_resource
    print(f"Last Updated:   {getattr(raw_resource, 'update_time', 'Unknown')}")
except Exception as e:
    print(f"Could not read cloud timestamps: {str(e)}")

print("==============================================\n")
