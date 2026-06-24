# ── Production image for the WebBot backend ──
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install runtime deps first (no dev group) for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Chromium + its OS libraries (apt step needs root, so do it before USER).
RUN uv run playwright install --with-deps chromium

COPY . .

# Make `app` importable for alembic's env.py (and uvicorn).
ENV PYTHONPATH=/app

# Run as a non-root user. Pre-create the runtime dirs so the named volumes
# mounted over them inherit appuser ownership (else they'd be root-owned and
# the non-root process couldn't write the SQLite DB / screenshots).
RUN mkdir -p /app/data /app/storage/screenshots /app/storage/exports \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app /ms-playwright
USER appuser

EXPOSE 8000

# Liveness against the health endpoint (start-period covers migration time).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"

# Apply migrations, then serve (no --reload in production).
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
