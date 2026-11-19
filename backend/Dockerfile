# syntax=docker/dockerfile:1
# The API: FastAPI + the embedding model, baked in so the container never downloads it.
# Build from the repo root (it needs scripts/ and sample_data/):
#   docker build -f backend/Dockerfile -t resume-matcher-backend .
FROM python:3.12.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    HF_HOME=/opt/huggingface

WORKDIR /app

# 1. Dependencies, from pyproject.toml's exact pins (this layer is cached until they change).
#    CPU-only torch first: the default Linux wheel pulls in ~2 GB of CUDA libraries.
COPY backend/pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" \
        > /tmp/requirements.txt \
    && pip install "$(grep '^torch==' /tmp/requirements.txt)" \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# 2. The embedding model (~90 MB), downloaded once at build time.
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}', device='cpu')"

# 3. The app, its migrations, the skills seeder and the sample data for "Load sample data".
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY scripts/seed_skills.py ./scripts/
COPY sample_data/jds ./sample_data/jds
COPY sample_data/resumes ./sample_data/resumes

# Run as a non-root user; uploads live in /app/storage (a volume in docker-compose).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p storage/uploads \
    && chown -R app:app storage
USER app

ENV PYTHONPATH=/app \
    EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    HF_HUB_OFFLINE=1 \
    SAMPLE_DATA_DIR=/app/sample_data \
    UPLOAD_DIR=/app/storage/uploads \
    APP_ENV=production

EXPOSE 8000

# Each start: apply migrations, seed the skills (both safe to re-run), then serve.
# One worker: parsing runs as in-process background tasks next to the loaded model.
CMD ["sh", "-c", "alembic upgrade head && python scripts/seed_skills.py && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
