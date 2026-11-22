FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps/api ./apps/api
COPY packages ./packages
COPY workers ./workers
COPY db ./db
COPY evals ./evals

# Editable install: the runtime locates db/migrations and db/seeds next to the packages.
RUN pip install --no-cache-dir -e . \
    && useradd --system --uid 10001 --home /app app \
    && chown -R app /app

USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=4)"

CMD ["factory-os-api"]
