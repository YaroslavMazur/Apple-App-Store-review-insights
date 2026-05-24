FROM python:3.11-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# hdbscan (a BERTopic dependency) is a C extension. Most platforms have wheels,
# but if uv falls back to a source build we need a compiler + python headers.
# Kept in the builder stage only; runtime image stays slim.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml ./
# uv.lock is optional on first build; copy if present
COPY uv.loc[k] ./

RUN uv sync --no-dev --no-install-project

COPY app ./app
RUN uv sync --no-dev

# ── Stage 2: warm-up — pre-download HF model weights ──────────────────────────
# Bakes the sentiment + embedding models into the image so Cloud Run cold
# starts don't re-download ~500 MB on every fresh instance. Adds ~500 MB to the
# final image but predictable user-facing latency wins.
FROM python:3.11-slim AS warmup

ENV PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf_cache \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv

RUN mkdir -p /opt/hf_cache && \
    python -c "from transformers import pipeline; \
pipeline('sentiment-analysis', model='nlptown/bert-base-multilingual-uncased-sentiment', tokenizer='nlptown/bert-base-multilingual-uncased-sentiment'); \
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# ── Stage 3: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENV=prod \
    HF_HOME=/opt/hf_cache \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_OFFLINE=1

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/app /app/app
COPY --from=warmup /opt/hf_cache /opt/hf_cache

# Pre-create /app/data so the named compose volume inherits the right ownership.
# Without this, Docker creates an empty root-owned volume and SQLite cannot write.
RUN mkdir -p /app/data && chown -R app:app /opt/hf_cache /app
USER app
EXPOSE 8000

# Cloud Run injects $PORT; default to 8000 for local docker run.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
