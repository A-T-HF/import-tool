"""Smoke-Test, damit die CI-Pipeline grün durchläuft.

Der Test stellt sicher, dass die App importierbar ist und der
Health-Endpoint antwortet. Ohne diesen Test überspringt die Pipeline
pytest und die CI-Absicherung wäre löchrig.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_healthz_antwortet_ok() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
