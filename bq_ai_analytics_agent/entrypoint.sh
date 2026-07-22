#!/bin/bash
set -euxo pipefail

# 1. Update the fallback Project ID to your new project
PROJECT_ID="${PROJECT_ID:-agentic-ai-502518}"
REGION="${REGION:-europe-west1}"

echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"

python --version
adk --version

# Run serialization to ensure agent.pkl is up-to-date
python compile_agent.py

python - <<'PY'
from agent import root_agent
print("Agent loaded:", root_agent.name)
PY

# 2. Cleaned command targeting /app inside the container
adk deploy agent_engine \
  /app \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display_name="BigQuery_Analytics_Vertex_Agent"

echo "Deployment completed"
