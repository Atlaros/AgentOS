FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
COPY apps ./apps
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts

RUN uv sync --frozen --all-packages --no-dev \
    && useradd --system --uid 10001 --home /app app \
    && chown -R app /app

USER app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8080\")}/health', timeout=4)"

CMD ["python", "scripts/render_boot.py"]
