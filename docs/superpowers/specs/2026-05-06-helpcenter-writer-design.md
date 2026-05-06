# Helpcenter Writer — Design Spec

**Datum:** 2026-05-06
**Status:** Entwurf zur Implementierung freigegeben

---

## Überblick

Zwei-Produkt-Architektur: Der bestehende **support-helpcenter-bot** bekommt Gap-Logging und einen Artikel-Eingang. Das neue **helpcenter-writer**-Projekt übernimmt alle drei Trigger, den KI-Writer und die Review-Queue.

Ziel: Andreas kann Wissenslücken sehen, Artikel-Entwürfe generieren lassen, reviewen, freigeben — und der Bot kennt den Artikel sofort, ohne dass er erst im echten Helpcenter live sein muss.

---

## Architektur

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│   support-helpcenter-bot    │        │      helpcenter-writer        │
│                             │        │                               │
│  • Anfragen beantworten     │◄───────│  Trigger:                     │
│  • Gap-Logging (neu)        │        │  • Gap-Queue (aus Bot-Logs)   │
│  • POST /api/articles (neu) │        │  • Manuell ("schreib über X") │
│  • /admin/reindex           │        │  • Release-Notes (paste, v2)  │
└─────────────────────────────┘        │                               │
                                       │  • KI-Writer (Gemini)         │
                                       │  • Review-Queue               │
                                       │  • Freigabe → POST /api/      │
                                       │    articles an Bot            │
                                       └──────────────────────────────┘
```

Kommunikation: HTTP intern. `helpcenter-writer` kennt Bot-URL via `BOT_INTERNAL_URL` (ENV). Kein shared Volume, kein gemeinsamer Code — nur der API-Vertrag.

---

## Produkt 1: Änderungen am support-helpcenter-bot

### Gap-Logging

- In `find_relevant_chunks`: wenn bester combined-Score < 0.3, Frage in Tabelle `unanswered_questions` schreiben.
- Fire-and-forget — kein Blocking, kein Fehler wenn DB-Schreiber fehlschlägt.
- Kein automatischer Relevanz-Filter (kein extra Gemini-Call). Andreas entscheidet selbst was relevant ist.

**Tabelle (Bot-DB):**
```sql
unanswered_questions (
  id         SERIAL PRIMARY KEY,
  question   TEXT NOT NULL,
  score      FLOAT NOT NULL,
  asked_at   TIMESTAMP DEFAULT now()
)
```

### Neuer Endpoint: POST /api/articles

- Nimmt `{title, slug, body_md}` entgegen.
- Hängt Artikel als neuen `## Abschnitt {#slug}` an `helpcenter_clean.md` an.
- Ruft intern `/admin/reindex` auf — Bot kennt Artikel sofort.
- Antwort: `{"status": "ok", "slug": "..."}`.
- Kein Auth in v1 (internes Netz).

### Neuer Endpoint: GET /api/gaps

- Gibt die letzten N unanswered_questions zurück (JSON).
- `helpcenter-writer` pollt oder ruft einmalig ab.

---

## Produkt 2: helpcenter-writer (neues Projekt)

### Stack

Identisch mit support-helpcenter-bot: FastAPI + Jinja2 + HTMX, PostgreSQL, Gemini (`gemini-3.1-flash-lite-preview`), Plattform-Design-Tokens, Gitea CI.

### Datenmodell (Writer-eigene DB)

```sql
article_drafts (
  id          SERIAL PRIMARY KEY,
  source      TEXT NOT NULL,        -- 'gap' | 'manual' | 'release'
  source_ref  TEXT,                 -- question-Text oder null
  title       TEXT NOT NULL,
  slug        TEXT NOT NULL,
  body_md     TEXT NOT NULL,
  status      TEXT DEFAULT 'draft', -- 'draft' | 'approved' | 'rejected'
  created_at  TIMESTAMP DEFAULT now(),
  approved_at TIMESTAMP
)
```

### Screens und Flow

**1. Gap-Queue**
- Lädt `GET /api/gaps` vom Bot.
- Liste mit Checkboxen. Kein Auto-Filter — Andreas wählt selbst.
- `[Artikel generieren]` startet Writer für alle ausgewählten Fragen.

**2. Manuell**
- Formular: Thema (Pflicht) + optionaler Kontext/Notizen.
- `[Artikel generieren]` startet Writer direkt.

**3. Release-Notes (v2)**
- Paste-Feld für Release-Text aus Rocket.Chat oder Confluence.
- Writer leitet daraus Artikel-Entwürfe ab.
- In v1 nicht implementiert.

**4. Review-Queue**
- Liste aller Entwürfe mit Status `draft`.
- Jeder Eintrag: Titel, Quelle, Datum, `[Bearbeiten]`.

**5. Artikel-Editor**
- Felder: Titel, Slug (auto-generiert, editierbar), Markdown-Body.
- Vorschau-Pane neben dem Editor.
- Buttons: `[Verwerfen]` → Status `rejected`, `[Freigeben]` → POST an Bot, Status `approved`.

### KI-Writer

- Gemini-Prompt: gleicher `SYSTEM_PROMPT` wie der Bot + Schreib-Anweisung.
- Kontext: Die 3 relevantesten bestehenden Helpcenter-Artikel zum Thema (via Bot-Suche oder lokal).
- Output: Markdown mit `## Titel {#slug}` Struktur — direkt kompatibel mit `helpcenter_clean.md`.
- Retry-Logik: identisch mit Bot (429 → 65s, 503 → 15s, 3 Versuche).

### Freigabe-Flow

```
Freigabe-Klick
  → POST /api/articles an support-helpcenter-bot
  → Bot hängt Artikel an helpcenter_clean.md an
  → Bot triggert /admin/reindex
  → Writer markiert Draft als approved
  → Andreas publiziert manuell im echten Helpcenter
```

---

## Was explizit nicht in v1 ist

- Automatischer Relevanz-Filter für Gap-Fragen (zu viel Token-Verbrauch für wenig Gewinn)
- Release-Notes-Integration (Rocket.Chat / Confluence) — kommt in v2
- Auth auf `/api/articles` — internes Netz reicht vorerst
- Automatisches Publizieren ins echte Helpcenter (kein CMS-API vorhanden)

---

## Offene Fragen für Implementierung

- Schwellwert für Gap-Logging: 0.3 als Startwert, nach ersten Wochen justieren
- Slug-Generierung: aus Titel automatisch (Umlaute ersetzen, Leerzeichen → `-`)
- Polling-Intervall für Gap-Queue im Writer: manuell per Button reicht für v1
