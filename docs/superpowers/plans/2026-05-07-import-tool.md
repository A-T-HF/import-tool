# HotelFriend Import Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Internes Flask-Tool das CSV/XLS/XLSX aus fremden PMS-Systemen in das HotelFriend-Importformat transformiert — mit Column Mapping, automatischen Konvertierungen, Inline-Fehlerkorrektur und CSV/ZIP-Download.

**Architecture:** Flask-Backend mit drei Routes (`/upload`, `/validate`, `/download`). Transformations-Logik komplett isoliert in `transformer.py` (V2-ready). Ein einziges HTML-Template mit Vanilla-JS-Zustandsmaschine für alle vier Screens — kein Page-Reload.

**Tech Stack:** Python 3.11+, Flask 3.x, pandas 2.x, openpyxl 3.x, rapidfuzz 3.x, Bootstrap 5 (CDN), Vanilla JS

---

## Dateistruktur

```
import-tool/
  app.py                  ← Flask-Server: /upload, /validate, /download
  transformer.py          ← Schemas, Transformationen, Validierung, TransformResult
  templates/
    index.html            ← Alle 4 Screens, JS-Zustandsmaschine
  tests/
    test_transformer.py   ← Alle Unit-Tests für transformer.py
  requirements.txt
```

---

## Task 1: Projektstruktur + minimale Flask-App

**Files:**
- Create: `import-tool/requirements.txt`
- Create: `import-tool/app.py`
- Create: `import-tool/transformer.py`
- Create: `import-tool/templates/index.html`
- Create: `import-tool/tests/__init__.py`
- Create: `import-tool/tests/test_transformer.py`

- [ ] **Step 1: Verzeichnisse anlegen**

```bash
mkdir -p import-tool/templates import-tool/tests
touch import-tool/tests/__init__.py
```

- [ ] **Step 2: requirements.txt schreiben**

```
flask>=3.0
pandas>=2.0
openpyxl>=3.1
rapidfuzz>=3.0
pytest>=8.0
```

- [ ] **Step 3: Abhängigkeiten installieren**

```bash
cd import-tool && pip install -r requirements.txt
```

- [ ] **Step 4: Minimale Flask-App schreiben**

`import-tool/app.py`:
```python
from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True, port=5050)
```

- [ ] **Step 5: Minimales HTML-Template anlegen**

`import-tool/templates/index.html`:
```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <title>HotelFriend Import Tool</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
  <div class="container py-5">
    <h1 class="mb-4">HotelFriend Import Tool</h1>
    <p>Placeholder</p>
  </div>
</body>
</html>
```

- [ ] **Step 6: App starten und prüfen**

```bash
cd import-tool && python app.py
```
Erwartet: `Running on http://127.0.0.1:5050` — Browser zeigt "HotelFriend Import Tool"

- [ ] **Step 7: Commit**

```bash
git add import-tool/
git commit -m "feat: import-tool project scaffold"
```

---

## Task 2: transformer.py — Field Schemas

**Files:**
- Modify: `import-tool/transformer.py`
- Modify: `import-tool/tests/test_transformer.py`

Die Field Schemas definieren für jeden Entitätstyp: welche Felder existieren, welche sind Pflicht, und welcher Transformer/Validator greift.

- [ ] **Step 1: Test schreiben**

`import-tool/tests/test_transformer.py`:
```python
from transformer import get_fields, ENTITY_TYPES

def test_guest_required_fields():
    fields = get_fields("guest")
    required = [f["name"] for f in fields if f["required"]]
    assert set(required) == {"first_name", "last_name", "email"}

def test_company_required_fields():
    fields = get_fields("company")
    required = [f["name"] for f in fields if f["required"]]
    assert set(required) == {"name", "email"}

def test_reservation_required_fields():
    fields = get_fields("reservation")
    required = [f["name"] for f in fields if f["required"]]
    assert set(required) == {"first_name", "last_name", "email", "Check In", "Check Out", "Zimmer", "Zimmertyp"}

def test_entity_types_known():
    assert set(ENTITY_TYPES) == {"guest", "company", "reservation"}
```

- [ ] **Step 2: Test ausführen — muss scheitern**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -v
```
Erwartet: FAIL mit `ImportError`

- [ ] **Step 3: Field Schemas implementieren**

`import-tool/transformer.py`:
```python
from dataclasses import dataclass, field
from typing import Any

ENTITY_TYPES = ["guest", "company", "reservation"]

_GUEST_FIELDS = [
    {"name": "first_name",    "required": True,  "transformer": None,        "validator": None},
    {"name": "last_name",     "required": True,  "transformer": None,        "validator": None},
    {"name": "email",         "required": True,  "transformer": None,        "validator": "email"},
    {"name": "phone",         "required": False, "transformer": None,        "validator": None},
    {"name": "country",       "required": False, "transformer": "country",   "validator": None},
    {"name": "city",          "required": False, "transformer": None,        "validator": None},
    {"name": "date_of_birth", "required": False, "transformer": "date",      "validator": None},
    {"name": "language",      "required": False, "transformer": None,        "validator": "language"},
    {"name": "is_a_child",    "required": False, "transformer": None,        "validator": "is_child"},
    {"name": "passport_data", "required": False, "transformer": None,        "validator": None},
    {"name": "nationality",   "required": False, "transformer": "country",   "validator": None},
    {"name": "gender",        "required": False, "transformer": "gender",    "validator": None},
    {"name": "title",         "required": False, "transformer": "title",     "validator": None},
]

_COMPANY_FIELDS = [
    {"name": "name",           "required": True,  "transformer": None,      "validator": None},
    {"name": "email",          "required": True,  "transformer": None,      "validator": "email"},
    {"name": "code",           "required": False, "transformer": None,      "validator": "company_code"},
    {"name": "phone",          "required": False, "transformer": None,      "validator": None},
    {"name": "phone2",         "required": False, "transformer": None,      "validator": None},
    {"name": "country",        "required": False, "transformer": "country", "validator": None},
    {"name": "city",           "required": False, "transformer": None,      "validator": None},
    {"name": "address",        "required": False, "transformer": None,      "validator": None},
    {"name": "address2",       "required": False, "transformer": None,      "validator": None},
    {"name": "postcode",       "required": False, "transformer": None,      "validator": None},
    {"name": "type",           "required": False, "transformer": None,      "validator": "company_type"},
    {"name": "register_number","required": False, "transformer": None,      "validator": None},
    {"name": "discount_type",  "required": False, "transformer": None,      "validator": "discount_type"},
    {"name": "discount_value", "required": False, "transformer": None,      "validator": None},
    {"name": "bank_account",   "required": False, "transformer": None,      "validator": None},
    {"name": "iban",           "required": False, "transformer": None,      "validator": None},
    {"name": "bic",            "required": False, "transformer": None,      "validator": None},
]

_RESERVATION_FIELDS = [
    {"name": "first_name", "required": True,  "transformer": None,   "validator": None},
    {"name": "last_name",  "required": True,  "transformer": None,   "validator": None},
    {"name": "email",      "required": True,  "transformer": None,   "validator": "email"},
    {"name": "Check In",   "required": True,  "transformer": "date", "validator": None},
    {"name": "Check Out",  "required": True,  "transformer": "date", "validator": None},
    {"name": "Zimmer",     "required": True,  "transformer": None,   "validator": None},
    {"name": "Zimmertyp",  "required": True,  "transformer": None,   "validator": None},
    {"name": "Summe",      "required": False, "transformer": None,   "validator": None},
    {"name": "Status",     "required": False, "transformer": "reservation_status", "validator": None},
]

_SCHEMAS = {
    "guest":       _GUEST_FIELDS,
    "company":     _COMPANY_FIELDS,
    "reservation": _RESERVATION_FIELDS,
}

def get_fields(entity_type: str) -> list[dict]:
    return _SCHEMAS[entity_type]
```

- [ ] **Step 4: Tests ausführen — müssen bestehen**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -v
```
Erwartet: 4x PASS

- [ ] **Step 5: Commit**

```bash
git add import-tool/transformer.py import-tool/tests/test_transformer.py
git commit -m "feat: transformer field schemas for guest, company, reservation"
```

---

## Task 3: transformer.py — Daten-Transformationen

**Files:**
- Modify: `import-tool/transformer.py`
- Modify: `import-tool/tests/test_transformer.py`

Jede Transformationsfunktion nimmt einen Rohwert (string) und gibt entweder den transformierten Wert oder `None` bei Misserfolg zurück.

- [ ] **Step 1: Tests schreiben**

Tests an `test_transformer.py` anhängen:
```python
from transformer import (
    transform_date, transform_country, transform_gender,
    transform_title, transform_reservation_status
)

# --- Datum ---
def test_date_german_format():
    assert transform_date("19.12.1992") == "1992-12-19"

def test_date_us_format():
    assert transform_date("12/19/1992") == "1992-12-19"

def test_date_iso_passthrough():
    assert transform_date("1992-12-19") == "1992-12-19"

def test_date_invalid():
    assert transform_date("kein datum") is None

def test_date_empty():
    assert transform_date("") is None

# --- Ländercode ---
def test_country_german_name():
    assert transform_country("Deutschland") == "DE"

def test_country_english_name():
    assert transform_country("Germany") == "DE"

def test_country_already_code():
    assert transform_country("DE") == "DE"

def test_country_lowercase_code():
    assert transform_country("de") == "DE"

def test_country_unknown():
    assert transform_country("Unbekanntes Land") is None

# --- Gender ---
def test_gender_male_variants():
    for v in ["m", "male", "männlich", "Mann", "M", "1"]:
        assert transform_gender(v) == "1", f"Failed for: {v}"

def test_gender_female_variants():
    for v in ["f", "female", "weiblich", "Frau", "F", "2"]:
        assert transform_gender(v) == "2", f"Failed for: {v}"

def test_gender_other():
    for v in ["other", "divers", "3", "x"]:
        assert transform_gender(v) == "3", f"Failed for: {v}"

# --- Title ---
def test_title_mr_variants():
    for v in ["Herr", "Mr", "mr", "MR", "mr."]:
        assert transform_title(v) == "mr", f"Failed for: {v}"

def test_title_mrs_variants():
    for v in ["Frau", "Mrs", "mrs", "ms", "Ms"]:
        assert transform_title(v) == "mrs", f"Failed for: {v}"

def test_title_miss_variants():
    for v in ["Miss", "miss", "Frl", "Frl."]:
        assert transform_title(v) == "miss", f"Failed for: {v}"

def test_title_unknown():
    assert transform_title("Prof.") is None

# --- Reservierungsstatus ---
def test_status_new_variants():
    for v in ["neu", "new", "Neu"]:
        assert transform_reservation_status(v) == "new", f"Failed for: {v}"

def test_status_confirmed():
    assert transform_reservation_status("bestätigt") == "confirmed"
    assert transform_reservation_status("confirmed") == "confirmed"

def test_status_cancelled_guest():
    assert transform_reservation_status("storniert (Gast)") == "cancelled_by_guest"
    assert transform_reservation_status("cancelled_by_guest") == "cancelled_by_guest"

def test_status_unknown():
    assert transform_reservation_status("unbekannt") is None
```

- [ ] **Step 2: Tests ausführen — müssen scheitern**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -v
```
Erwartet: Neue Tests FAIL mit `ImportError`

- [ ] **Step 3: Transformationsfunktionen implementieren**

An `import-tool/transformer.py` anhängen:
```python
from datetime import datetime
import re

# --- Datum ---
_DATE_FORMATS = [
    "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y",
    "%Y-%m-%d", "%d-%m-%Y", "%Y.%m.%d",
    "%d.%m.%y", "%m/%d/%y",
]

def transform_date(value: str) -> str | None:
    if not value or not value.strip():
        return None
    v = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

# --- Ländercode ---
_COUNTRY_MAP = {
    # Deutsch
    "deutschland": "DE", "österreich": "AT", "schweiz": "CH",
    "frankreich": "FR", "spanien": "ES", "italien": "IT",
    "niederlande": "NL", "belgien": "BE", "polen": "PL",
    "tschechien": "CZ", "tschechische republik": "CZ",
    "ungarn": "HU", "russland": "RU", "türkei": "TR",
    "griechenland": "GR", "portugal": "PT", "schweden": "SE",
    "norwegen": "NO", "dänemark": "DK", "finnland": "FI",
    "großbritannien": "GB", "vereinigtes königreich": "GB",
    "usa": "US", "vereinigte staaten": "US", "vereinigte staaten von amerika": "US",
    "china": "CN", "japan": "JP", "australien": "AU", "kanada": "CA",
    "rumänien": "RO", "bulgarien": "BG", "kroatien": "HR",
    "slowakei": "SK", "slowenien": "SI", "serbien": "RS",
    "luxemburg": "LU", "irland": "IE", "ukraine": "UA",
    # Englisch
    "germany": "DE", "austria": "AT", "switzerland": "CH",
    "france": "FR", "spain": "ES", "italy": "IT",
    "netherlands": "NL", "belgium": "BE", "poland": "PL",
    "czech republic": "CZ", "hungary": "HU", "russia": "RU",
    "turkey": "TR", "greece": "GR", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "finland": "FI",
    "united kingdom": "GB", "great britain": "GB",
    "united states": "US", "united states of america": "US",
    "australia": "AU", "canada": "CA", "romania": "RO",
    "bulgaria": "BG", "croatia": "HR", "slovakia": "SK",
    "slovenia": "SI", "serbia": "RS", "luxembourg": "LU",
    "ireland": "IE", "ukraine": "UA",
}
_VALID_ISO2 = re.compile(r"^[A-Z]{2}$")

def transform_country(value: str) -> str | None:
    if not value or not value.strip():
        return None
    v = value.strip()
    upper = v.upper()
    if _VALID_ISO2.match(upper):
        return upper
    return _COUNTRY_MAP.get(v.lower())

# --- Gender ---
_GENDER_MAP = {
    "1": "1", "m": "1", "male": "1", "männlich": "1", "mann": "1",
    "2": "2", "f": "2", "female": "2", "weiblich": "2", "frau": "2",
    "3": "3", "other": "3", "divers": "3", "x": "3",
}

def transform_gender(value: str) -> str | None:
    if not value or not value.strip():
        return None
    return _GENDER_MAP.get(value.strip().lower())

# --- Title ---
_TITLE_MAP = {
    "mr": "mr", "mr.": "mr", "herr": "mr",
    "mrs": "mrs", "mrs.": "mrs", "ms": "mrs", "ms.": "mrs", "frau": "mrs",
    "miss": "miss", "frl": "miss", "frl.": "miss",
}

def transform_title(value: str) -> str | None:
    if not value or not value.strip():
        return None
    return _TITLE_MAP.get(value.strip().lower())

# --- Reservierungsstatus ---
_STATUS_MAP = {
    "neu": "new", "new": "new",
    "bestätigt": "confirmed", "confirmed": "confirmed",
    "eingecheckt": "check_in", "check_in": "check_in",
    "ausgecheckt": "check_out", "check_out": "check_out",
    "storniert (gast)": "cancelled_by_guest", "cancelled_by_guest": "cancelled_by_guest",
    "storniert (hotel)": "cancelled_by_hf", "cancelled_by_hf": "cancelled_by_hf",
    "no show": "no_show", "no_show": "no_show",
    "due_in": "due_in", "due_out": "due_out",
    "booking_offer": "booking_offer",
}

def transform_reservation_status(value: str) -> str | None:
    if not value or not value.strip():
        return None
    return _STATUS_MAP.get(value.strip().lower())
```

- [ ] **Step 4: Tests ausführen — alle müssen bestehen**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -v
```
Erwartet: Alle PASS

- [ ] **Step 5: Commit**

```bash
git add import-tool/transformer.py import-tool/tests/test_transformer.py
git commit -m "feat: data transformers for date, country, gender, title, status"
```

---

## Task 4: transformer.py — Validierungsregeln

**Files:**
- Modify: `import-tool/transformer.py`
- Modify: `import-tool/tests/test_transformer.py`

Validierungsfunktionen geben `None` (OK) oder einen Fehlerstring zurück.

- [ ] **Step 1: Tests schreiben**

An `test_transformer.py` anhängen:
```python
from transformer import validate_field

def test_validate_email_valid():
    assert validate_field("email", "test@example.com") is None

def test_validate_email_invalid():
    assert validate_field("email", "kein email") is not None

def test_validate_email_empty_required():
    assert validate_field("email", "") is not None

def test_validate_language_valid():
    assert validate_field("language", "de") is None
    assert validate_field("language", "en") is None

def test_validate_language_too_long():
    assert validate_field("language", "deu") is not None

def test_validate_is_child_valid():
    assert validate_field("is_child", "0") is None
    assert validate_field("is_child", "1") is None

def test_validate_is_child_invalid():
    assert validate_field("is_child", "ja") is not None

def test_validate_company_code_valid():
    assert validate_field("company_code", "1234") is None
    assert validate_field("company_code", "1234567890") is None

def test_validate_company_code_too_short():
    assert validate_field("company_code", "123") is not None

def test_validate_company_code_too_long():
    assert validate_field("company_code", "12345678901") is not None

def test_validate_company_type_valid():
    assert validate_field("company_type", "Company") is None
    assert validate_field("company_type", "Agency") is None

def test_validate_company_type_invalid():
    assert validate_field("company_type", "GmbH") is not None

def test_validate_discount_type_valid():
    for v in ["Percentage", "Fixed discount", "Price for room type"]:
        assert validate_field("discount_type", v) is None

def test_validate_discount_type_invalid():
    assert validate_field("discount_type", "Rabatt") is not None
```

- [ ] **Step 2: Tests ausführen — müssen scheitern**

```bash
cd import-tool && python -m pytest tests/test_transformer.py::test_validate_email_valid -v
```
Erwartet: FAIL mit `ImportError`

- [ ] **Step 3: Validierungsfunktionen implementieren**

An `import-tool/transformer.py` anhängen:
```python
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_VALIDATORS = {
    "email": lambda v: None if _EMAIL_RE.match(v or "") else "Ungültiges E-Mail-Format",
    "language": lambda v: None if (v and len(v.strip()) <= 2 and v.strip().isalpha()) else "Muss ISO 639-1 sein (max 2 Zeichen)",
    "is_child": lambda v: None if v in ("0", "1") else "Muss 0 oder 1 sein",
    "company_code": lambda v: None if (v and v.strip().isdigit() and 4 <= len(v.strip()) <= 10) else "Muss Zahl mit 4–10 Stellen sein",
    "company_type": lambda v: None if v in ("Company", "Agency") else "Muss 'Company' oder 'Agency' sein",
    "discount_type": lambda v: None if v in ("Percentage", "Fixed discount", "Price for room type") else "Muss 'Percentage', 'Fixed discount' oder 'Price for room type' sein",
}

def validate_field(validator_name: str, value: str) -> str | None:
    """Returns error message or None if valid."""
    fn = _VALIDATORS.get(validator_name)
    if fn is None:
        return None
    return fn(value)
```

- [ ] **Step 4: Tests ausführen — alle müssen bestehen**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -v
```
Erwartet: Alle PASS

- [ ] **Step 5: Commit**

```bash
git add import-tool/transformer.py import-tool/tests/test_transformer.py
git commit -m "feat: field validators for email, language, gender, company fields"
```

---

## Task 5: transformer.py — TransformResult + transform()

**Files:**
- Modify: `import-tool/transformer.py`
- Modify: `import-tool/tests/test_transformer.py`

Die Kernfunktion `transform()` wendet Mapping, Transformatoren und Validierung auf alle Zeilen an.

- [ ] **Step 1: Tests schreiben**

An `test_transformer.py` anhängen:
```python
from transformer import transform, TransformResult

def _guest_mapping():
    return {
        "Vorname": "first_name",
        "Nachname": "last_name",
        "E-Mail": "email",
    }

def test_transform_valid_guest_row():
    rows = [{"Vorname": "Max", "Nachname": "Müller", "E-Mail": "max@example.com"}]
    result = transform(rows, "guest", _guest_mapping())
    assert isinstance(result, TransformResult)
    assert len(result.valid_rows) == 1
    assert len(result.error_rows) == 0
    assert result.valid_rows[0]["email"] == "max@example.com"
    assert result.valid_rows[0]["first_name"] == "Max"

def test_transform_missing_required_field():
    rows = [{"Vorname": "Max", "Nachname": "Müller", "E-Mail": ""}]
    result = transform(rows, "guest", _guest_mapping())
    assert len(result.valid_rows) == 0
    assert len(result.error_rows) == 1
    error = result.error_rows[0]
    assert error["row_index"] == 0
    assert any(e["field"] == "email" for e in error["errors"])

def test_transform_date_auto_converted():
    rows = [{
        "Vorname": "Max", "Nachname": "Müller", "E-Mail": "max@example.com",
        "Geburt": "19.12.1992"
    }]
    mapping = {**_guest_mapping(), "Geburt": "date_of_birth"}
    result = transform(rows, "guest", mapping)
    assert result.valid_rows[0]["date_of_birth"] == "1992-12-19"

def test_transform_country_auto_converted():
    rows = [{
        "Vorname": "Max", "Nachname": "Müller", "E-Mail": "max@example.com",
        "Land": "Deutschland"
    }]
    mapping = {**_guest_mapping(), "Land": "country"}
    result = transform(rows, "guest", mapping)
    assert result.valid_rows[0]["country"] == "DE"

def test_transform_unknown_country_is_error():
    rows = [{
        "Vorname": "Max", "Nachname": "Müller", "E-Mail": "max@example.com",
        "Land": "Unbekanntes Land"
    }]
    mapping = {**_guest_mapping(), "Land": "country"}
    result = transform(rows, "guest", mapping)
    assert len(result.error_rows) == 1

def test_transform_duplicate_emails_guest():
    rows = [
        {"Vorname": "Max", "Nachname": "Müller", "E-Mail": "same@example.com"},
        {"Vorname": "Anna", "Nachname": "Meier", "E-Mail": "same@example.com"},
    ]
    result = transform(rows, "guest", _guest_mapping())
    assert len(result.valid_rows) == 1
    assert len(result.error_rows) == 1
    assert result.error_rows[0]["row_index"] == 1

def test_transform_ignored_columns_excluded():
    rows = [{"Vorname": "Max", "Nachname": "Müller", "E-Mail": "max@example.com", "Intern": "ignore"}]
    mapping = {**_guest_mapping(), "Intern": "_ignore"}
    result = transform(rows, "guest", mapping)
    assert "Intern" not in result.valid_rows[0]
    assert "_ignore" not in result.valid_rows[0]
```

- [ ] **Step 2: Tests ausführen — müssen scheitern**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -k "test_transform" -v
```
Erwartet: FAIL mit `ImportError`

- [ ] **Step 3: TransformResult + transform() implementieren**

An `import-tool/transformer.py` anhängen:
```python
_TRANSFORMERS = {
    "date":                 transform_date,
    "country":              transform_country,
    "gender":               transform_gender,
    "title":                transform_title,
    "reservation_status":   transform_reservation_status,
}

@dataclass
class TransformResult:
    valid_rows: list[dict[str, Any]] = field(default_factory=list)
    error_rows: list[dict[str, Any]] = field(default_factory=list)


def transform(rows: list[dict], entity_type: str, mapping: dict[str, str]) -> TransformResult:
    """
    rows:        list of dicts with source column names as keys
    entity_type: "guest" | "company" | "reservation"
    mapping:     {source_col: target_field} — target "_ignore" means skip column
    """
    fields_schema = {f["name"]: f for f in get_fields(entity_type)}
    result = TransformResult()
    seen_emails = set()

    for row_index, raw_row in enumerate(rows):
        mapped = {}
        errors = []

        # Apply mapping + transformations
        for src_col, target_field in mapping.items():
            if target_field == "_ignore" or target_field == "":
                continue
            raw_value = str(raw_row.get(src_col, "") or "").strip()
            schema = fields_schema.get(target_field, {})
            transformer_name = schema.get("transformer")
            if transformer_name:
                transformed = _TRANSFORMERS[transformer_name](raw_value)
                if transformed is None and raw_value:
                    errors.append({"field": target_field, "reason": f"Wert '{raw_value}' konnte nicht konvertiert werden"})
                    mapped[target_field] = raw_value  # keep original for inline correction
                else:
                    mapped[target_field] = transformed or ""
            else:
                mapped[target_field] = raw_value

        # Check required fields
        for fname, fschema in fields_schema.items():
            if fschema["required"] and not mapped.get(fname):
                errors.append({"field": fname, "reason": "Pflichtfeld fehlt"})

        # Run validators
        for fname, fschema in fields_schema.items():
            validator_name = fschema.get("validator")
            if validator_name and mapped.get(fname):
                err = validate_field(validator_name, mapped[fname])
                if err:
                    errors.append({"field": fname, "reason": err})

        # Duplicate email check (guests only)
        if entity_type == "guest":
            email = mapped.get("email", "")
            if email and email in seen_emails:
                errors.append({"field": "email", "reason": "Duplikat-E-Mail — wird übersprungen"})
            elif email:
                seen_emails.add(email)

        if errors:
            result.error_rows.append({
                "row_index": row_index,
                "row_data": mapped,
                "errors": errors,
            })
        else:
            result.valid_rows.append(mapped)

    return result
```

- [ ] **Step 4: Tests ausführen — alle müssen bestehen**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -v
```
Erwartet: Alle PASS

- [ ] **Step 5: Commit**

```bash
git add import-tool/transformer.py import-tool/tests/test_transformer.py
git commit -m "feat: TransformResult dataclass and transform() core function"
```

---

## Task 6: transformer.py — Fuzzy Column Suggestions

**Files:**
- Modify: `import-tool/transformer.py`
- Modify: `import-tool/tests/test_transformer.py`

`suggest_mapping()` gibt für jede Quellspalte den besten Treffer aus den HotelFriend-Zielfeldern zurück (rapidfuzz).

- [ ] **Step 1: Tests schreiben**

An `test_transformer.py` anhängen:
```python
from transformer import suggest_mapping

def test_suggest_mapping_german_first_name():
    suggestions = suggest_mapping(["Vorname", "Nachname", "E-Mail"], "guest")
    assert suggestions["Vorname"]["field"] == "first_name"
    assert suggestions["Nachname"]["field"] == "last_name"

def test_suggest_mapping_english_columns():
    suggestions = suggest_mapping(["First Name", "Last Name", "Email"], "guest")
    assert suggestions["First Name"]["field"] == "first_name"
    assert suggestions["Email"]["field"] == "email"

def test_suggest_mapping_arrival():
    suggestions = suggest_mapping(["Arrival", "Departure"], "reservation")
    assert suggestions["Arrival"]["field"] == "Check In"
    assert suggestions["Departure"]["field"] == "Check Out"

def test_suggest_mapping_has_score():
    suggestions = suggest_mapping(["Vorname"], "guest")
    assert "score" in suggestions["Vorname"]
    assert 0 <= suggestions["Vorname"]["score"] <= 100
```

- [ ] **Step 2: Tests ausführen — müssen scheitern**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -k "suggest" -v
```
Erwartet: FAIL mit `ImportError`

- [ ] **Step 3: suggest_mapping() implementieren**

Am Anfang von `transformer.py` `rapidfuzz` importieren, dann Funktion hinzufügen:
```python
from rapidfuzz import process, fuzz
```

Funktion an `transformer.py` anhängen:
```python
# Aliases für fuzzy matching: alternative Namen für Zielfelder
_FIELD_ALIASES: dict[str, list[str]] = {
    "first_name":   ["Vorname", "First Name", "firstname", "Given Name", "Name"],
    "last_name":    ["Nachname", "Last Name", "lastname", "Surname", "Family Name"],
    "email":        ["E-Mail", "Email", "Mail", "E-Mail-Adresse"],
    "date_of_birth":["Geburtsdatum", "Date of Birth", "DOB", "Geburtstag"],
    "country":      ["Land", "Country", "Herkunft"],
    "nationality":  ["Nationalität", "Nationality"],
    "phone":        ["Telefon", "Phone", "Tel", "Mobilnummer"],
    "gender":       ["Geschlecht", "Gender"],
    "title":        ["Titel", "Title", "Anrede"],
    "language":     ["Sprache", "Language"],
    "Check In":     ["Arrival", "Ankunft", "Check-in", "Anreise", "Von"],
    "Check Out":    ["Departure", "Abreise", "Check-out", "Abreise", "Bis"],
    "Zimmer":       ["Room", "Zimmer", "Zimmer-Nr", "Room Number"],
    "Zimmertyp":    ["Room Type", "Zimmertyp", "Kategorie"],
    "Summe":        ["Total", "Betrag", "Preis", "Sum", "Amount"],
    "Status":       ["Status", "Buchungsstatus", "Booking Status"],
    "name":         ["Firma", "Company Name", "Firmenname", "Name"],
    "code":         ["ID", "Kunden-ID", "Code"],
}

def suggest_mapping(source_columns: list[str], entity_type: str) -> dict[str, dict]:
    """
    Returns {source_col: {"field": best_target_field, "score": int}}
    Score 0-100. Score < 60 means low confidence.
    """
    target_fields = [f["name"] for f in get_fields(entity_type)]

    # Build lookup: alias → field name
    alias_to_field: dict[str, str] = {}
    for field_name in target_fields:
        alias_to_field[field_name.lower()] = field_name
        for alias in _FIELD_ALIASES.get(field_name, []):
            alias_to_field[alias.lower()] = field_name

    candidates = list(alias_to_field.keys())
    result = {}

    for src_col in source_columns:
        match, score, _ = process.extractOne(
            src_col.lower(), candidates, scorer=fuzz.token_sort_ratio
        )
        result[src_col] = {
            "field": alias_to_field[match],
            "score": int(score),
        }

    return result
```

- [ ] **Step 4: Tests ausführen — alle müssen bestehen**

```bash
cd import-tool && python -m pytest tests/test_transformer.py -v
```
Erwartet: Alle PASS

- [ ] **Step 5: Commit**

```bash
git add import-tool/transformer.py import-tool/tests/test_transformer.py
git commit -m "feat: fuzzy column mapping suggestions with rapidfuzz"
```

---

## Task 7: app.py — /upload und /validate Routes

**Files:**
- Modify: `import-tool/app.py`

- [ ] **Step 1: /upload Route implementieren**

`import-tool/app.py` komplett ersetzen:
```python
import io
import csv
import zipfile
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from transformer import get_fields, suggest_mapping, transform, ENTITY_TYPES

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB Limit

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    entity_type = request.form.get("entity_type")
    if not f or entity_type not in ENTITY_TYPES:
        return jsonify({"error": "Ungültige Anfrage"}), 400

    filename = f.filename or ""
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(f, dtype=str, keep_default_na=False)
    except Exception as e:
        return jsonify({"error": f"Datei konnte nicht gelesen werden: {e}"}), 400

    df = df.fillna("")
    columns = list(df.columns)
    preview = df.head(5).to_dict(orient="records")
    all_rows = df.to_dict(orient="records")
    suggestions = suggest_mapping(columns, entity_type)
    target_fields = get_fields(entity_type)

    return jsonify({
        "columns": columns,
        "preview": preview,
        "all_rows": all_rows,
        "suggestions": suggestions,
        "target_fields": target_fields,
    })
```

- [ ] **Step 2: /validate Route implementieren**

An `app.py` anhängen:
```python
@app.route("/validate", methods=["POST"])
def validate():
    data = request.get_json()
    rows = data.get("rows", [])
    entity_type = data.get("entity_type")
    mapping = data.get("mapping", {})

    if entity_type not in ENTITY_TYPES:
        return jsonify({"error": "Unbekannter Entitätstyp"}), 400

    result = transform(rows, entity_type, mapping)
    return jsonify({
        "valid_rows": result.valid_rows,
        "error_rows": result.error_rows,
        "valid_count": len(result.valid_rows),
        "error_count": len(result.error_rows),
    })
```

- [ ] **Step 3: /download Route implementieren**

An `app.py` anhängen:
```python
@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    valid_rows = data.get("valid_rows", [])
    skipped_rows = data.get("skipped_rows", [])
    entity_type = data.get("entity_type", "data")

    def rows_to_csv_bytes(rows: list[dict]) -> bytes:
        if not rows:
            return b""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8-sig")  # BOM für Excel-Kompatibilität

    if len(valid_rows) <= 100:
        csv_bytes = rows_to_csv_bytes(valid_rows)
        return send_file(
            io.BytesIO(csv_bytes),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{entity_type}_import.csv",
        )

    # Mehr als 100 Zeilen → ZIP mit Chunks
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        chunks = [valid_rows[i:i+100] for i in range(0, len(valid_rows), 100)]
        for idx, chunk in enumerate(chunks, 1):
            zf.writestr(f"{entity_type}_teil_{idx}.csv", rows_to_csv_bytes(chunk).decode("utf-8-sig"))
        if skipped_rows:
            zf.writestr(f"{entity_type}_fehler.csv", rows_to_csv_bytes(skipped_rows).decode("utf-8-sig"))
    zip_buf.seek(0)
    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{entity_type}_import.zip",
    )

if __name__ == "__main__":
    app.run(debug=True, port=5050)
```

- [ ] **Step 4: Routes manuell testen**

```bash
cd import-tool && python app.py
```
In einem zweiten Terminal:
```bash
# Upload-Test mit Beispiel-CSV (erstelle kurz eine test.csv)
echo "Vorname,Nachname,E-Mail
Max,Müller,max@example.com" > /tmp/test.csv

curl -X POST http://localhost:5050/upload \
  -F "file=@/tmp/test.csv" \
  -F "entity_type=guest"
```
Erwartet: JSON mit `columns`, `suggestions`, `target_fields`

- [ ] **Step 5: Commit**

```bash
git add import-tool/app.py
git commit -m "feat: Flask routes /upload /validate /download"
```

---

## Task 8: index.html — Screen 1 & 2 (Upload + Mapping)

**Files:**
- Modify: `import-tool/templates/index.html`

- [ ] **Step 1: Vollständiges HTML-Grundgerüst mit JS-Zustandsmaschine**

`import-tool/templates/index.html` komplett ersetzen:
```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <title>HotelFriend Import Tool</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    .screen { display: none; }
    .screen.active { display: block; }
    .field-required { color: #dc3545; font-weight: 600; }
    .drop-zone {
      border: 2px dashed #6c757d; border-radius: 8px;
      padding: 40px; text-align: center; cursor: pointer;
      transition: border-color 0.2s;
    }
    .drop-zone.dragover { border-color: #0d6efd; background: #f0f4ff; }
    .drop-zone input[type=file] { display: none; }
  </style>
</head>
<body class="bg-light">
<div class="container py-5" style="max-width: 900px;">

  <!-- Header -->
  <div class="d-flex align-items-center mb-4 gap-3">
    <h1 class="h3 mb-0">HotelFriend Import Tool</h1>
    <span id="stepBadge" class="badge bg-secondary">Schritt 1 von 4</span>
  </div>

  <!-- Screen 1: Upload -->
  <div id="screen1" class="screen active card shadow-sm p-4">
    <h2 class="h5 mb-3">Datei hochladen</h2>
    <div class="mb-3">
      <label class="form-label fw-semibold">Entitätstyp</label>
      <select id="entityType" class="form-select">
        <option value="guest">Gäste</option>
        <option value="company">Firmen / Gruppen</option>
        <option value="reservation">Reservierungen</option>
      </select>
    </div>
    <div class="mb-3">
      <div class="drop-zone" id="dropZone">
        <p class="mb-1 text-muted">CSV, XLS oder XLSX hierher ziehen</p>
        <p class="mb-2 text-muted small">oder</p>
        <button class="btn btn-outline-primary btn-sm" onclick="document.getElementById('fileInput').click()">
          Datei auswählen
        </button>
        <input type="file" id="fileInput" accept=".csv,.xls,.xlsx">
        <p id="fileName" class="mt-2 mb-0 text-muted small"></p>
      </div>
    </div>
    <div id="uploadError" class="alert alert-danger d-none"></div>
    <button id="btnUpload" class="btn btn-primary" disabled>Weiter →</button>
  </div>

  <!-- Screen 2: Column Mapping -->
  <div id="screen2" class="screen card shadow-sm p-4">
    <h2 class="h5 mb-1">Spalten zuordnen</h2>
    <p class="text-muted small mb-3">Ordne jede Quellspalte einem HotelFriend-Feld zu. Pflichtfelder sind rot markiert.</p>
    <div id="mappingWarning" class="alert alert-warning d-none">
      Nicht alle Pflichtfelder sind zugeordnet.
    </div>
    <table class="table table-bordered table-sm">
      <thead class="table-light">
        <tr><th>Quellspalte</th><th>→ HotelFriend Feld</th><th>Vorschau (erste Zeile)</th></tr>
      </thead>
      <tbody id="mappingTable"></tbody>
    </table>
    <div class="d-flex gap-2">
      <button class="btn btn-outline-secondary" onclick="showScreen(1)">← Zurück</button>
      <button id="btnValidate" class="btn btn-primary">Prüfen & Weiter →</button>
    </div>
  </div>

  <!-- Screen 3a: Error Correction -->
  <div id="screen3a" class="screen card shadow-sm p-4">
    <h2 class="h5 mb-1">Fehler prüfen & korrigieren</h2>
    <div id="validationSummary" class="alert alert-info mb-3"></div>
    <div id="errorTable"></div>
    <div class="d-flex gap-2 mt-3">
      <button class="btn btn-outline-secondary" onclick="showScreen(2)">← Zurück</button>
      <button id="btnRevalidate" class="btn btn-warning">Erneut prüfen</button>
      <button id="btnDownload" class="btn btn-success d-none">Herunterladen ↓</button>
    </div>
  </div>

  <!-- Screen 3b: Download -->
  <div id="screen3b" class="screen card shadow-sm p-4">
    <h2 class="h5 mb-1">Download</h2>
    <div id="downloadSummary" class="alert alert-success mb-3"></div>
    <div class="d-flex gap-2">
      <button id="btnDoDownload" class="btn btn-success btn-lg">CSV herunterladen ↓</button>
      <button class="btn btn-outline-secondary" onclick="showScreen('3a')">← Zurück</button>
    </div>
  </div>

</div>

<script>
// ── State ──────────────────────────────────────────────────────────
const S = {
  entityType: "guest",
  allRows: [],
  columns: [],
  preview: [],
  targetFields: [],
  mapping: {},        // {srcCol: targetField}
  validRows: [],
  errorRows: [],      // [{row_index, row_data, errors}]
  corrections: {},    // {row_index: {field: value}}
  skipped: new Set(),
};

// ── Screen navigation ──────────────────────────────────────────────
function showScreen(n) {
  document.querySelectorAll(".screen").forEach(el => el.classList.remove("active"));
  const id = n === "3a" ? "screen3a" : n === "3b" ? "screen3b" : `screen${n}`;
  document.getElementById(id).classList.add("active");
  const labels = {1:"Schritt 1 von 4",2:"Schritt 2 von 4","3a":"Schritt 3 von 4","3b":"Schritt 4 von 4"};
  document.getElementById("stepBadge").textContent = labels[n] || "";
}

// ── Screen 1: Upload ───────────────────────────────────────────────
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
let selectedFile = null;

dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("dragover"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", e => {
  e.preventDefault(); dropZone.classList.remove("dragover");
  handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

function handleFile(file) {
  if (!file) return;
  selectedFile = file;
  document.getElementById("fileName").textContent = file.name;
  document.getElementById("btnUpload").disabled = false;
}

document.getElementById("btnUpload").addEventListener("click", async () => {
  const btn = document.getElementById("btnUpload");
  btn.disabled = true; btn.textContent = "Wird geladen…";
  const errEl = document.getElementById("uploadError");
  errEl.classList.add("d-none");

  const fd = new FormData();
  fd.append("file", selectedFile);
  fd.append("entity_type", document.getElementById("entityType").value);

  try {
    const res = await fetch("/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Fehler beim Upload");

    S.entityType = document.getElementById("entityType").value;
    S.allRows = data.all_rows;
    S.columns = data.columns;
    S.preview = data.preview;
    S.targetFields = data.target_fields;

    // Apply suggestions as default mapping
    S.mapping = {};
    for (const [col, suggestion] of Object.entries(data.suggestions)) {
      S.mapping[col] = suggestion.score >= 60 ? suggestion.field : "_ignore";
    }

    buildMappingTable();
    showScreen(2);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove("d-none");
  } finally {
    btn.disabled = false; btn.textContent = "Weiter →";
  }
});
</script>
</body>
</html>
```

- [ ] **Step 2: Browser öffnen und Screen 1 prüfen**

```bash
cd import-tool && python app.py
```
`http://localhost:5050` öffnen — Upload-Screen soll erscheinen, Drag & Drop funktionieren.

- [ ] **Step 3: Commit**

```bash
git add import-tool/templates/index.html
git commit -m "feat: Screen 1 Upload UI with drag-and-drop"
```

---

## Task 9: index.html — Screen 2 (Column Mapping) + Screen 3a (Fehlerkorrektur)

**Files:**
- Modify: `import-tool/templates/index.html`

- [ ] **Step 1: buildMappingTable() + validateAndShowErrors() zum `<script>` hinzufügen**

Den `<script>`-Block in `index.html` vor `</script>` erweitern:
```javascript
// ── Screen 2: Column Mapping ───────────────────────────────────────
function buildMappingTable() {
  const tbody = document.getElementById("mappingTable");
  const requiredFields = new Set(S.targetFields.filter(f => f.required).map(f => f.name));

  const options = [
    '<option value="_ignore">— ignorieren —</option>',
    ...S.targetFields.map(f => {
      const label = f.required ? `${f.name} *` : f.name;
      return `<option value="${f.name}">${label}</option>`;
    })
  ].join("");

  tbody.innerHTML = S.columns.map(col => {
    const previewVal = S.preview[0]?.[col] ?? "";
    const currentVal = S.mapping[col] || "_ignore";
    return `<tr>
      <td class="fw-semibold">${col}</td>
      <td>
        <select class="form-select form-select-sm mapping-select" data-col="${col}">
          ${options}
        </select>
      </td>
      <td class="text-muted small">${previewVal}</td>
    </tr>`;
  }).join("");

  // Set saved mapping values
  tbody.querySelectorAll(".mapping-select").forEach(sel => {
    sel.value = S.mapping[sel.dataset.col] || "_ignore";
    sel.addEventListener("change", () => {
      S.mapping[sel.dataset.col] = sel.value;
      checkRequiredMapped();
    });
  });
  checkRequiredMapped();
}

function checkRequiredMapped() {
  const requiredFields = new Set(S.targetFields.filter(f => f.required).map(f => f.name));
  const mappedTargets = new Set(Object.values(S.mapping).filter(v => v !== "_ignore"));
  const allMapped = [...requiredFields].every(f => mappedTargets.has(f));
  document.getElementById("btnValidate").disabled = !allMapped;
  document.getElementById("mappingWarning").classList.toggle("d-none", allMapped);
}

document.getElementById("btnValidate").addEventListener("click", async () => {
  const btn = document.getElementById("btnValidate");
  btn.disabled = true; btn.textContent = "Prüfe…";
  try {
    await validateAndShowErrors(S.allRows);
    showScreen("3a");
  } finally {
    btn.disabled = false; btn.textContent = "Prüfen & Weiter →";
  }
});

// ── Screen 3a: Error Correction ────────────────────────────────────
async function validateAndShowErrors(rows) {
  const res = await fetch("/validate", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ rows, entity_type: S.entityType, mapping: S.mapping }),
  });
  const data = await res.json();
  S.validRows = data.valid_rows;
  S.errorRows = data.error_rows;
  renderErrorScreen();
}

function renderErrorScreen() {
  const summary = document.getElementById("validationSummary");
  const total = S.validRows.length + S.errorRows.length;
  const errCount = S.errorRows.filter(r => !S.skipped.has(r.row_index)).length;

  summary.innerHTML = `
    <strong>${S.validRows.length} von ${total} Zeilen korrekt.</strong>
    ${S.errorRows.length > 0 ? ` <span class="text-danger">${S.errorRows.length} Zeile(n) mit Fehlern.</span>` : ""}
  `;

  const container = document.getElementById("errorTable");
  if (S.errorRows.length === 0) {
    container.innerHTML = '<div class="alert alert-success">Keine Fehler — alle Zeilen sind importierbar.</div>';
    document.getElementById("btnDownload").classList.remove("d-none");
    return;
  }

  container.innerHTML = S.errorRows.map(row => {
    const isSkipped = S.skipped.has(row.row_index);
    const errorList = row.errors.map(e =>
      `<li><strong>${e.field}:</strong> ${e.reason}</li>`
    ).join("");

    const editableFields = Object.entries(row.row_data).map(([field, val]) => {
      const hasError = row.errors.some(e => e.field === field);
      const correction = S.corrections[row.row_index]?.[field] ?? val;
      return `<td class="${hasError ? "table-danger" : ""}">
        <input type="text" class="form-control form-control-sm border-0 p-0 bg-transparent"
          data-row="${row.row_index}" data-field="${field}"
          value="${correction}" ${isSkipped ? "disabled" : ""}>
      </td>`;
    }).join("");

    const fieldHeaders = Object.keys(row.row_data).map(f => `<th class="small">${f}</th>`).join("");

    return `<div class="card mb-2 ${isSkipped ? "opacity-50" : "border-danger"}">
      <div class="card-header d-flex justify-content-between align-items-center py-1">
        <span class="small fw-semibold text-danger">Zeile ${row.row_index + 1}</span>
        <div class="form-check mb-0">
          <input class="form-check-input skip-check" type="checkbox" id="skip${row.row_index}"
            data-row="${row.row_index}" ${isSkipped ? "checked" : ""}>
          <label class="form-check-label small" for="skip${row.row_index}">Überspringen</label>
        </div>
      </div>
      <div class="card-body py-2">
        <ul class="small text-danger mb-2">${errorList}</ul>
        <div class="table-responsive">
          <table class="table table-sm table-bordered mb-0">
            <thead><tr>${fieldHeaders}</tr></thead>
            <tbody><tr>${editableFields}</tr></tbody>
          </table>
        </div>
      </div>
    </div>`;
  }).join("");

  // Events: inline corrections
  container.querySelectorAll("input[data-row]").forEach(inp => {
    inp.addEventListener("change", () => {
      const ri = parseInt(inp.dataset.row);
      const field = inp.dataset.field;
      if (!S.corrections[ri]) S.corrections[ri] = {};
      S.corrections[ri][field] = inp.value;
    });
  });

  // Events: skip checkboxes
  container.querySelectorAll(".skip-check").forEach(chk => {
    chk.addEventListener("change", () => {
      const ri = parseInt(chk.dataset.row);
      if (chk.checked) S.skipped.add(ri);
      else S.skipped.delete(ri);
      const allHandled = S.errorRows.every(r => S.skipped.has(r.row_index));
      document.getElementById("btnDownload").classList.toggle("d-none", !allHandled);
    });
  });

  document.getElementById("btnDownload").classList.add("d-none");
}

document.getElementById("btnRevalidate").addEventListener("click", async () => {
  // Apply corrections back into rows
  const correctedRows = S.allRows.map((row, i) => {
    if (!S.corrections[i]) return row;
    // Re-map corrections from target field names back to source columns
    const corrected = { ...row };
    for (const [srcCol, targetField] of Object.entries(S.mapping)) {
      if (S.corrections[i]?.[targetField] !== undefined) {
        corrected[srcCol] = S.corrections[i][targetField];
      }
    }
    return corrected;
  });
  S.corrections = {};
  S.skipped = new Set();
  await validateAndShowErrors(correctedRows);
});

document.getElementById("btnDownload").addEventListener("click", () => {
  const skippedRows = S.errorRows
    .filter(r => S.skipped.has(r.row_index))
    .map(r => ({ ...r.row_data, _fehler: r.errors.map(e => `${e.field}: ${e.reason}`).join("; ") }));
  S._skippedRows = skippedRows;
  showScreen("3b");
  const total = S.validRows.length;
  const skipped = skippedRows.length;
  document.getElementById("downloadSummary").innerHTML =
    `<strong>${total} Zeile(n) exportiert${skipped ? `, ${skipped} übersprungen` : ""}.</strong>
    ${total > 100 ? " Die Datei wird automatisch in Teile à 100 Zeilen aufgeteilt (ZIP)." : ""}`;
});

// ── Screen 3b: Download ────────────────────────────────────────────
document.getElementById("btnDoDownload").addEventListener("click", async () => {
  const btn = document.getElementById("btnDoDownload");
  btn.disabled = true; btn.textContent = "Wird erstellt…";
  try {
    const res = await fetch("/download", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        valid_rows: S.validRows,
        skipped_rows: S._skippedRows || [],
        entity_type: S.entityType,
      }),
    });
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const nameMatch = disposition.match(/filename="?([^"]+)"?/);
    const filename = nameMatch ? nameMatch[1] : "import.csv";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  } finally {
    btn.disabled = false; btn.textContent = "CSV herunterladen ↓";
  }
});
```

- [ ] **Step 2: Manuell testen — vollständiger Durchlauf**

```bash
cd import-tool && python app.py
```
Test-CSV erstellen:
```bash
cat > /tmp/gaeste_test.csv << 'EOF'
Vorname,Nachname,E-Mail,Land,Geburtsdatum,Geschlecht
Max,Müller,max@example.com,Deutschland,19.12.1992,männlich
Anna,Meier,anna@example.com,AT,1985-06-15,weiblich
Fehler,Row,,Unbekanntes Land,,
EOF
```
Schritte im Browser:
1. Datei hochladen → Screen 2 erscheint mit Mapping-Vorschlägen
2. Mapping prüfen → "Prüfen & Weiter" klicken
3. Screen 3a: Zeile 3 hat Fehler → Inline korrigieren oder überspringen
4. "Herunterladen" → Screen 3b erscheint
5. "CSV herunterladen" → Datei kommt an

- [ ] **Step 3: Commit**

```bash
git add import-tool/templates/index.html
git commit -m "feat: Screen 2 column mapping + Screen 3a inline error correction + Screen 3b download"
```

---

## Task 10: Abschluss & Smoke Test

**Files:**
- Read: `import-tool/app.py`, `import-tool/transformer.py`

- [ ] **Step 1: Alle Tests ausführen**

```bash
cd import-tool && python -m pytest tests/ -v
```
Erwartet: Alle PASS, kein FAIL

- [ ] **Step 2: Smoke Test mit allen drei Entitätstypen**

Test-Dateien erstellen und nacheinander durch das Tool schicken:

Firmen-CSV:
```bash
cat > /tmp/firmen_test.csv << 'EOF'
Name,E-Mail,Land,Typ,Discount
Muster GmbH,info@muster.de,Germany,Company,Percentage
Test AG,test@test.at,AT,Agency,Fixed discount
EOF
```

Reservierungen-CSV:
```bash
cat > /tmp/reservierungen_test.csv << 'EOF'
Vorname,Nachname,E-Mail,Ankunft,Abreise,Zimmer,Zimmertyp,Status
Max,Müller,max@example.com,01.06.2026,05.06.2026,101,Einzelzimmer,bestätigt
Anna,Meier,anna@example.com,15.06.2026,18.06.2026,202,Doppelzimmer,neu
EOF
```

Jeden Typ durch das Browser-Tool laufen lassen und Download prüfen.

- [ ] **Step 3: Finaler Commit**

```bash
git add import-tool/
git commit -m "feat: HotelFriend Import Tool v1 complete"
```

---

## Spec Coverage Check

| Spec-Anforderung | Task |
|---|---|
| Entitäten: Gäste, Firmen, Reservierungen | Task 2 |
| Flask + Bootstrap + Vanilla JS | Task 1 |
| transformer.py isoliert (V2-ready) | Task 5 |
| Screen 1: Upload mit Drag & Drop | Task 8 |
| Screen 2: Column Mapping + fuzzy suggestions | Tasks 6, 9 |
| Screen 3a: Fehlerreport + Inline-Korrektur | Task 9 |
| Screen 3b: Download CSV / ZIP | Tasks 7, 9 |
| Datum-Transformation | Task 3 |
| Ländercode-Transformation | Task 3 |
| Gender-Transformation | Task 3 |
| Title-Transformation | Task 3 |
| Reservierungsstatus-Transformation | Task 3 |
| Validierung: required fields | Tasks 4, 5 |
| Duplikat-Email-Erkennung (Gäste) | Task 5 |
| ZIP bei >100 Zeilen | Task 7 |
| Fehlerreport CSV | Task 7 |
