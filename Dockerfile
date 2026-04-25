FROM python:3.12-slim

LABEL maintainer="arivera"
LABEL description="Options scanner + position tracker via Schwab API"

# System deps for psycopg binary + curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Tokens volume — persists OAuth tokens across container restarts
VOLUME /app/.schwabdev

# Data volume — SQLite journal + cache
VOLUME /app/data

# Default: show help
ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
