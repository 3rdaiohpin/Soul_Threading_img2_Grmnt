# Hugging Face Spaces – Docker SDK
# Build: frontend once, then run FastAPI on port 7860 serving API + static SPA
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/yarn.lock* ./
RUN yarn install --frozen-lockfile --network-timeout 600000 || yarn install --network-timeout 600000
COPY frontend/ .
ENV REACT_APP_BACKEND_URL=""
RUN yarn build

FROM python:3.11-slim
WORKDIR /app

# System deps for OpenCV / Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r /tmp/req.txt \
 && pip install --no-cache-dir --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ emergentintegrations==0.2.0 || true

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
    PORT=7860

EXPOSE 7860

# Hugging Face Spaces expects the process on $PORT (default 7860)
CMD ["sh", "-c", "uvicorn hf_serve:app --host 0.0.0.0 --port ${PORT:-7860}"]
