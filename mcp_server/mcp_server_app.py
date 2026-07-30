import os
from fastmcp import FastMCP
from google.cloud import bigquery

mcp = FastMCP("BigQuery Analytics Engine")

@mcp.tool()
def run_analytics_query(sql_query: str) -> str:
    """Executes a structured analytical SQL query against the corporate data warehouse."""
    client = bigquery.Client()
    try:
        query_job = client.query(sql_query)
        results = query_job.result()
        return str([dict(row) for row in results])
    except Exception as e:
        return f"Query Failed: {str(e)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    mcp.run(transport="sse", host="0.0.0.0", port=port)

