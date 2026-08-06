# CUDA-enabled base image with PyTorch pre-installed, matching what
# Cloud Run's L4 GPU expects (NVIDIA driver 535.x / CUDA 12.2 per
# Cloud Run's current GPU docs).
FROM nvidia/cuda:12.2.2-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the model into the image at BUILD time, not runtime. This is
# the actual mechanism behind "fully offline" here -- without this,
# the container would download ~14GB from Hugging Face Hub on every
# cold start (Cloud Run scaling from zero), which is slow and defeats
# the point of an offline model. MODEL_ID must match what app.py uses
# at runtime -- passed as a build arg so both stay in sync from one
# source of truth (your deploy command), not hardcoded twice.
ENV PYTHONUNBUFFERED=1
ARG MODEL_ID=Qwen/Qwen2.5-7B-Instruct
ENV MODEL_ID=${MODEL_ID}
RUN python3 -c "\
from transformers import AutoModelForCausalLM, AutoTokenizer; \
AutoTokenizer.from_pretrained('${MODEL_ID}'); \
AutoModelForCausalLM.from_pretrained('${MODEL_ID}', torch_dtype='auto')"

COPY app.py rag.py .
COPY docs/ ./docs/

EXPOSE 8080

# --server.address=0.0.0.0 is required for Cloud Run (it can't reach
# a service only bound to localhost); --server.port must match
# Cloud Run's expected $PORT, which is 8080 by default.
ENTRYPOINT ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --browser.gatherUsageStats=false"]