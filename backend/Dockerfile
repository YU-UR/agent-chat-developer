FROM python:3.11-slim

# Python runtime settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /app

# Native runtime libraries
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root application user
RUN groupadd --system app \
    && useradd --system \
        --gid app \
        --create-home \
        --home-dir /home/app \
        app

RUN mkdir -p /home/app/.cache/huggingface \
    && chown -R app:app /home/app/.cache

# Install Python dependencies first for better layer caching
COPY requirements.txt /app/requirements.txt

RUN python -m pip install \
    --no-cache-dir \
    -r /app/requirements.txt

# Copy application code and database migrations
COPY --chown=app:app app/ /app/app/
COPY --chown=app:app alembic/ /app/alembic/
COPY --chown=app:app alembic.ini /app/alembic.ini

# Runtime processes use a non-root user by default
USER app

# The same image can serve different application processes.
EXPOSE 8000 8010 8020

# Default process: FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]