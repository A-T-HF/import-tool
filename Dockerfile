FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Firebird 3 — Engine-Plugin für embedded gbak-Restore (HS3-Backups)
# firebird3.0-server wird nur für libEngine13.so benötigt, nicht als laufender Dienst
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y --no-install-recommends firebird3.0-server \
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
