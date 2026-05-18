# Import Tool

Repo-Name in Gitea: `support-import-tool`.

Dieses Projekt wurde automatisch vom Intranet-Admin-Panel angelegt und mit dem Plattform-Boilerplate bestückt. Die detaillierte Arbeitsanweisung für Claude steht unter [`/api/new-project`](http://192.168.178.201/api/new-project) der Intranet-Shell.

## Struktur

```
.
├── .gitea/workflows/ci.yml   # pytest + bandit + semgrep + trivy-fs
├── app/
│   ├── __init__.py
│   └── main.py               # FastAPI-App mit /healthz
├── tests/
│   ├── __init__.py
│   └── test_smoke.py         # Smoke-Test gegen /healthz
├── Dockerfile                # non-root, Python 3.13-slim
├── requirements.txt
└── README.md                 # diese Datei
```

## Lokal starten

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# in einem zweiten Terminal
curl http://localhost:8000/healthz
```

## Tests

```bash
pytest -q
```

## Wichtig: URLs immer relativ

Die App läuft unter `/apps/{slug}/`. Absolute Pfade (`href="/seite"`, `src="/static/..."`) brechen. Immer relative Pfade nutzen: `href="seite"`, `src="static/app.css"`.

## Deployment

Push auf `main` → Gitea Actions läuft → bei grün übernimmt die Plattform-Deploy-Pipeline.
