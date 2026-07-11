# Hugging Face Spaces – Docker SDK with ZeroGPU + Ollama LLaVA
FROM nvidia/cuda:12.1.0-devel-ubuntu22.04 as ollama-builder

# Install Ollama in builder stage
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://ollama.ai/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*

# Build frontend (CPU)
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/yarn.lock* ./
RUN yarn install --frozen-lockfile --network-timeout 600000 || yarn install --network-timeout 600000
COPY frontend/ .
ENV REACT_APP_BACKEND_URL=""
RUN yarn build

# Final image: Python + CUDA + Ollama
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3-pip \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    curl git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/python3.11 /usr/bin/python

# Copy Ollama from builder
COPY --from=ollama-builder /usr/local/bin/ollama /usr/local/bin/ollama
COPY --from=ollama-builder /etc/profile.d/ollama.sh /etc/profile.d/ollama.sh

# Python deps (CPU base)
COPY backend/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt

# AI stack (GPU-friendly, optional)
COPY requirements-ai.txt /tmp/req-ai.txt
RUN pip install --no-cache-dir -r /tmp/req-ai.txt || true

# App code + data
COPY backend/ /app/backend/
COPY hf_serve.py /app/hf_serve.py

# Built frontend
COPY --from=frontend /build/build /app/frontend/build

# Runtime env
ENV MONGO_URL="mongodb://localhost:27017" \
    DB_NAME="soul_threading" \
    CORS_ORIGINS="*" \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    OLLAMA_HOST="127.0.0.1:11434"

EXPOSE 7860

# Start Ollama + pull model + run FastAPI
CMD ["sh", "-c", "\
    echo 'Starting Ollama...' && \
    ollama serve > /tmp/ollama.log 2>&1 & \
    OLLAMA_PID=$! && \
    sleep 8 && \
    echo 'Pulling LLaVA model...' && \
    ollama pull llava:7b && \
    echo 'Starting Soul Threading API...' && \
    uvicorn hf_serve:app --host 0.0.0.0 --port ${PORT:-7860} && \
    wait $OLLAMA_PID \
"]
