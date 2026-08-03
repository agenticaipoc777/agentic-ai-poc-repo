FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir google-cloud-bigquery
COPY app.py .
ENV PG_PROXY_LISTEN_HOST=0.0.0.0
ENV PG_PROXY_LISTEN_PORT=5432
ENV PG_PROXY_PROJECT_ID=agentic-ai-502518
ENV PG_PROXY_LOCATION=europe-west1
EXPOSE 5432
CMD ["python", "app.py"]
