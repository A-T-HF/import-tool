# HotelFriend Import Tool

Web-basiertes Tool zum Importieren von Gästen, Firmen und Reservierungen in das HotelFriend PMS.

## Features

- **CSV / XLSX Upload** — Auto-Erkennung von Encoding und Trennzeichen
- **Spalten-Mapping** mit Fuzzy-Matching (Vorschläge per RapidFuzz)
- **Unterstützte Quellformate**
  - Generisches CSV/XLSX
  - Mews XLSX-Export (Reservations / Customers / Companies)
  - HS3 Firebird-Datenbank (`.hsb` / `.fdb`)
  - HS3 CSV-Export (ZIP)
  - Booking-List XLSX (Lodgify, Smoobu, …)
- **Automatische Transformationen**
  - Datumsformate: `19.12.2025`, `2025-12-19`, `19 Dez. 2025`, `Dec 19 2025`, …
  - Ländercodes: `Deutschland` → `DE`, `Germany` → `DE`
  - Währungsbeträge: `€129,00` → `129.00`
  - Reservierungsstatus: `bestätigt` → `confirmed`, `Abbruch durch Hotel` → `cancelled_by_hf`
- **Fallback-E-Mail-Generierung** — fehlende Emails werden als `vorname.nachname@import-hotelfriend.de` generiert
- **Validierung** mit Inline-Korrektur vor dem Export
- **CSV-Download** im HotelFriend-Import-Format

## Entitätstypen

| Typ | Pflichtfelder |
|-----|--------------|
| `guest` | `first_name`, `last_name` |
| `company` | `name` |
| `reservation` | `first_name`, `last_name`, `Check In`, `Check Out`, `Zimmertyp` |

## Lokaler Start (ohne Docker)

```bash
pip install -r requirements.txt
flask --app app run --port 8080
```

Öffne http://localhost:8080

> **HS3 / Firebird-Support** (optional): Für den Import von `.hsb`/`.fdb`-Dateien
> wird Firebird 3.0 + `firebird-driver` benötigt. Das `start_local.sh`-Skript
> installiert alles automatisch auf macOS (x86_64).

## Docker

```bash
docker build -t import-tool .
docker run -p 8080:8080 import-tool
```

> Hinweis: Der Docker-Container unterstützt **kein** HS3/Firebird-Import
> (erfordert x86_64-Binaries). CSV, XLSX und alle anderen Formate funktionieren.

## Tests

```bash
pip install pytest
pytest
```

## Projektstruktur

```
app.py                  # Flask-App, Upload-Routes
transformer.py          # Feld-Mapping, Transformationen, Validierung
bookinglist_reader.py   # BookingList XLSX (Lodgify/Smoobu)
mews_reader.py          # Mews XLSX-Export
hs3_reader.py           # HS3 Firebird-Datenbank
hs3_csv_reader.py       # HS3 CSV-Export (ZIP)
guests_importer.py      # Hilfsfunktionen Namensauflösung
templates/              # Jinja2 HTML-Templates
tests/                  # pytest-Testsuites
```
