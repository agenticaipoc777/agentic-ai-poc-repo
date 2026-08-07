FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV GCP_PROJECT_ID=agentic-ai-502518
ENV GCP_LOCATION=europe-west1
ENV BQ_LOCATION=EU
ENV GEMINI_MODEL=gemini-2.5-pro

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --browser.gatherUsageStats=false"]