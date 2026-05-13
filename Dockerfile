FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN useradd --system --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000

# Healthcheck nutzt Python statt curl, damit das Slim-Image kein zusätzliches
# Paket braucht. Greift immer auf den internen Container-Port und den
# unverschobenen Pfad /healthz zu — root_path wirkt nur auf generierte Links,
# nicht auf Route-Pfade.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://localhost:8000/healthz',timeout=2); sys.exit(0 if r.status==200 else 1)"

# ROOT_PATH wird von der Plattform als ENV gesetzt (/apps/{slug}).
# Uvicorn übergibt ihn an den ASGI-Scope — dort gehört er hin, nicht im
# FastAPI-Konstruktor (das würde die Route-Pfade verschieben und Nginx
# Proxy-Stripping brechen).
#
# --forwarded-allow-ips='*' ist nötig, damit uvicorn die X-Forwarded-*-
# Header vom nginx im Nachbar-Container akzeptiert. Per Default vertraut
# uvicorn nur 127.0.0.1 — aus dem Docker-Netz kommt der Proxy aber mit
# einer 172.x-Adresse. Ohne diesen Schalter ignoriert uvicorn
# X-Forwarded-Proto und baut auf HTTPS-Seiten http://-Links (Mixed
# Content, CSS wird geblockt).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --root-path ${ROOT_PATH:-}"]
