# NEXUS-HEAL — single-container deployment image.
#
# Used by Hugging Face Spaces (Docker SDK), Fly.io, Cloud Run, or any
# generic Docker host. Render auto-detects render.yaml first and doesn't
# need this image, but it works there too.
#
# Layout: FastAPI on the loopback (127.0.0.1:8000) + Streamlit on $PORT
# (HF injects 7860 by default; override with -e PORT=... elsewhere).
# start.sh boots both processes and handles SIGTERM cleanly.

FROM python:3.13-slim

WORKDIR /app

# System deps — curl for occasional health-probe / smoke-test use; CA
# certificates so the Groq SDK and HuggingFace ChromaDB downloads work.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps in a separate layer so a code-only change doesn't
# bust the dependency cache.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Sensible defaults for HF Spaces. The host platform's $PORT overrides
# this at runtime; the rest can be overridden via Space "Variables".
ENV PORT=7860 \
    NEXUS_API_URL=http://127.0.0.1:8000 \
    FASTAPI_HOST=127.0.0.1 \
    FASTAPI_PORT=8000 \
    CHROMA_PATH=/tmp/chroma_db \
    NEXUS_DB_PATH=/tmp/nexus_alerts.db \
    PYTHONUNBUFFERED=1

EXPOSE 7860

CMD ["bash", "start.sh"]
