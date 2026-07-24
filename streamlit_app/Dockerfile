FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first to utilize Docker build layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files (app.py, runner_credentials.json, etc.) explicitly into /app
COPY . /app

EXPOSE 8080

# Clean, robust production execution entrypoint
ENTRYPOINT ["streamlit", "run", "/app/app.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.enableCORS=false", "--server.enableXsrfProtection=false", "--browser.gatherUsageStats=false"]
