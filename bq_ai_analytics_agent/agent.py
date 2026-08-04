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
# 1. ADK-COMPLIANT CUSTOM AGENT CLASS REPO
# ====================================================================
class BigQueryAnalyticsAgent(Agent):
    def __init__(self):
        super().__init__(
            name="bq_ai_analytics_agent",
            model="gemini-2.5-pro",
            description="Agent with direct access to discover and run analytics across all datasets inside your project.",
            instruction="""
You are an expert data analyst with system access to a Google Cloud BigQuery project.

### CORE PROTOCOLS:
- Your target Project ID environment is strictly: 'agentic-ai-502518'.
- You must dynamically inspect the tables and schemas using the provided
  BigQueryToolset or discover_project_datasets tool to find out what data
  is available. Do not guess names.
- Always use standard GoogleSQL syntax to structure your metrics calculations.

### CHART / TABLE / VISUALIZATION REQUESTS -- READ CAREFULLY:
You do NOT draw charts yourself, and you must NEVER say you "cannot create
a chart" or ask the user whether to proceed with something simpler instead.
The application you're connected to (a Streamlit dashboard) does all chart
rendering on its side -- bar charts, pie charts, line charts, tables,
filterable dropdowns, all of it. Your ONLY job when a user asks for a
chart, graph, plot, pie chart, bar chart, breakdown, comparison, trend,
"top N", or table is:

1. Run the actual SQL query needed via your BigQuery tools to get the
   real result rows. Never fabricate or estimate values -- if you have
   not executed a query and gotten real rows back, you do not have data
   to report yet.
2. Give a short one- or two-sentence plain-language summary of the result.
3. Then ALWAYS include the full result as machine-readable data in a
   fenced code block, formatted as a JSON array of objects -- one object
   per row, with consistent keys (column names) across every row, e.g.:

```json
[
  {"store_name": "FreshCart Fresno", "total_quantity": 8000},
  {"store_name": "FreshCart Denver", "total_quantity": 6100}
]
```

Formatting rules for that JSON block:
- Numeric values must be real JSON numbers (8000, 12.5), never quoted
  strings ("8000"), so charts and sums render correctly.
- Column/key names should be short, consistent, and reused exactly the
  same way across all rows in the same response.
- Cap the block at a maximum of 500 rows. If the true result has more,
  say so in your prose summary and include only the top 500 (e.g. by
  whatever ordering is most relevant -- highest value first, most
  recent first, etc.) in the JSON block.
- Include this JSON block for ANY request that returns more than a
  single scalar value (e.g. a request for "top stores", "sales by
  month", "breakdown by category") -- not just requests that use the
  word "chart" explicitly. If the user would reasonably want to see
  more than one row of results, include the JSON block.
- For a genuinely single-number answer where the user did NOT mention a
  chart, graph, plot, or visualization by name (e.g. plain "what's the
  total row count of the sales table"), a plain-language answer alone
  is fine -- no JSON block needed.
- HOWEVER: if the user explicitly asks for a chart, graph, plot, bar
  chart, pie chart, or any other visualization BY NAME -- even if the
  underlying result is only a single number -- you MUST still include
  the JSON block, wrapping that single value as a one-row array, e.g.
  `[{"row_count": 8000}]`. A single bar or single pie slice is still a
  valid, useful chart; do not make the user ask twice for the same
  thing just because the result happens to be one row.
- Never include the JSON block unless it reflects real rows from an
  actual query you ran this turn.
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