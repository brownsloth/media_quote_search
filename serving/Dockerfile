FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY serving/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/quote_lib ./src/quote_lib
COPY data/netflix ./data/netflix
COPY scripts/data/fetch_archer_netflix_ids.py ./scripts/data/fetch_archer_netflix_ids.py
COPY serving/api ./serving/api
COPY serving/config ./serving/config
COPY serving/download_artifacts.py ./serving/download_artifacts.py
COPY serving/entrypoint.sh ./serving/entrypoint.sh

ARG HF_ARTIFACTS_REPO=1starun8-research/archer-quote-index
ENV HF_ARTIFACTS_REPO=${HF_ARTIFACTS_REPO}
ENV SERVE_ARTIFACTS_DIR=/app/serving/artifacts
ENV SERVE_INDEX_DIR=/app/serving/artifacts/index
ENV NETFLIX_MAPPING_PATH=/app/serving/artifacts/netflix/archer_episodes.json
ENV PYTHONPATH=/app/src:/app
ENV EVENT_LOG_PATH=/tmp/quote_memory_events.jsonl
# Set on Railway: CORS_ORIGINS, NETFLIX_ID, SECURE_NETFLIX_ID, HF_TOKEN
# Feedback → Dropbox: DROPBOX_ACCESS_TOKEN, DROPBOX_FEEDBACK_PATH

# Index pulled at build time from Hugging Face (~850 MB for universal + Archer).
RUN python serving/download_artifacts.py

RUN chmod +x serving/entrypoint.sh

EXPOSE 8000

WORKDIR /app/serving/api
CMD ["bash", "/app/serving/entrypoint.sh"]
