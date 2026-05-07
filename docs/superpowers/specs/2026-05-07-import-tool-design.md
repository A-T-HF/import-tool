# HotelFriend Import Tool — Design Spec

**Datum:** 2026-05-07
**Status:** Entwurf zur Implementierung freigegeben

---

## Überblick

Internes Tool für HotelFriend-Mitarbeiter und Hoteliers, das CSV/XLS/XLSX-Dateien aus fremden PMS-Systemen in das HotelFriend-Importformat transformiert. Der Nutzer lädt eine Datei hoch, mappt Spalten auf HotelFriend-Felder, korrigiert Fehler inline, und lädt eine saubere, importfertige CSV herunter.

V1: reine Datei-Transformation (file in → file out)
V2 (spätere Iteration): direkter API-Push in HotelFriend

---

## Entitäten

Das Tool unterstützt drei Entitätstypen:

| Entität | HotelFriend-Import |
|---|---|
| Gäste | CSV mit Feldern lt. Gastimport-Spec |
| Firmen / Gruppen | CSV mit Feldern lt. Company-Import-Spec |
| Reservierungen | CSV mit Feldern lt. Reservierungsimport-Spec |

Der Nutzer wählt den Typ zu Beginn — das Tool lädt dann die passenden Zielfelder und Validierungsregeln.

---

## Architektur

```
import-tool/
  app.py           ← Flask-Server + Routes
  transformer.py   ← Mapping, Transformation, Validierung (V2-ready)
  templates/
    index.html     ← Alle Screens (JS-gesteuert, kein Page-Reload)
  requirements.txt
```

**Stack:** Flask (Python) + Bootstrap 5 (HTML/CSS) + Vanilla JS

`transformer.py` ist bewusst vom Server isoliert. V2 kann dieselbe Transformations-Logik nutzen und statt CSV-Export einen API-Call machen, ohne `app.py` anzufassen.

---

## UI-Flow

```
Screen 1        Screen 2          Screen 3a              Screen 3b
─────────       ─────────         ─────────────          ─────────
Upload          Column Mapping    Fehler korrigieren     Download
+ Typ wählen    Spalten zuordnen  Inline-Editor          CSV / ZIP
```

Kein Page-Reload zwischen Screens — alles per JS-Zustandsmaschine in einem HTML-Template.

---

## Screen 1 — Upload

- Dropdown: Entität wählen (Gäste / Firmen / Reservierungen)
- Drag & Drop Dateifeld (akzeptiert CSV, XLS, XLSX)
- "Weiter"-Button → sendet Datei an Backend, Backend liest Spaltenköpfe und erste Zeilen, gibt JSON zurück

---

## Screen 2 — Column Mapping

- Tabelle mit zwei Spalten:
  - Links: erkannte Spaltenname aus Quelldatei
  - Rechts: Dropdown mit HotelFriend-Zielfeldern + Option "ignorieren"
- Auto-Vorschlag per fuzzy-matching (z.B. `"Vorname"` → `first_name`, `"Arrival"` → `Check In`)
- Pflichtfelder rot markiert wenn noch nicht gemappt — "Weiter" gesperrt bis alle Pflichtfelder belegt
- Vorschau: erste 5 Zeilen nach Transformation

---

## Screen 3a — Fehlerreport & Inline-Korrektur

- Korrekte Zeilen: grün, eingeklappt (read-only)
- Fehlerhafte Zeilen: rot, aufgeklappt, editierbar
  - Fehlerhaftes Feld direkt in der Zelle bearbeitbar
  - "Erneut validieren"-Button prüft Korrekturen sofort
- Nicht korrigierbare Zeilen (z.B. Duplikat-Email): Checkbox "bewusst überspringen"
- "Download"-Button erscheint erst wenn alle Fehler korrigiert oder übersprungen

---

## Screen 3b — Download

- Statistik-Banner: z.B. `17 von 19 Zeilen exportiert, 2 übersprungen`
- Download-Logik:
  - ≤ 100 Zeilen → einfache CSV
  - > 100 Zeilen → ZIP mit `teil_1.csv`, `teil_2.csv`, ... (HotelFriend-Limit: 100 Zeilen / Import wegen 30-Sekunden-Timeout)
- Optionaler Download: Fehlerreport CSV mit übersprungenen Zeilen + Grund

---

## Transformations-Logik (`transformer.py`)

Automatische Format-Konvertierungen vor der Validierung:

### Datum
Erkennt gängige Formate, gibt `YYYY-MM-DD` aus:
```
19.12.1992  →  1992-12-19
12/19/1992  →  1992-12-19
1992-12-19  →  unverändert
```

### Ländercode
Volltext zu ISO 3166-1 Alpha-2 uppercase:
```
Germany / Deutschland / germany  →  DE
Austria / Österreich             →  AT
unbekannt / ungültig             →  ⚠️ Fehler → Screen 3a
```

### Gender (Gäste)
```
m / male / männlich / Mann  →  1
f / female / weiblich       →  2
other / divers / *          →  3
```

### Title (Gäste)
```
Herr / Mr / mr    →  mr
Frau / Mrs / ms   →  mrs
Miss / Frl.       →  miss
```

### Reservierungsstatus
```
neu / new                →  new
bestätigt / confirmed    →  confirmed
eingecheckt / check_in   →  check_in
ausgecheckt / check_out  →  check_out
storniert (Gast)         →  cancelled_by_guest
storniert (Hotel)        →  cancelled_by_hf
no show                  →  no_show
```

Nicht erkannte Werte → Fehler → zur Inline-Korrektur in Screen 3a.

---

## Validierungsregeln

### Gäste
- Pflichtfelder: `first_name`, `last_name`, `email`
- Email-Format prüfen
- Duplikat-Emails innerhalb der Datei → zweite Zeile überspringen (mit Hinweis)
- `language`: max 2 Zeichen, ISO 639-1 lowercase
- `is_a_child`: nur `0` oder `1`
- `gender`: nur `1`, `2`, `3`
- `title`: nur `mr`, `mrs`, `miss`

### Firmen
- Pflichtfelder: `name`, `email`
- Kein automatischer Duplikat-Check (wie im System — Hinweis an Nutzer)
- `code`: numerisch, 4–10 Stellen
- `type`: nur `Company` oder `Agency`
- `discount_type`: nur `Percentage`, `Fixed discount`, `Price for room type`

### Reservierungen
- Pflichtfelder: `first_name`, `last_name`, `email`, `Check In`, `Check Out`, `Zimmer`, `Zimmertyp`
- Datum-Format: `YYYY-MM-DD`
- Status: nur erlaubte Werte (s. Transformations-Logik)

---

## V2-Vorbereitung

`transformer.py` exportiert eine klare Schnittstelle:

```python
def transform(rows, entity_type, mapping) -> TransformResult:
    # gibt zurück: valid_rows, error_rows
    ...
```

V2 ersetzt nur den letzten Schritt:
```python
# V1
write_csv(result.valid_rows)

# V2
post_to_hotelfriend_api(result.valid_rows, entity_type)
```

Keine Änderung an Mapping, Transformation oder Validierung nötig.

---

## Nicht im Scope (V1)

- Direkter API-Push an HotelFriend
- User-Authentifizierung (internes Tool)
- Persistenz / Verlauf gespeicherter Imports
- Custom Guest Fields (erweiterbar in V2)
