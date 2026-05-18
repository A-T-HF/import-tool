FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Firebird 5 embedded — für HS3-Backup-Restore ohne laufenden Server
# Tarball enthält buildroot.tar.gz mit ./opt/firebird/... → direkt nach / extrahieren
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libtommath1 libtomcrypt1 libicu72 \
    && curl -fsSL \
       "https://github.com/FirebirdSQL/firebird/releases/download/v5.0.1/Firebird-5.0.1.1469-0-linux-x64.tar.gz" \
       | tar -xzOf - "Firebird-5.0.1.1469-0-linux-x64/buildroot.tar.gz" \
       | tar -xzf - -C / \
    && chmod +x /opt/firebird/bin/* \
    && echo "/opt/firebird/lib" > /etc/ld.so.conf.d/firebird.conf \
    && ldconfig \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

ENV HS3_FIREBIRD_HOME=/opt/firebird \
    LD_LIBRARY_PATH=/opt/firebird/lib

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN useradd --system --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://localhost:8000/healthz',timeout=2); sys.exit(0 if r.status==200 else 1)"

CMD ["sh", "-c", "cd /app/import-tool && gunicorn -w 2 -b 0.0.0.0:8000 app:app"]
