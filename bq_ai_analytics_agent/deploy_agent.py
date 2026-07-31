import os
import vertexai
from vertexai.preview import reasoning_engines
from agent import BigQueryAnalyticsAgent  # Imports your custom agent class

# 1. Initialize environment variables passed from GitHub Actions
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "agentic-ai-502518")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")
REASONING_ENGINE_ID = "5739512269641875456"  # Your engine ID from the screenshot

vertexai.init(project=PROJECT_ID, location=LOCATION)

# 2. Instantiate your ADK agent instance
print("Initializing BigQuery_Analytics_Vertex_Agent...")
root_agent = BigQueryAnalyticsAgent()

# 3. Target your existing Reasoning Engine resource to update it
resource_name = f"projects/661224241135/locations/{LOCATION}/reasoningEngines/{REASONING_ENGINE_ID}"
print(f"Deploying updates directly to: {resource_name}")

try:
    remote_agent = reasoning_engines.ReasoningEngine(resource_name)
    # Perform an in-place update of the agent logic and configurations
    remote_agent.update(
        reasoning_class=root_agent,
        requirements=[
            "google-cloud-aiplatform[reasoningengine]",
            "google-cloud-bigquery",
            "python-dotenv"
        ]
    )
    print("Successfully deployed Agent Engine via CI/CD!")
except Exception as e:
    print(f"Deployment failed: {str(e)}")
    raise e
