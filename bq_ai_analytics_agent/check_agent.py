import os
import vertexai
from vertexai.preview import reasoning_engines

PROJECT_ID = "agentic-ai-502518"
LOCATION = "europe-west1"
ENGINE_ID = "5739512269641875456"

vertexai.init(project=PROJECT_ID, location=LOCATION)

print(f"Fetching active state for ID: {ENGINE_ID}...")
remote_agent = reasoning_engines.ReasoningEngine(
    f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}"
)

print("\n==============================================")
print("===      LIVE REASONING ENGINE STATUS      ===")
print("==============================================")
print(f"Agent Name:    {remote_agent.display_name}")

try:
    # Access the underlying proto message resource mapping directly
    raw_resource = remote_agent._gca_resource
    
    # 1. Print the actual cloud update timestamp
    update_time = getattr(raw_resource, "update_time", "Not available")
    print(f"Last Updated:  {update_time}")
    
    # 2. Extract internal package specifications safely
    spec = getattr(raw_resource, "spec", None)
    if spec and hasattr(spec, "package_spec"):
        print(f"Package GCS:   {spec.package_spec.pickle_object_gcs_uri}")
    else:
        print("Package Spec:  Managed via ADK App Layer")

except Exception as e:
    print(f"Metadata read warning: {str(e)}")

print("==============================================\n")
