import os
# FORCE VERTEX AI ENTERPRISE ROUTING BEFORE ANY ADK INITIALIZATION OCCURS
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ["GOOGLE_CLOUD_PROJECT"] = "agentic-ai-502518"
os.environ["GOOGLE_CLOUD_LOCATION"] = "europe-west1"

from dotenv import load_dotenv
from google.cloud import bigquery
from google.adk.agents import Agent
from google.adk.tools.bigquery import BigQueryToolset

load_dotenv()

# ====================================================================
# 1. ADK-COMPLIANT CUSTOM AGENT CLASS
# ====================================================================
class BigQueryAnalyticsAgent(Agent):
    def __init__(self):
        super().__init__(
            name="bq_ai_analytics_agent",
            model="gemini-2.5-flash", 
            description="Agent with direct access to discover and run analytics across all datasets inside your project.",
            instruction="""
You are an expert data analyst with system access to a Google Cloud BigQuery project.

### CORE PROTOCOLS:
- Your target Project ID environment is strictly: 'agentic-ai-502518'.
- You must dynamically inspect the tables and schemas using the provided BigQueryToolset or discover_project_datasets tool to find out what data is available. Do not guess names.
- Always use standard GoogleSQL syntax to structure your metrics calculations.
""",
            # Bind the standard toolset alongside the self-contained execution scope tool
            tools=[BigQueryToolset(), self.discover_project_datasets],
        )

    def discover_project_datasets(self) -> list:
        """
        Lists all available dataset IDs inside the target BigQuery project.
        Use this first to find out what data regions exist before querying.
        """
        # Forces the internal bigquery connection layer to query the EU multi-region location
        bq_client = bigquery.Client(project='agentic-ai-502518', location='EU')
        try:
            datasets = list(bq_client.list_datasets())
            if not datasets:
                return ["No datasets found in the EU multi-region for this project."]
            return [ds.dataset_id for ds in datasets]
        except Exception as e:
            return [f"Error connecting to BigQuery metadata layers: {str(e)}"]

# ====================================================================
# 2. EXPOSE COMPLIANT ROOT OBJECT
# ====================================================================
root_agent = BigQueryAnalyticsAgent()
app = root_agent
