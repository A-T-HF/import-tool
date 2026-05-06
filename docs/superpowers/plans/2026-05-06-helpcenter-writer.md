# Helpcenter Writer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend support-helpcenter-bot with gap-logging and an article-intake API, then build helpcenter-writer — a FastAPI app with three article-generation triggers (gap-queue, manual, release-notes paste), a review queue, and a one-click publish to the bot.

**Architecture:** Two separate Gitea projects, one API contract. The bot gains `UnansweredQuestion` logging and a `CustomChunk` table so new articles survive container restarts without touching the bundled markdown file. The writer calls `GET /api/gaps` and `POST /api/articles` on the bot over the internal network.

**Tech Stack:** Python 3.13, FastAPI, Jinja2, HTMX, SQLAlchemy 2, psycopg3, Google Gemini (`gemini-3.1-flash-lite-preview` + `gemini-embedding-2`), Plattform-Design-Tokens, Gitea CI (pytest / bandit / semgrep / trivy-fs).

---

## Phase 1 — support-helpcenter-bot extensions

### Task 1: Add UnansweredQuestion + CustomChunk models and load_all_chunks

**Files:**
- Modify: `support-helpcenter-bot/app/models.py`
- Modify: `support-helpcenter-bot/app/services/search.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_models.py  (new file)
def test_unanswered_question_model_fields():
    from app.models import UnansweredQuestion
    cols = {c.name for c in UnansweredQuestion.__table__.columns}
    assert {"id", "question", "score", "asked_at"} <= cols

def test_custom_chunk_model_fields():
    from app.models import CustomChunk
    cols = {c.name for c in CustomChunk.__table__.columns}
    assert {"id", "slug", "title", "body_md", "created_at"} <= cols

def test_load_all_chunks_includes_file_chunks():
    import os; os.environ.setdefault("GEMINI_API_KEY", "test")
    from unittest.mock import MagicMock
    from app.services.search import load_all_chunks
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = []
    result = load_all_chunks(db)
    assert len(result) > 0  # file-based chunks loaded
```

- [ ] **Step 2: Run — expect FAIL** (`pytest tests/test_models.py -v`)

- [ ] **Step 3: Add models to `app/models.py`**

Append after the existing `HelpcenterChunk` class:

```python
from sqlalchemy import Float  # add to existing import line


class UnansweredQuestion(Base):
    """Fragen, auf die der Bot keine gute Antwort gefunden hat (Score < 0.3).

    Fire-and-forget — Schreibfehler blockieren nie den Request-Path.
    """

    __tablename__ = "unanswered_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    asked_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class CustomChunk(Base):
    """Vom helpcenter-writer freigegebene Artikel, gespeichert in DB.

    Ergänzt die dateibasierten Chunks aus helpcenter_clean.md.
    Container-Filesystem ist read-only, daher kein Schreiben in die MD-Datei.
    """

    __tablename__ = "custom_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
```

- [ ] **Step 4: Add `load_all_chunks` to `app/services/search.py`**

Add after the existing `load_chunks()` function:

```python
def load_all_chunks(db: Session) -> list[dict]:
    """Lädt Datei-Chunks + freigegebene Custom-Chunks aus DB.

    Custom-Chunks werden ans Ende gehängt (nach Erstellungsdatum).
    """
    from app.models import CustomChunk

    file_chunks = load_chunks()

    rows = db.query(CustomChunk).order_by(CustomChunk.created_at).all()
    custom = [
        {
            "title": row.title,
            "slug": row.slug,
            "url": f"https://hotelfriend.com/de/b/{row.slug}",
            "body": f"## {row.title} {{#{row.slug}}}\n\n{row.body_md}",
        }
        for row in rows
    ]
    return file_chunks + custom
```

- [ ] **Step 5: Run — expect PASS** (`pytest tests/test_models.py -v`)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/services/search.py tests/test_models.py
git commit -m "feat: UnansweredQuestion + CustomChunk models, load_all_chunks"
```

---

### Task 2: Gap-logging in find_relevant_chunks + update lifespan to use load_all_chunks

**Files:**
- Modify: `support-helpcenter-bot/app/services/search.py`
- Modify: `support-helpcenter-bot/app/main.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_gap_logging.py  (new file)
def test_gap_callback_called_when_score_low():
    """on_gap wird aufgerufen wenn bester Score unter GAP_THRESHOLD."""
    from app.services.search import GAP_THRESHOLD, find_relevant_chunks

    called_with = []

    def fake_on_gap(q, s):
        called_with.append((q, s))

    # Leere Chunk- und Embedding-Listen → Score = 0.0 < GAP_THRESHOLD
    find_relevant_chunks(
        question="Was ist mit Gemüseanbau?",
        chunks=[],
        chunk_embeddings=[],
        idf={},
        gemini_client=None,
        on_gap=fake_on_gap,
    )
    assert len(called_with) == 1
    assert called_with[0][1] < GAP_THRESHOLD


def test_gap_callback_not_called_when_score_high():
    """on_gap wird NICHT aufgerufen wenn gute Ergebnisse gefunden wurden."""
    import math
    from app.services.search import find_relevant_chunks, tokenize

    called_with = []

    chunks = [{"title": "Checkin", "slug": "checkin", "url": "http://x", "body": "checkin checkin checkin " * 20}]
    idf = {"checkin": math.log(2)}
    # Fake embedding — hohe Cosine-Ähnlichkeit zu query_emb [1.0]
    embeddings = [[1.0]]

    class FakeClient:
        class models:
            @staticmethod
            def embed_content(model, contents):
                class R:
                    embeddings = [type("E", (), {"values": [1.0]})()]
                return R()

    find_relevant_chunks(
        question="checkin",
        chunks=chunks,
        chunk_embeddings=embeddings,
        idf=idf,
        gemini_client=FakeClient(),
        on_gap=lambda q, s: called_with.append((q, s)),
    )
    assert called_with == []
```

- [ ] **Step 2: Run — expect FAIL**

```
pytest tests/test_gap_logging.py -v
```

- [ ] **Step 3: Add GAP_THRESHOLD and on_gap parameter to `find_relevant_chunks`**

In `app/services/search.py`, add constant after imports:

```python
GAP_THRESHOLD = 0.3
```

Replace the `find_relevant_chunks` signature and add gap check before the return:

```python
def find_relevant_chunks(
    question: str,
    chunks: list[dict],
    chunk_embeddings: list[list[float]],
    idf: dict[str, float],
    gemini_client,
    top_n: int = 8,
    on_gap: Callable[[str, float], None] | None = None,
) -> list[dict]:
    """Kombiniert TF-IDF (40 %) + semantische Suche (60 %) für Ranking.

    Ruft on_gap(question, best_score) wenn bester Score < GAP_THRESHOLD.
    """
    if not chunks or not chunk_embeddings:
        if on_gap is not None:
            on_gap(question, 0.0)
        return []

    query_tokens = tokenize(question)

    tfidf_scores = [score_chunk(c, query_tokens, idf) for c in chunks]
    max_tfidf = max(tfidf_scores) if tfidf_scores else 1.0
    max_tfidf = max_tfidf or 1.0
    tfidf_norm = [s / max_tfidf for s in tfidf_scores]

    query_emb = get_embedding(question, gemini_client)
    sem_scores = [cosine_similarity(query_emb, emb) for emb in chunk_embeddings]
    max_sem = max(sem_scores) if sem_scores else 1.0
    max_sem = max_sem or 1.0
    sem_norm = [s / max_sem for s in sem_scores]

    combined = [0.4 * t + 0.6 * s for t, s in zip(tfidf_norm, sem_norm)]
    best_score = max(combined) if combined else 0.0

    if best_score < GAP_THRESHOLD and on_gap is not None:
        on_gap(question, best_score)

    ranked = sorted(enumerate(combined), key=lambda x: x[1], reverse=True)
    return [chunks[i] for i, score in ranked[:top_n] if score > 0.1]
```

- [ ] **Step 4: Add `_log_gap` helper and update `antwort` in `app/main.py`**

Add below the `_try_enable_pgvector` function:

```python
def _log_gap(question: str, score: float) -> None:
    """Schreibt eine unbeantwortete Frage in die DB. Fire-and-forget."""
    from app.models import UnansweredQuestion

    try:
        db = SessionLocal()
        try:
            db.add(UnansweredQuestion(question=question, score=score))
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        print(f"Gap-Logging fehlgeschlagen (ignoriert): {exc}")
```

In the `antwort` route, update the `ask_bot` call to pass `on_gap`:

```python
        answer, sources = ask_bot(
            question=frage,
            chunks=request.app.state.chunks,
            chunk_embeddings=request.app.state.chunk_embeddings,
            idf=request.app.state.idf,
            gemini_client=request.app.state.gemini_client,
            on_gap=_log_gap,
        )
```

- [ ] **Step 5: Update `ask_bot` signature in `app/services/bot.py`**

```python
def ask_bot(
    question: str,
    chunks: list[dict],
    chunk_embeddings: list[list[float]],
    idf: dict[str, float],
    gemini_client,
    on_gap: Callable[[str, float], None] | None = None,
) -> tuple[str, list[dict]]:
```

And pass it through to `find_relevant_chunks`:

```python
    relevant = find_relevant_chunks(
        question, chunks, chunk_embeddings, idf, gemini_client, on_gap=on_gap
    )
```

Add `from typing import Callable` to bot.py imports.

- [ ] **Step 6: Update lifespan in `app/main.py` to use `load_all_chunks`**

Change the import line:

```python
from app.services.search import (
    build_embeddings,
    build_tfidf_index,
    compute_source_hash,
    load_all_chunks,
    load_chunks,
    load_embeddings_from_db,
)
```

In the lifespan body, replace `chunks = load_chunks()` with:

```python
    db_init = SessionLocal()
    try:
        chunks = load_all_chunks(db_init)
    finally:
        db_init.close()
```

And update `_run_build` to reload chunks fresh:

```python
async def _run_build(app: FastAPI) -> None:
    """Asyncio-Task: lädt Chunks fresh (inkl. custom_chunks) und baut Embeddings."""
    status: dict[str, Any] = app.state.index_status
    gemini_client = app.state.gemini_client

    # Chunks immer fresh laden — custom_chunks könnten sich geändert haben
    db_load = SessionLocal()
    try:
        chunks = load_all_chunks(db_load)
    finally:
        db_load.close()

    source_hash = compute_source_hash(chunks)
    app.state.chunks = chunks
    app.state.idf = build_tfidf_index(chunks)
    app.state.source_hash = source_hash
    status["total"] = len(chunks)

    def _sync_build() -> list[list[float]]:
        db = SessionLocal()
        try:
            return build_embeddings(
                db,
                chunks,
                source_hash,
                gemini_client,
                on_progress=lambda done, total: status.update({"done": done, "total": total}),
            )
        finally:
            db.close()

    try:
        embeddings = await asyncio.to_thread(_sync_build)
        app.state.chunk_embeddings = embeddings
        status["state"] = "ready"
        status["done"] = len(chunks)
        status["total"] = len(chunks)
    except Exception as exc:
        status["state"] = "error"
        print(f"Embedding-Build fehlgeschlagen: {exc}")
```

- [ ] **Step 7: Run all tests — expect PASS**

```
pytest tests/ -v
```

- [ ] **Step 8: Commit**

```bash
git add app/services/search.py app/services/bot.py app/main.py tests/test_gap_logging.py
git commit -m "feat: Gap-Logging in find_relevant_chunks, load_all_chunks im Lifespan"
```

---

### Task 3: GET /api/gaps and POST /api/articles endpoints

**Files:**
- Modify: `support-helpcenter-bot/app/main.py`
- Create: `support-helpcenter-bot/tests/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api.py  (new file)
import os
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock

os.environ.setdefault("GEMINI_API_KEY", "test-key")


@asynccontextmanager
async def _noop_lifespan(app):
    app.state.chunks = []
    app.state.chunk_embeddings = []
    app.state.idf = {}
    app.state.gemini_client = None
    app.state.source_hash = "test"
    app.state.index_status = {"state": "ready", "done": 0, "total": 0}
    yield


def test_get_gaps_returns_list():
    from fastapi.testclient import TestClient
    from app.main import app

    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        with patch("app.main.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value = mock_db
            with TestClient(app) as client:
                resp = client.get("/api/gaps")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_post_articles_missing_fields_returns_400():
    from fastapi.testclient import TestClient
    from app.main import app

    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        with TestClient(app) as client:
            resp = client.post("/api/articles", json={"title": "x"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run — expect FAIL** (`pytest tests/test_api.py -v`)

- [ ] **Step 3: Add endpoints to `app/main.py`**

After the `/admin/reindex` endpoint, add:

```python
@app.get("/api/gaps")
def api_gaps(limit: int = 50) -> JSONResponse:
    """Gibt unbeantwortete Fragen zurück (für helpcenter-writer)."""
    from app.models import UnansweredQuestion

    db = SessionLocal()
    try:
        rows = (
            db.query(UnansweredQuestion)
            .order_by(UnansweredQuestion.asked_at.desc())
            .limit(limit)
            .all()
        )
        return JSONResponse([
            {
                "id": r.id,
                "question": r.question,
                "score": r.score,
                "asked_at": r.asked_at.isoformat(),
            }
            for r in rows
        ])
    finally:
        db.close()


@app.post("/api/articles")
async def api_articles(request: Request) -> JSONResponse:
    """Nimmt einen neuen Helpcenter-Artikel entgegen und triggert Reindex.

    Body: {title: str, slug: str, body_md: str}
    Speichert in custom_chunks (DB) — kein Dateischreiben, Container ist read-only.
    """
    from app.models import CustomChunk

    data = await request.json()
    title = (data.get("title") or "").strip()
    slug = (data.get("slug") or "").strip()
    body_md = (data.get("body_md") or "").strip()

    if not title or not slug or not body_md:
        return JSONResponse(
            {"error": "title, slug und body_md sind Pflichtfelder."},
            status_code=400,
        )

    db = SessionLocal()
    try:
        # Upsert: existierender Slug wird überschrieben
        existing = db.query(CustomChunk).filter(CustomChunk.slug == slug).first()
        if existing:
            existing.title = title
            existing.body_md = body_md
        else:
            db.add(CustomChunk(slug=slug, title=title, body_md=body_md))
        db.commit()
    finally:
        db.close()

    # Reindex im Hintergrund — lädt custom_chunks mit
    request.app.state.index_status = {
        "state": "building",
        "done": 0,
        "total": len(request.app.state.chunks) + 1,
    }
    asyncio.create_task(_run_build(request.app))

    return JSONResponse({"status": "ok", "slug": slug})
```

- [ ] **Step 4: Run all tests — expect PASS** (`pytest tests/ -v`)

- [ ] **Step 5: Push to Gitea, warte auf grünes CI**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat: GET /api/gaps + POST /api/articles endpoints"
git push origin main
```

---

## Phase 2 — helpcenter-writer (neues Projekt)

> Voraussetzung: Neues Projekt auf der Plattform anlegen unter `http://192.168.178.201/api/new-project`, Slug `helpcenter-writer`. Repo klonen: `http://192.168.178.201:3000/intranet/helpcenter-writer.git`. ENV `GEMINI_API_KEY` und `BOT_INTERNAL_URL` in der Plattform-UI eintragen.

### Task 4: Projekt-Scaffold

**Files:**
- Create: `helpcenter-writer/requirements.txt`
- Create: `helpcenter-writer/Dockerfile`
- Create: `helpcenter-writer/.gitea/workflows/ci.yml`
- Create: `helpcenter-writer/app/__init__.py`
- Create: `helpcenter-writer/app/db.py`
- Create: `helpcenter-writer/tests/__init__.py`

- [ ] **Step 1: requirements.txt**

```
fastapi>=0.115.6
uvicorn>=0.34.0
python-multipart>=0.0.22
sqlalchemy>=2.0.36
psycopg[binary]>=3.2.3
cryptography>=46.0.5
jinja2>=3.1.5
google-genai>=1.0.0
httpx>=0.28.1
pytest>=8.3.4
```

- [ ] **Step 2: Dockerfile** (identisch mit support-helpcenter-bot)

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

RUN adduser --system --uid 10001 app

COPY app/ ./app/

RUN chown -R app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://localhost:8000/healthz',timeout=2); sys.exit(0 if r.status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --root-path ${ROOT_PATH:-}"]
```

- [ ] **Step 3: .gitea/workflows/ci.yml** (exakte Kopie von support-helpcenter-bot)

```bash
cp ../support-helpcenter-bot/.gitea/workflows/ci.yml .gitea/workflows/ci.yml
```

- [ ] **Step 4: app/db.py** (exakte Kopie von support-helpcenter-bot)

```python
"""Datenbankverbindung — SQLite (lokal/Test) und PostgreSQL (Prod).

PgBouncer-Kompatibilität: prepare_threshold=None deaktiviert Prepared
Statements, die PgBouncer im Transaction-Mode nicht unterstützt.
"""
from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./helpcenter_writer.db")

if _DATABASE_URL.startswith("sqlite"):
    _connect_args: dict = {"check_same_thread": False}
else:
    _connect_args = {"prepare_threshold": None}

engine = create_engine(_DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Leere `__init__.py` anlegen**

```bash
touch app/__init__.py app/services/__init__.py tests/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "chore: Projekt-Scaffold (Dockerfile, requirements, CI, DB)"
```

---

### Task 5: ArticleDraft-Modell + Slug-Util

**Files:**
- Create: `helpcenter-writer/app/models.py`
- Create: `helpcenter-writer/app/services/slugify.py`
- Create: `helpcenter-writer/tests/test_slugify.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_slugify.py
def test_slug_lowercase():
    from app.services.slugify import slugify
    assert slugify("Früh Aufstehen") == "frueh-aufstehen"

def test_slug_umlaut_replacement():
    from app.services.slugify import slugify
    assert slugify("Überblick über Ärger") == "ueberblick-ueber-aerger"

def test_slug_special_chars_removed():
    from app.services.slugify import slugify
    assert slugify("Was ist (PMS)?") == "was-ist-pms"

def test_slug_multiple_spaces():
    from app.services.slugify import slugify
    assert slugify("Early   Check-in") == "early-check-in"
```

- [ ] **Step 2: Run — expect FAIL** (`pytest tests/test_slugify.py -v`)

- [ ] **Step 3: Create `app/services/slugify.py`**

```python
"""Slug-Generierung aus deutschen Titeln."""
from __future__ import annotations
import re
import unicodedata

_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
            "Ä": "ae", "Ö": "oe", "Ü": "ue"}


def slugify(title: str) -> str:
    """Konvertiert einen Titel in einen URL-sicheren Slug.

    Umlaute werden transkribiert, Sonderzeichen entfernt,
    Leerzeichen durch Bindestriche ersetzt.
    """
    for k, v in _UMLAUTS.items():
        title = title.replace(k, v)
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")
    title = re.sub(r"[^\w\s-]", "", title).strip().lower()
    return re.sub(r"[\s_-]+", "-", title)
```

- [ ] **Step 4: Create `app/models.py`**

```python
"""SQLAlchemy-Modell für Artikel-Entwürfe."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ArticleDraft(Base):
    """Ein KI-generierter Helpcenter-Artikel-Entwurf.

    status: 'draft' | 'approved' | 'rejected'
    source: 'gap' | 'manual' | 'release'
    source_ref: Originaltext der Frage oder Release-Notes (für Kontext).
    """

    __tablename__ = "article_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 5: Run — expect PASS** (`pytest tests/test_slugify.py -v`)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/services/slugify.py tests/test_slugify.py
git commit -m "feat: ArticleDraft-Modell, Slug-Util mit Umlaut-Transkription"
```

---

### Task 6: Writer-Service (Gemini Artikel-Generierung)

**Files:**
- Create: `helpcenter-writer/app/services/writer.py`
- Create: `helpcenter-writer/tests/test_writer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_writer.py
def test_write_article_returns_title_and_body():
    """write_article liefert einen nicht-leeren Titel und Markdown-Body."""
    from unittest.mock import MagicMock, patch
    from app.services.writer import write_article

    fake_response = MagicMock()
    fake_response.text = "## Früh-Check-in einrichten {#frueh-check-in-einrichten}\n\nSo geht es..."

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    title, slug, body = write_article(
        topic="Früh-Check-in",
        notes="Gäste fragen oft danach",
        context_articles=[],
        gemini_client=fake_client,
    )
    assert title
    assert slug
    assert "Check-in" in body or "check-in" in body.lower()
```

- [ ] **Step 2: Run — expect FAIL** (`pytest tests/test_writer.py -v`)

- [ ] **Step 3: Create `app/services/writer.py`**

```python
"""KI-Writer: generiert Helpcenter-Artikel mit Gemini."""
from __future__ import annotations
import re
import time

from app.services.slugify import slugify

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

WRITER_SYSTEM_PROMPT = """Du bist ein technischer Redakteur für HotelFriend — eine Hotel-Management-Software.

Schreibe einen neuen Helpcenter-Artikel im Stil der bestehenden HotelFriend-Artikel.

Regeln:
- Schreibe auf Deutsch, klar, freundlich und handlungsorientiert
- Keine Begriffe wie "Bug", "Fehler", "Crash" — stattdessen "Verhalten", "Anpassungsbedarf"
- Das Modul heißt "Unterlagen" — NICHT "Dokumente"
- Der Standard-Zahlungsanbieter heißt "HotelFriend Payment"
- Struktur: kurze Einleitung, dann nummerierte Schritte oder Abschnitte
- Ausgabe: NUR Markdown, keine Erklärungen, kein Präambel
- Erste Zeile zwingend: ## Titel des Artikels {#slug-des-artikels}
- Slug: Kleinbuchstaben, Umlaute transkribiert (ä→ae), Leerzeichen als Bindestriche
- Länge: 200-500 Wörter"""


def write_article(
    topic: str,
    notes: str,
    context_articles: list[str],
    gemini_client,
) -> tuple[str, str, str]:
    """Generiert einen Helpcenter-Artikel zu einem Thema.

    Args:
        topic: Thema / Titel des Artikels
        notes: Optionale Notizen / Kontext vom Nutzer
        context_articles: Texte ähnlicher bestehender Artikel (bis 3)
        gemini_client: Initialisierter Gemini-Client

    Returns:
        (title, slug, body_md) — body_md ohne die erste Titelzeile
    """
    from google import genai
    from google.genai import errors as genai_errors

    context_block = ""
    if context_articles:
        context_block = "\n\nÄhnliche bestehende Artikel (nur als Stilreferenz):\n\n"
        context_block += "\n\n---\n\n".join(context_articles[:3])

    prompt = f"Thema: {topic}"
    if notes:
        prompt += f"\n\nHinweise: {notes}"
    if context_block:
        prompt += context_block

    for attempt in range(3):
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=WRITER_SYSTEM_PROMPT,
                    max_output_tokens=1500,
                ),
            )
            break
        except (genai_errors.ClientError, genai_errors.ServerError) as e:
            status = getattr(e, "status_code", 0)
            if status in (429, 503) and attempt < 2:
                time.sleep(65 if status == 429 else 15)
                continue
            raise

    raw = response.text.strip()

    # Erste Zeile parsen: ## Titel {#slug}
    first_line = raw.split("\n")[0]
    title_match = re.match(r"^##\s+(.+?)(?:\s*\{#([\w-]+)\})?\s*$", first_line)
    if title_match:
        raw_title = title_match.group(1).strip()
        extracted_slug = title_match.group(2) or slugify(raw_title)
        title = re.sub(r"\s*\{#[\w-]+\}", "", raw_title).strip()
    else:
        title = topic
        extracted_slug = slugify(topic)

    # Body = alles nach der ersten Zeile
    body_lines = raw.split("\n")[1:]
    body_md = "\n".join(body_lines).strip()

    return title, extracted_slug, body_md
```

- [ ] **Step 4: Run — expect PASS** (`pytest tests/test_writer.py -v`)

- [ ] **Step 5: Commit**

```bash
git add app/services/writer.py tests/test_writer.py
git commit -m "feat: Writer-Service — Gemini Artikel-Generierung"
```

---

### Task 7: Bot-Client (HTTP)

**Files:**
- Create: `helpcenter-writer/app/services/bot_client.py`

- [ ] **Step 1: Create `app/services/bot_client.py`**

```python
"""HTTP-Client für die support-helpcenter-bot API."""
from __future__ import annotations
import os
import httpx

_BOT_URL = os.environ.get("BOT_INTERNAL_URL", "http://localhost:8001").rstrip("/")


def get_gaps(limit: int = 100) -> list[dict]:
    """Holt unbeantwortete Fragen vom Bot.

    Returns:
        Liste von {id, question, score, asked_at}
    """
    resp = httpx.get(f"{_BOT_URL}/api/gaps", params={"limit": limit}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def publish_article(title: str, slug: str, body_md: str) -> None:
    """Veröffentlicht einen Artikel im Bot (löst Reindex aus).

    Raises:
        httpx.HTTPStatusError wenn der Bot einen Fehler zurückgibt.
    """
    resp = httpx.post(
        f"{_BOT_URL}/api/articles",
        json={"title": title, "slug": slug, "body_md": body_md},
        timeout=30,
    )
    resp.raise_for_status()
```

- [ ] **Step 2: Commit**

```bash
git add app/services/bot_client.py
git commit -m "feat: Bot-HTTP-Client (GET /api/gaps, POST /api/articles)"
```

---

### Task 8: main.py + Templates Grundgerüst

**Files:**
- Create: `helpcenter-writer/app/main.py`
- Create: `helpcenter-writer/app/templates/base.html`
- Create: `helpcenter-writer/app/static/` (copy CSS + SVG from bot)

- [ ] **Step 1: Copy static assets from support-helpcenter-bot**

```bash
cp -r ../support-helpcenter-bot/app/static app/static
```

- [ ] **Step 2: Create `app/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Helpcenter Writer{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{{ request.url_for('static', path='design-tokens.css') }}">
  <link rel="stylesheet" href="{{ request.url_for('static', path='components.css') }}">
  <link rel="stylesheet" href="{{ request.url_for('static', path='app.css') }}">
</head>
<body>
  <nav class="navbar" id="navbar">
    <div class="navbar-inner">
      <a class="nav-project" href="{{ request.url_for('index') }}">Helpcenter Writer</a>
      <button class="nav-toggle" aria-label="Menü"
              onclick="document.getElementById('navbar').classList.toggle('is-open')">&#9776;</button>
      <div class="nav-menu">
        <a href="{{ request.url_for('gaps_page') }}"
           {% if active == 'gaps' %}class="is-active"{% endif %}>Lücken</a>
        <a href="{{ request.url_for('manual_page') }}"
           {% if active == 'manual' %}class="is-active"{% endif %}>Manuell</a>
        <a href="{{ request.url_for('releases_page') }}"
           {% if active == 'releases' %}class="is-active"{% endif %}>Release-Notes</a>
        <a href="{{ request.url_for('queue_page') }}"
           {% if active == 'queue' %}class="is-active"{% endif %}>Review-Queue</a>
      </div>
      <div class="nav-logo-wrap">
        <img class="nav-logo" src="{{ request.url_for('static', path='hotelfriend-white.svg') }}" alt="HotelFriend">
      </div>
    </div>
  </nav>
  <main>
    {% block content %}{% endblock %}
  </main>
  <script src="https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"
          integrity="sha384-HGfztofotfshcF7+8n44JQL2oJmowVChPTg48S+jvZoztPfvwD79OC/LTtG6dMp+"
          crossorigin="anonymous"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: Create `app/main.py`**

```python
"""Helpcenter Writer — FastAPI App.

Drei Artikel-Trigger: Gap-Queue, Manuell, Release-Notes.
Review-Queue mit Editor und Freigabe an support-helpcenter-bot.
"""
from __future__ import annotations
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google import genai

from app.db import Base, engine

_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not _GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY nicht gesetzt.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    app.state.gemini_client = genai.Client(api_key=_GEMINI_API_KEY)
    yield


app = FastAPI(title="Helpcenter Writer", lifespan=lifespan)

_BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, name="index")
async def index(request: Request):
    return templates.TemplateResponse(request, "gaps.html", {"active": "gaps", "gaps": []})
```

- [ ] **Step 4: Smoke-Test schreiben**

```python
# tests/test_smoke.py
import os
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock

os.environ.setdefault("GEMINI_API_KEY", "test-key")


@asynccontextmanager
async def _noop_lifespan(app):
    app.state.gemini_client = MagicMock()
    yield


def test_healthz():
    from fastapi.testclient import TestClient
    from app.main import app
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        with TestClient(app) as client:
            resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 5: Run** (`pytest tests/test_smoke.py -v`) — expect PASS

- [ ] **Step 6: Commit**

```bash
git add app/ tests/test_smoke.py
git commit -m "feat: App-Grundgerüst, base.html, Navbar, /healthz"
```

---

### Task 9: Gap-Queue Seite

**Files:**
- Create: `helpcenter-writer/app/templates/gaps.html`
- Create: `helpcenter-writer/app/templates/_generating.html`
- Modify: `helpcenter-writer/app/main.py`

- [ ] **Step 1: Create `app/templates/gaps.html`**

```html
{% extends "base.html" %}
{% block title %}Lücken – Helpcenter Writer{% endblock %}
{% block content %}
<div class="page-container">
  <div class="page-card">
    <h1 class="page-title">Wissenslücken</h1>
    <p class="page-subtitle">Fragen, auf die der Bot keine Antwort fand. Auswählen und Artikel generieren lassen.</p>

    {% if error %}
      <div class="alert alert-danger">{{ error }}</div>
    {% endif %}

    <form hx-post="{{ request.url_for('generate_from_gaps') }}"
          hx-target="#result"
          hx-swap="innerHTML"
          hx-indicator="#spinner">
      <div class="form-group">
        {% if gaps %}
          {% for g in gaps %}
          <label class="checkbox-row">
            <input type="checkbox" name="question_ids" value="{{ g.id }}">
            <span class="checkbox-label">
              {{ g.question }}
              <span class="badge">Score: {{ "%.2f"|format(g.score) }}</span>
            </span>
          </label>
          {% endfor %}
        {% else %}
          <p class="text-muted">Keine offenen Lücken — der Bot beantwortet alles gut.</p>
        {% endif %}
      </div>
      {% if gaps %}
      <div class="form-actions">
        <button type="submit" class="btn btn-primary">Artikel generieren</button>
      </div>
      {% endif %}
    </form>

    <div id="spinner" class="loading-indicator" style="display:none;">
      <span class="loading-spinner"></span>
      <span class="loading-text">Artikel werden generiert&hellip;</span>
    </div>
    <div id="result"></div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Create `app/templates/_generating.html`** (HTMX-Partial nach Generierung)

```html
<div class="alert alert-success">
  {{ count }} Artikel-Entwurf{% if count != 1 %}e{% endif %} generiert.
  <a href="{{ queue_url }}" class="btn btn-secondary btn-sm" style="margin-left:1rem;">Review-Queue öffnen →</a>
</div>
```

- [ ] **Step 3: Add routes to `app/main.py`**

Add imports at top:
```python
from fastapi import Form
from fastapi.responses import HTMLResponse, JSONResponse
from app.db import SessionLocal
from app.models import ArticleDraft
from app.services import bot_client, writer as writer_svc
from app.services.slugify import slugify
```

Add routes:
```python
@app.get("/gaps", response_class=HTMLResponse, name="gaps_page")
async def gaps_page(request: Request):
    try:
        gaps = bot_client.get_gaps(limit=100)
    except Exception:
        gaps = []
        error = "Bot nicht erreichbar — gaps konnten nicht geladen werden."
        return templates.TemplateResponse(
            request, "gaps.html", {"active": "gaps", "gaps": [], "error": error}
        )
    return templates.TemplateResponse(
        request, "gaps.html", {"active": "gaps", "gaps": gaps}
    )


@app.post("/gaps/generate", response_class=HTMLResponse, name="generate_from_gaps")
async def generate_from_gaps(request: Request):
    form = await request.form()
    question_ids = form.getlist("question_ids")
    if not question_ids:
        return HTMLResponse("<div class='alert alert-warning'>Bitte mindestens eine Frage auswählen.</div>")

    try:
        all_gaps = bot_client.get_gaps(limit=200)
    except Exception:
        return HTMLResponse("<div class='alert alert-danger'>Bot nicht erreichbar.</div>")

    selected = [g for g in all_gaps if str(g["id"]) in question_ids]
    count = 0
    db = SessionLocal()
    try:
        for gap in selected:
            question = gap["question"]
            title, slug, body_md = writer_svc.write_article(
                topic=question,
                notes="",
                context_articles=[],
                gemini_client=request.app.state.gemini_client,
            )
            # Doppelten Slug vermeiden
            base_slug = slug
            i = 1
            while db.query(ArticleDraft).filter(ArticleDraft.slug == slug).first():
                slug = f"{base_slug}-{i}"
                i += 1
            db.add(ArticleDraft(
                source="gap",
                source_ref=question,
                title=title,
                slug=slug,
                body_md=body_md,
            ))
            db.commit()
            count += 1
    finally:
        db.close()

    queue_url = str(request.url_for("queue_page"))
    return templates.TemplateResponse(
        request, "_generating.html", {"count": count, "queue_url": queue_url}
    )
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/gaps.html app/templates/_generating.html app/main.py
git commit -m "feat: Gap-Queue Seite + generate_from_gaps Endpoint"
```

---

### Task 10: Manuell + Release-Notes Seiten

**Files:**
- Create: `helpcenter-writer/app/templates/manual.html`
- Create: `helpcenter-writer/app/templates/releases.html`
- Modify: `helpcenter-writer/app/main.py`

- [ ] **Step 1: Create `app/templates/manual.html`**

```html
{% extends "base.html" %}
{% block title %}Manuell – Helpcenter Writer{% endblock %}
{% block content %}
<div class="page-container">
  <div class="page-card">
    <h1 class="page-title">Artikel manuell erstellen</h1>
    <p class="page-subtitle">Thema eingeben — KI schreibt den Entwurf, du prüfst ihn.</p>

    <form hx-post="{{ request.url_for('generate_manual') }}"
          hx-target="#result"
          hx-swap="innerHTML"
          hx-indicator="#spinner">
      <div class="form-group">
        <label class="form-label" for="topic">Thema *</label>
        <input id="topic" name="topic" class="form-input"
               placeholder="z. B.: Early Check-in einrichten" required autofocus>
      </div>
      <div class="form-group">
        <label class="form-label" for="notes">Hinweise / Kontext (optional)</label>
        <textarea id="notes" name="notes" class="form-textarea" rows="3"
                  placeholder="z. B.: Gäste fragen danach seit dem letzten Update"></textarea>
      </div>
      <div class="form-actions">
        <button type="submit" class="btn btn-primary">Artikel generieren</button>
      </div>
    </form>

    <div id="spinner" class="loading-indicator" style="display:none;">
      <span class="loading-spinner"></span>
      <span class="loading-text">Artikel wird generiert&hellip;</span>
    </div>
    <div id="result"></div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Create `app/templates/releases.html`**

```html
{% extends "base.html" %}
{% block title %}Release-Notes – Helpcenter Writer{% endblock %}
{% block content %}
<div class="page-container">
  <div class="page-card">
    <h1 class="page-title">Release-Notes einfügen</h1>
    <p class="page-subtitle">Release-Text aus Rocket.Chat oder Confluence einfügen — KI leitet Artikel-Entwürfe ab.</p>

    <form hx-post="{{ request.url_for('generate_from_release') }}"
          hx-target="#result"
          hx-swap="innerHTML"
          hx-indicator="#spinner">
      <div class="form-group">
        <label class="form-label" for="release_text">Release-Notes *</label>
        <textarea id="release_text" name="release_text" class="form-textarea" rows="10"
                  placeholder="Hier den Release-Text einfügen..." required></textarea>
      </div>
      <div class="form-actions">
        <button type="submit" class="btn btn-primary">Artikel generieren</button>
      </div>
    </form>

    <div id="spinner" class="loading-indicator" style="display:none;">
      <span class="loading-spinner"></span>
      <span class="loading-text">Artikel werden generiert&hellip;</span>
    </div>
    <div id="result"></div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Add manual + release routes to `app/main.py`**

```python
@app.get("/manual", response_class=HTMLResponse, name="manual_page")
async def manual_page(request: Request):
    return templates.TemplateResponse(request, "manual.html", {"active": "manual"})


@app.post("/manual/generate", response_class=HTMLResponse, name="generate_manual")
async def generate_manual(request: Request, topic: str = Form(...), notes: str = Form("")):
    topic = topic.strip()
    if not topic:
        return HTMLResponse("<div class='alert alert-warning'>Bitte ein Thema eingeben.</div>")

    title, slug, body_md = writer_svc.write_article(
        topic=topic,
        notes=notes.strip(),
        context_articles=[],
        gemini_client=request.app.state.gemini_client,
    )
    db = SessionLocal()
    try:
        base_slug = slug
        i = 1
        while db.query(ArticleDraft).filter(ArticleDraft.slug == slug).first():
            slug = f"{base_slug}-{i}"
            i += 1
        db.add(ArticleDraft(source="manual", source_ref=topic, title=title, slug=slug, body_md=body_md))
        db.commit()
    finally:
        db.close()

    queue_url = str(request.url_for("queue_page"))
    return templates.TemplateResponse(
        request, "_generating.html", {"count": 1, "queue_url": queue_url}
    )


@app.get("/releases", response_class=HTMLResponse, name="releases_page")
async def releases_page(request: Request):
    return templates.TemplateResponse(request, "releases.html", {"active": "releases"})


@app.post("/releases/generate", response_class=HTMLResponse, name="generate_from_release")
async def generate_from_release(request: Request, release_text: str = Form(...)):
    release_text = release_text.strip()
    if not release_text:
        return HTMLResponse("<div class='alert alert-warning'>Bitte Release-Text einfügen.</div>")

    # Gemini extrahiert Themen aus dem Release-Text
    from google import genai as _genai

    extract_prompt = (
        "Extrahiere aus folgenden Release-Notes alle neuen Features und Änderungen, "
        "die einen eigenen Helpcenter-Artikel rechtfertigen. "
        "Antworte NUR mit einer nummerierten Liste der Themen, je Zeile ein Thema.\n\n"
        f"Release-Notes:\n{release_text}"
    )
    client = request.app.state.gemini_client
    resp = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=extract_prompt,
        config=_genai.types.GenerateContentConfig(max_output_tokens=500),
    )
    topics = [
        line.lstrip("0123456789.- ").strip()
        for line in resp.text.strip().splitlines()
        if line.strip()
    ]

    count = 0
    db = SessionLocal()
    try:
        for topic in topics[:5]:  # max 5 Artikel pro Release
            title, slug, body_md = writer_svc.write_article(
                topic=topic,
                notes="",
                context_articles=[],
                gemini_client=client,
            )
            base_slug = slug
            i = 1
            while db.query(ArticleDraft).filter(ArticleDraft.slug == slug).first():
                slug = f"{base_slug}-{i}"
                i += 1
            db.add(ArticleDraft(
                source="release", source_ref=release_text[:500], title=title, slug=slug, body_md=body_md
            ))
            db.commit()
            count += 1
    finally:
        db.close()

    queue_url = str(request.url_for("queue_page"))
    return templates.TemplateResponse(
        request, "_generating.html", {"count": count, "queue_url": queue_url}
    )
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/manual.html app/templates/releases.html app/main.py
git commit -m "feat: Manuell- und Release-Notes-Seiten + generate-Endpoints"
```

---

### Task 11: Review-Queue + Editor + Approve/Reject

**Files:**
- Create: `helpcenter-writer/app/templates/queue.html`
- Create: `helpcenter-writer/app/templates/editor.html`
- Modify: `helpcenter-writer/app/main.py`

- [ ] **Step 1: Create `app/templates/queue.html`**

```html
{% extends "base.html" %}
{% block title %}Review-Queue – Helpcenter Writer{% endblock %}
{% block content %}
<div class="page-container">
  <div class="page-card">
    <h1 class="page-title">Review-Queue</h1>
    <p class="page-subtitle">{{ drafts|length }} Entwurf{% if drafts|length != 1 %}e{% endif %} warten auf Freigabe.</p>

    {% if drafts %}
    <table class="data-table">
      <thead>
        <tr>
          <th>Titel</th>
          <th>Quelle</th>
          <th>Erstellt</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for d in drafts %}
        <tr>
          <td>{{ d.title }}</td>
          <td><span class="badge">{{ d.source }}</span></td>
          <td>{{ d.created_at.strftime('%d.%m.%Y %H:%M') }}</td>
          <td>
            <a href="{{ request.url_for('editor_page', draft_id=d.id) }}"
               class="btn btn-secondary btn-sm">Bearbeiten</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="text-muted">Keine Entwürfe — alles freigegeben oder noch nichts generiert.</p>
    {% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Create `app/templates/editor.html`**

```html
{% extends "base.html" %}
{% block title %}Editor – {{ draft.title }}{% endblock %}
{% block content %}
<div class="page-container" style="max-width:1100px;">
  <div class="page-card">
    <h1 class="page-title">Artikel bearbeiten</h1>

    {% if error %}
      <div class="alert alert-danger">{{ error }}</div>
    {% endif %}

    <form method="POST" action="{{ request.url_for('editor_save', draft_id=draft.id) }}">
      <div class="form-group">
        <label class="form-label" for="title">Titel</label>
        <input id="title" name="title" class="form-input" value="{{ draft.title }}" required>
      </div>
      <div class="form-group">
        <label class="form-label" for="slug">Slug (URL-Kennung)</label>
        <input id="slug" name="slug" class="form-input" value="{{ draft.slug }}" required>
      </div>
      <div class="form-group">
        <label class="form-label" for="body_md">Inhalt (Markdown)</label>
        <textarea id="body_md" name="body_md" class="form-textarea"
                  rows="20" style="font-family:var(--font-mono);font-size:.875rem;">{{ draft.body_md }}</textarea>
      </div>
      <div class="form-actions">
        <a href="{{ request.url_for('queue_page') }}" class="btn btn-secondary">← Queue</a>
        <button type="submit" name="action" value="save" class="btn btn-secondary">Speichern</button>
        <button type="submit" name="action" value="reject"
                class="btn btn-danger"
                onclick="return confirm('Entwurf verwerfen?')">Verwerfen</button>
        <button type="submit" name="action" value="approve" class="btn btn-primary">Freigeben →</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Add queue + editor routes to `app/main.py`**

```python
from datetime import datetime


@app.get("/queue", response_class=HTMLResponse, name="queue_page")
async def queue_page(request: Request):
    db = SessionLocal()
    try:
        drafts = (
            db.query(ArticleDraft)
            .filter(ArticleDraft.status == "draft")
            .order_by(ArticleDraft.created_at.desc())
            .all()
        )
        return templates.TemplateResponse(
            request, "queue.html", {"active": "queue", "drafts": drafts}
        )
    finally:
        db.close()


@app.get("/editor/{draft_id}", response_class=HTMLResponse, name="editor_page")
async def editor_page(request: Request, draft_id: int):
    db = SessionLocal()
    try:
        draft = db.query(ArticleDraft).filter(ArticleDraft.id == draft_id).first()
        if not draft:
            return HTMLResponse("Entwurf nicht gefunden.", status_code=404)
        return templates.TemplateResponse(
            request, "editor.html", {"active": "queue", "draft": draft}
        )
    finally:
        db.close()


@app.post("/editor/{draft_id}", response_class=HTMLResponse, name="editor_save")
async def editor_save(
    request: Request,
    draft_id: int,
    title: str = Form(...),
    slug: str = Form(...),
    body_md: str = Form(...),
    action: str = Form(...),
):
    db = SessionLocal()
    try:
        draft = db.query(ArticleDraft).filter(ArticleDraft.id == draft_id).first()
        if not draft:
            return HTMLResponse("Entwurf nicht gefunden.", status_code=404)

        draft.title = title.strip()
        draft.slug = slug.strip()
        draft.body_md = body_md.strip()

        if action == "save":
            db.commit()
            return templates.TemplateResponse(
                request, "editor.html", {"active": "queue", "draft": draft}
            )

        if action == "reject":
            draft.status = "rejected"
            db.commit()
            return templates.TemplateResponse(
                request, "queue.html",
                {
                    "active": "queue",
                    "drafts": db.query(ArticleDraft).filter(ArticleDraft.status == "draft").all(),
                },
            )

        if action == "approve":
            db.commit()  # Speichere Änderungen zuerst
            try:
                bot_client.publish_article(
                    title=draft.title,
                    slug=draft.slug,
                    body_md=draft.body_md,
                )
            except Exception as exc:
                return templates.TemplateResponse(
                    request, "editor.html",
                    {"active": "queue", "draft": draft,
                     "error": f"Bot nicht erreichbar: {exc}"},
                )
            draft.status = "approved"
            draft.approved_at = datetime.utcnow()
            db.commit()
            return templates.TemplateResponse(
                request, "queue.html",
                {
                    "active": "queue",
                    "drafts": db.query(ArticleDraft).filter(ArticleDraft.status == "draft").all(),
                },
            )

        return HTMLResponse("Unbekannte Aktion.", status_code=400)
    finally:
        db.close()
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/queue.html app/templates/editor.html app/main.py
git commit -m "feat: Review-Queue, Editor, Approve/Reject + Publish-to-Bot"
```

---

### Task 12: CSS-Ergänzungen + Tests + Push

**Files:**
- Modify: `helpcenter-writer/app/static/app.css`
- Create: `helpcenter-writer/tests/test_routes.py`

- [ ] **Step 1: App-spezifisches CSS für Tabelle und Alert**

Append to `app/static/app.css`:

```css
/* ── Tabelle ──────────────────────────────────────────────────── */

.data-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: var(--space-md);
  font-size: 0.92rem;
}

.data-table th {
  text-align: left;
  padding: var(--space-sm) var(--space-md);
  border-bottom: 2px solid var(--border);
  color: var(--text-muted);
  font-weight: 600;
  font-size: 0.82rem;
}

.data-table td {
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.data-table tr:last-child td {
  border-bottom: none;
}

/* ── Alert ────────────────────────────────────────────────────── */

.alert {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-md);
  font-size: 0.92rem;
}

.alert-success { background: var(--success-light); color: var(--success); }
.alert-warning { background: var(--warning-light); color: var(--warning); }
.alert-danger  { background: var(--danger-light);  color: var(--danger);  }

/* ── Checkbox-Row ─────────────────────────────────────────────── */

.checkbox-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
}

.checkbox-row:last-child { border-bottom: none; }

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex: 1;
}

.text-muted { color: var(--text-muted); font-size: 0.92rem; }

.btn-sm { padding: 0.3rem 0.75rem; font-size: 0.82rem; }

.btn-danger {
  background: var(--danger);
  color: var(--white);
  border: none;
}
.btn-danger:hover { background: #8f1f2e; }
```

- [ ] **Step 2: Write route tests**

```python
# tests/test_routes.py
import os
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock

os.environ.setdefault("GEMINI_API_KEY", "test-key")


@asynccontextmanager
async def _noop_lifespan(app):
    app.state.gemini_client = MagicMock()
    yield


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app), app


def test_index_redirects_to_gaps():
    client, app = _client()
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        with patch("app.services.bot_client.get_gaps", return_value=[]):
            with client as c:
                resp = c.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_manual_page_renders():
    client, app = _client()
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        with client as c:
            resp = c.get("/manual")
    assert resp.status_code == 200


def test_releases_page_renders():
    client, app = _client()
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        with client as c:
            resp = c.get("/releases")
    assert resp.status_code == 200


def test_queue_page_renders():
    client, app = _client()
    with patch.object(app.router, "lifespan_context", _noop_lifespan):
        with patch("app.main.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
            mock_sl.return_value = mock_db
            with client as c:
                resp = c.get("/queue")
    assert resp.status_code == 200
```

- [ ] **Step 3: Run all tests — expect PASS**

```
pytest tests/ -v
```

- [ ] **Step 4: Final commit + push**

```bash
git add app/static/app.css tests/test_routes.py
git commit -m "feat: CSS-Ergänzungen (Tabelle, Alert, Checkbox), Route-Tests"
git push origin main
```

- [ ] **Step 5: CI abwarten, dann in Plattform-UI deployen**

Gitea → Actions → grüner Haken → Plattform-UI → Live-Deploy auslösen.

---

## Checkliste Spec-Coverage

| Spec-Anforderung | Task |
|---|---|
| Gap-Logging (Score < 0.3) | Task 2 |
| GET /api/gaps | Task 3 |
| POST /api/articles (Custom-Chunks in DB) | Task 3 |
| load_all_chunks (Datei + DB) | Task 1 |
| Projekt-Scaffold Writer | Task 4 |
| ArticleDraft-Modell | Task 5 |
| Slug-Util mit Umlauten | Task 5 |
| KI-Writer (Gemini) | Task 6 |
| Bot-HTTP-Client | Task 7 |
| Gap-Queue Seite | Task 9 |
| Manuell Seite | Task 10 |
| Release-Notes Seite | Task 10 |
| Review-Queue | Task 11 |
| Editor (Titel, Slug, Body) | Task 11 |
| Approve → publish_article | Task 11 |
| Reject | Task 11 |
| /healthz | Task 8 |
| Tests (Smoke, Writer, Slug, Routen) | Tasks 4, 6, 5, 12 |
