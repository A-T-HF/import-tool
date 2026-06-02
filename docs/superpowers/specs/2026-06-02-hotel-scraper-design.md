# Hotel Scraper — Design Spec

**Datum:** 2026-06-02
**Status:** Entwurf zur Implementierung freigegeben

---

## Überblick

Internes Intranet-Tool für HotelFriend-Mitarbeiter. Mitarbeiter gibt Hotel-Name + Stadt (oder eine URL) ein — das Tool zieht automatisch alle verfügbaren Stammdaten, Zimmertypen, Ausstattungsmerkmale, Medien und Social-Links aus Google Places, der Hotel-Website und optional Booking.com. Ergebnis: editierbare Vorschau, dann 1-Klick-JSON-Export.

V1: Datei-Export (JSON)
V2 (spätere Iteration): direkter API-Push in HotelFriend

---

## Architektur

```
hotel-scraper/
  app.py           ← Flask-Server + Routes
  scraper.py       ← Scraping-Logik (Flask-agnostisch, V2-ready)
  templates/
    index.html     ← 3-Screen UI (JS-Zustandsmaschine, kein Page-Reload)
  requirements.txt
```

**Stack:** Flask (Python) + Bootstrap 5 + Vanilla JS — identisch zum Import-Tool.

`scraper.py` ist bewusst vom Server isoliert und gibt nur ein Dict zurück. V2 kann dieselbe Logik nutzen und statt JSON-Export einen HotelFriend-API-Call machen, ohne `app.py` wesentlich anzufassen.

---

## Datenmodell

Alle Felder, die das Tool zu befüllen versucht:

| Gruppe | Felder | Primärquelle |
|---|---|---|
| Stammdaten | name, address, city, zip, country, phone, email, website, stars | Google Places |
| Zeiten | checkin_time, checkout_time, opening_hours | Google Places |
| Beschreibung | description, short_description | Website → Claude |
| Zimmer | room_types[]: name, description, price_from | Website / Booking → Claude |
| Ausstattung | amenities[] | Google Places + Website → Claude |
| Media | logo_url, photos[] | Website → Claude |
| Social | facebook, instagram, twitter | Website → Claude |
| Meta | _sources{}: pro Feld die Herkunft | intern |

Das `_sources`-Dict dokumentiert für jedes Feld, woher der Wert stammt (`"google"`, `"website"`, `"booking"`). Die UI zeigt diese Herkunft als Badge an.

---

## Scraping-Pipeline (`scraper.py`)

```
Eingabe: query (Name + Stadt)  oder  url direkt
          ↓
Schritt 1 — Google Places API
  places_search(query)  →  place_id
  places_details(place_id)  →  Stammdaten, Öffnungszeiten, Fotos, Ausstattung
          ↓
Schritt 2 — Hotel-Website
  fetch(website_url)  →  HTML
  claude_extract(html, schema)  →  Zimmertypen, Beschreibungen, Social-Links, Ausstattung
          ↓
Schritt 3 — Booking.com (optional)
  Nur ausgeführt wenn Zimmer-Array nach Schritt 2 leer ist.
  playwright_fetch(booking_url)  →  HTML
  claude_extract(html, schema)  →  Zimmertypen + Preise
          ↓
merge(google, website, booking)
  → Google gewinnt Konflikte bei Stammdaten
  → Website gewinnt bei Enrichment-Feldern (Beschreibung, Zimmer, Social)
  → _sources{} wird pro Feld befüllt
```

**Externe Abhängigkeiten:**
- Google Places API (Key als Env-Var `GOOGLE_PLACES_API_KEY`)
- Anthropic API (Key als Env-Var `ANTHROPIC_API_KEY`) — claude-sonnet-4-6 für Extraktionen
- Playwright (nur für Booking.com, optional installierbar)

---

## UI-Flow

```
Screen 1 — Suche
┌─────────────────────────────────────────────────────┐
│  Hotel-Name [ _________________ ]  Stadt [ _______ ]│
│  — oder —                                            │
│  URL direkt [ _________________________________ ]    │
│                          [ Suchen → ]                │
└─────────────────────────────────────────────────────┘
  → Loading-Spinner während Scraping läuft (~5–15 Sek)
  → Fehleranzeige wenn keine Ergebnisse gefunden

Screen 2 — Review & Edit
┌─────────────────────────────────────────────────────┐
│  Name        [ Grand Hotel Berlin  ] [Google]        │
│  Adresse     [ Unter den Linden 77 ] [Google]        │
│  Sterne      [ 5                  ] [Google]          │
│  Beschreibung[ ...                ] [Website]        │
│  Zimmertypen [ + Eintrag hinzufügen ]                │
│    • Deluxe  [ ...                ] [Website] [✕]   │
│  Ausstattung [ WiFi, Pool, Spa... ] [Google]         │
│  Instagram   [ @grandhotelberlin  ] [Website]        │
│                                                      │
│            [ JSON exportieren ]                      │
│            (V2: [ In HotelFriend speichern ])        │
└─────────────────────────────────────────────────────┘

Kein Page-Reload — JS-Zustandsmaschine (identisches Muster zum Import-Tool)
```

Alle Felder sind inline editierbar. Pflichtfelder (name, address, city) werden rot markiert wenn leer. Der Export-Button ist gesperrt bis alle Pflichtfelder befüllt sind.

---

## Routen

| Methode | Pfad | Eingabe | Ausgabe |
|---|---|---|---|
| GET | `/` | — | `index.html` |
| POST | `/scrape` | `{ query?, url? }` | Scraped dict als JSON |
| POST | `/export` | `{ data: {...} }` | JSON-Datei-Download |

---

## Fehlerbehandlung

- Google Places findet kein Hotel → Fehlermeldung in Screen 1, Nutzer kann URL manuell eingeben
- Website nicht erreichbar / kein HTML → Schritt 2 übersprungen, weiter mit Schritt 3
- Booking.com blockiert → Schritt 3 übersprungen, Export mit vorhandenen Daten möglich
- Alle Quellen fehlschlagen → Leeres Formular in Screen 2, Nutzer füllt manuell aus

---

## V1 vs. V2

| | V1 | V2 |
|---|---|---|
| Export | JSON-Datei Download | HotelFriend-API-Push (`POST /api/hotels`) |
| `scraper.py` | unverändert | unverändert |
| `app.py` | `/export` Route | zusätzlich `/push` Route |
| Booking.com | optional via Playwright | wie V1 |
