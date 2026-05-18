FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Firebird 3 — für HS3-Backup-Restore (gbak) und embedded DB-Zugriff
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfbclient2 \
    firebird3.0-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN useradd --system --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://localhost:8000/healthz',timeout=2); sys.exit(0 if r.status==200 else 1)"

CMD ["sh", "-c", "cd /app/import-tool && gunicorn -w 2 -b 0.0.0.0:8000 app:app"]
