import os
from dotenv import load_dotenv

# Path management: Load the local configuration before any SDK bootstrap occurs
load_dotenv()

# Force enterprise routing parameters to target your explicit workspace values
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ["GOOGLE_CLOUD_PROJECT"] = "agentic-ai-502518"
os.environ["GOOGLE_CLOUD_LOCATION"] = "europe-west1"

from google.adk.agents import Agent
from google.adk.tools.bigquery import BigQueryToolset

# ====================================================================
# 1. ADK-COMPLIANT PROJECT-WIDE ANALYTICS AGENT
# ====================================================================
class BigQueryAnalyticsAgent(Agent):
    def __init__(self):
        super().__init__(
            name="bq_ai_analytics_agent",
            model="gemini-2.5-flash", 
            description="Agent with direct access to discover and run analytics across all datasets inside agentic-ai-502518.",
            instruction="""
You are an expert data analyst with system access to a Google Cloud BigQuery project.

### CORE PROTOCOLS:
- Your target Project ID environment is strictly: 'agentic-ai-502518'.
- You have access to view and analyze ALL datasets resident inside this specific project.
- You must dynamically inspect the tables and schemas using the provided BigQueryToolset to find out what data is available. Do not guess names.
- Always use standard GoogleSQL syntax to structure your metrics calculations.
- If a user requests information, locate the relevant dataset first, review its column layout, and execute clean analytical query jobs.
""",
            # FIXED: Removed the invalid project_id argument. 
            # The toolset automatically adopts the project declared above in os.environ.
            tools=[BigQueryToolset()],
        )

# ====================================================================
# 2. EXPOSE THE SYSTEM COMPLIANT ROOT RUNTIME OBJECT
# ====================================================================
root_agent = BigQueryAnalyticsAgent()

