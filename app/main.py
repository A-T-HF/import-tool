"""Einstiegspunkt der App Import Tool.

Minimaler FastAPI-Grundriss, der vom Plattform-Boilerplate angelegt
wurde. Erweitere ihn — Health-Endpoint beibehalten, weil die Plattform
(Säule 4) ihn zum Deployen nutzt.

ROOT_PATH wird über Uvicorn gesetzt (siehe Dockerfile), nicht hier im
Konstruktor — damit bleiben die Routen unter ihren kurzen Pfaden und
der Nginx-Reverse-Proxy funktioniert sauber.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Import Tool")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
