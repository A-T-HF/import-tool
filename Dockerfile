FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# tzdata: Plattform-Vertrag Europe/Berlin (/api/new-time)
# libfbclient2 + firebird3.0-utils: Firebird 3.x Client für HS3-ODS-12.0-Datenbanken
#   (Firebird 5.x unterstützt ODS 12.0 nicht mehr — daher gezielt 3.x)
#   gbak: in firebird3.0-utils enthalten → /usr/bin/gbak
#   libfbclient.so.2: in libfbclient2 enthalten → ld.so findet sie automatisch
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata libfbclient2 firebird3.0-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Nicht-Root-Benutzer anlegen (vor COPY, damit chown effizient läuft)
RUN adduser --system --uid 10001 app

COPY . .

# Besitzer setzen — Container-Dateisystem ist read-only,
# /tmp ist weiterhin beschreibbar (tmpfs gemountet durch die Plattform)
RUN chown -R app /app
USER app

EXPOSE 8000

# Healthcheck nutzt Python statt curl (kein Extra-Paket nötig).
# Greift auf internen Port + unverschobenen Pfad /healthz zu.
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://localhost:8000/healthz',timeout=2); sys.exit(0 if r.status==200 else 1)"

# ROOT_PATH wird von der Plattform als ENV gesetzt (/apps/{slug}).
# Uvicorn übergibt ihn an den ASGI-Scope — dort gehört er hin, nicht im
# FastAPI-Konstruktor (das würde die Route-Pfade verschieben und Nginx
# Proxy-Stripping brechen).
#
# --forwarded-allow-ips='*': akzeptiert X-Forwarded-*-Header vom Nginx-Proxy
# im Docker-Netz (kommt mit 172.x-Adresse, nicht 127.0.0.1).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --root-path ${ROOT_PATH:-}"]
