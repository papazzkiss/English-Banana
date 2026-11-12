# Banana English API (FastAPI + faster-whisper). Reproducible: dependencies pinned by uv.lock.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    HF_HOME=/models
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app

# dependencies first (layer cache)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --group speech --no-install-project

COPY src ./src
COPY content ./content
COPY scripts ./scripts
COPY docs/calibration ./docs/calibration
RUN uv sync --frozen --no-dev --group speech \
    && useradd --create-home --uid 10001 app && mkdir -p /models /app/var \
    && chown -R app /models /app/var
USER app
ENV PATH="/app/.venv/bin:$PATH" BANANA_UPLOAD_DIR=/app/var/uploads
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "banana_english.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
