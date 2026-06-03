# Hotel Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal Flask tool that scrapes hotel data from Google Places, the hotel's website, and optionally Booking.com, presenting an editable preview with source badges and a 1-click JSON export.

**Architecture:** Flask server (`app.py`) with three routes; `scraper.py` contains all scraping logic and is Flask-agnostic (V2-ready for API push). A single-page JS state machine template handles Search → Review & Edit without page reloads.

**Tech Stack:** Python 3.13, Flask 3.x, requests, anthropic SDK (claude-sonnet-4-6), Google Places API, Playwright (optional, for Booking.com), pytest

---

## File Structure

| File | Responsibility |
|---|---|
| `hotel-scraper/app.py` | Flask server — 3 routes: `GET /`, `POST /scrape`, `POST /export` |
| `hotel-scraper/scraper.py` | All scraping logic: Google Places, website fetch, Claude extraction, merge |
| `hotel-scraper/templates/index.html` | Complete 2-screen UI (search + review) with JS state machine |
| `hotel-scraper/tests/test_scraper.py` | Unit tests for scraper.py functions |
| `hotel-scraper/tests/test_app.py` | Flask route smoke tests |
| `hotel-scraper/requirements.txt` | Python dependencies |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `hotel-scraper/requirements.txt`
- Create: `hotel-scraper/app.py`
- Create: `hotel-scraper/scraper.py`
- Create: `hotel-scraper/templates/index.html`
- Create: `hotel-scraper/tests/__init__.py`
- Create: `hotel-scraper/tests/test_scraper.py`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p hotel-scraper/templates hotel-scraper/tests
touch hotel-scraper/tests/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

Create `hotel-scraper/requirements.txt`:

```
flask>=3.0
requests>=2.31
beautifulsoup4>=4.12
anthropic>=0.34
pytest>=8.0
```

Note: Playwright is installed separately (`pip install playwright && playwright install chromium`) and is optional — if not installed, the Booking.com step is silently skipped.

- [ ] **Step 3: Create app.py with all three routes**

Create `hotel-scraper/app.py`:

```python
import os
import json
import io
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/scrape")
def scrape_route():
    data = request.get_json()
    query = (data.get("query") or "").strip()
    url = (data.get("url") or "").strip()
    if not query and not url:
        return jsonify({"error": "query oder url erforderlich"}), 400
    from scraper import scrape
    result = scrape(query=query or None, url=url or None)
    return jsonify(result)

@app.post("/export")
def export_route():
    data = request.get_json()
    hotel = data.get("data", {})
    clean = {k: v for k, v in hotel.items() if not k.startswith("_")}
    name_slug = (clean.get("name") or "hotel").replace(" ", "_").lower()
    buf = io.BytesIO(json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8"))
    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"{name_slug}.json",
    )

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, port=5055)
```

- [ ] **Step 4: Create placeholder scraper.py**

Create `hotel-scraper/scraper.py`:

```python
def scrape(query: str | None = None, url: str | None = None) -> dict:
    return empty_hotel()

def empty_hotel() -> dict:
    return {
        "name": None,
        "address": None,
        "city": None,
        "zip": None,
        "country": None,
        "phone": None,
        "email": None,
        "website": None,
        "stars": None,
        "checkin_time": None,
        "checkout_time": None,
        "opening_hours": [],
        "description": None,
        "short_description": None,
        "room_types": [],
        "amenities": [],
        "logo_url": None,
        "photos": [],
        "facebook": None,
        "instagram": None,
        "twitter": None,
        "_sources": {},
    }
```

- [ ] **Step 5: Create placeholder index.html**

Create `hotel-scraper/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>Hotel Scraper</title></head>
<body><h1>Hotel Scraper</h1><p>Coming soon.</p></body></html>
```

- [ ] **Step 6: Write smoke test for empty_hotel()**

Create `hotel-scraper/tests/test_scraper.py`:

```python
from scraper import empty_hotel

def test_empty_hotel_has_required_keys():
    h = empty_hotel()
    for key in ("name", "address", "city", "zip", "country", "phone", "email",
                "website", "stars", "checkin_time", "checkout_time",
                "opening_hours", "description", "short_description",
                "room_types", "amenities", "logo_url", "photos",
                "facebook", "instagram", "twitter", "_sources"):
        assert key in h

def test_empty_hotel_lists_are_empty():
    h = empty_hotel()
    assert h["room_types"] == []
    assert h["amenities"] == []
    assert h["photos"] == []
    assert h["opening_hours"] == []
    assert h["_sources"] == {}
```

- [ ] **Step 7: Install deps and run tests**

```bash
cd hotel-scraper
pip install -r requirements.txt
pytest tests/test_scraper.py -v
```

Expected output:
```
tests/test_scraper.py::test_empty_hotel_has_required_keys PASSED
tests/test_scraper.py::test_empty_hotel_lists_are_empty PASSED
2 passed
```

- [ ] **Step 8: Commit**

```bash
git add hotel-scraper/
git commit -m "feat: hotel-scraper project scaffolding"
```

---

### Task 2: scraper.py — merge() with source tracking

**Files:**
- Modify: `hotel-scraper/scraper.py`
- Modify: `hotel-scraper/tests/test_scraper.py`

The merge function combines data from three sources. Google wins for base fields (name, address, phone, etc.); website wins for enrichment fields (description, rooms, social). `_sources` tracks the origin of each non-null field.

- [ ] **Step 1: Write failing tests**

Add to `hotel-scraper/tests/test_scraper.py`:

```python
from scraper import merge

def test_merge_google_wins_base_fields():
    google = {"name": "Grand Hotel", "city": "Berlin", "phone": "+49 30 123"}
    website = {"name": "Grand Hotel GmbH", "city": "Berlin Mitte"}
    result = merge(google, website, {})
    assert result["name"] == "Grand Hotel"
    assert result["city"] == "Berlin"
    assert result["phone"] == "+49 30 123"

def test_merge_website_wins_enrichment():
    google = {"description": "nice hotel"}
    website = {"description": "A luxury 5-star experience", "facebook": "https://facebook.com/grand"}
    result = merge(google, website, {})
    assert result["description"] == "A luxury 5-star experience"
    assert result["facebook"] == "https://facebook.com/grand"

def test_merge_booking_fills_rooms_when_website_has_none():
    booking = {"room_types": [{"name": "Deluxe", "description": "Large room", "price_from": "150"}]}
    result = merge({}, {}, booking)
    assert len(result["room_types"]) == 1
    assert result["room_types"][0]["name"] == "Deluxe"
    assert result["_sources"]["room_types"] == "booking"

def test_merge_website_rooms_override_booking():
    website = {"room_types": [{"name": "Suite", "description": "Top floor", "price_from": "300"}]}
    booking = {"room_types": [{"name": "Standard", "description": "Basic", "price_from": "80"}]}
    result = merge({}, website, booking)
    assert result["room_types"][0]["name"] == "Suite"
    assert result["_sources"]["room_types"] == "website"

def test_merge_sources_tracked():
    google = {"name": "Hotel ABC", "stars": 4}
    website = {"description": "Beautiful hotel", "instagram": "@hotelABC"}
    result = merge(google, website, {})
    assert result["_sources"]["name"] == "google"
    assert result["_sources"]["stars"] == "google"
    assert result["_sources"]["description"] == "website"
    assert result["_sources"]["instagram"] == "website"

def test_merge_none_values_do_not_overwrite():
    google = {"name": "Hotel X"}
    website = {"name": None}
    result = merge(google, website, {})
    assert result["name"] == "Hotel X"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd hotel-scraper
pytest tests/test_scraper.py::test_merge_google_wins_base_fields -v
```

Expected: `FAILED` with `ImportError: cannot import name 'merge'`

- [ ] **Step 3: Implement merge() in scraper.py**

Add to `hotel-scraper/scraper.py` (after `empty_hotel`):

```python
_GOOGLE_FIELDS = {
    "name", "address", "city", "zip", "country", "phone",
    "website", "stars", "checkin_time", "checkout_time", "opening_hours",
}
_WEBSITE_FIELDS = {
    "description", "short_description", "room_types", "amenities",
    "logo_url", "photos", "facebook", "instagram", "twitter", "email",
}

def _is_empty(val) -> bool:
    return val is None or val == "" or val == []

def merge(google: dict, website: dict, booking: dict) -> dict:
    result = empty_hotel()
    sources = {}

    for key in _WEBSITE_FIELDS:
        val = booking.get(key)
        if not _is_empty(val):
            result[key] = val
            sources[key] = "booking"

    for key in _WEBSITE_FIELDS:
        val = website.get(key)
        if not _is_empty(val):
            result[key] = val
            sources[key] = "website"

    for key in _GOOGLE_FIELDS:
        val = google.get(key)
        if not _is_empty(val):
            result[key] = val
            sources[key] = "google"

    google_amenities = google.get("amenities", [])
    if google_amenities and _is_empty(result.get("amenities")):
        result["amenities"] = google_amenities
        sources["amenities"] = "google"

    result["_sources"] = sources
    return result
```

- [ ] **Step 4: Run all tests**

```bash
cd hotel-scraper
pytest tests/test_scraper.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hotel-scraper/scraper.py hotel-scraper/tests/test_scraper.py
git commit -m "feat: merge() with source tracking"
```

---

### Task 3: scraper.py — Google Places integration

**Files:**
- Modify: `hotel-scraper/scraper.py`
- Modify: `hotel-scraper/tests/test_scraper.py`

Calls Google Places Text Search API to find a hotel by name, then Place Details to get structured data. Requires `GOOGLE_PLACES_API_KEY` env var.

- [ ] **Step 1: Write failing tests**

Add to `hotel-scraper/tests/test_scraper.py`:

```python
from unittest.mock import patch, MagicMock
from scraper import places_search, places_details, _parse_google_result

def test_places_search_returns_place_id():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [{"place_id": "ChIJ_test123", "name": "Grand Hotel Berlin"}]
    }
    with patch("scraper.requests.get", return_value=mock_resp):
        result = places_search("Grand Hotel Berlin")
    assert result == "ChIJ_test123"

def test_places_search_returns_none_when_no_results():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    with patch("scraper.requests.get", return_value=mock_resp):
        result = places_search("xyzzy nonsense hotel")
    assert result is None

def test_parse_google_result_extracts_fields():
    raw = {
        "name": "Hotel Adlon",
        "formatted_phone_number": "+49 30 2261 0",
        "website": "https://www.kempinski.com/adlon",
        "address_components": [
            {"types": ["route"], "long_name": "Unter den Linden"},
            {"types": ["street_number"], "long_name": "77"},
            {"types": ["locality"], "long_name": "Berlin"},
            {"types": ["postal_code"], "long_name": "10117"},
            {"types": ["country"], "long_name": "Germany"},
        ],
        "opening_hours": {"weekday_text": ["Monday: 0:00 – 24:00"]},
    }
    result = _parse_google_result(raw)
    assert result["name"] == "Hotel Adlon"
    assert result["city"] == "Berlin"
    assert result["zip"] == "10117"
    assert result["country"] == "Germany"
    assert result["phone"] == "+49 30 2261 0"
    assert result["website"] == "https://www.kempinski.com/adlon"
    assert result["opening_hours"] == ["Monday: 0:00 – 24:00"]

def test_places_details_calls_api_and_parses():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "result": {
            "name": "Test Hotel",
            "address_components": [
                {"types": ["locality"], "long_name": "Hamburg"},
                {"types": ["country"], "long_name": "Germany"},
            ],
        }
    }
    with patch("scraper.requests.get", return_value=mock_resp):
        result = places_details("ChIJ_test")
    assert result["name"] == "Test Hotel"
    assert result["city"] == "Hamburg"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd hotel-scraper
pytest tests/test_scraper.py::test_places_search_returns_place_id -v
```

Expected: `FAILED` with `ImportError: cannot import name 'places_search'`

- [ ] **Step 3: Implement Google Places functions in scraper.py**

Add at the top of `hotel-scraper/scraper.py` (before `empty_hotel`):

```python
import os
import requests

GOOGLE_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
_PLACES_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
_DETAILS_FIELDS = (
    "name,formatted_address,formatted_phone_number,international_phone_number,"
    "website,opening_hours,address_components"
)

def places_search(query: str) -> str | None:
    resp = requests.get(
        _PLACES_SEARCH_URL,
        params={"query": query, "type": "lodging", "key": GOOGLE_API_KEY},
        timeout=10,
    )
    results = resp.json().get("results", [])
    return results[0]["place_id"] if results else None

def places_details(place_id: str) -> dict:
    resp = requests.get(
        _PLACES_DETAILS_URL,
        params={"place_id": place_id, "fields": _DETAILS_FIELDS, "key": GOOGLE_API_KEY},
        timeout=10,
    )
    return _parse_google_result(resp.json().get("result", {}))

def _parse_google_result(raw: dict) -> dict:
    comp = {}
    for c in raw.get("address_components", []):
        if c.get("types"):
            comp[c["types"][0]] = c["long_name"]

    hotel: dict = {}
    if raw.get("name"):
        hotel["name"] = raw["name"]
    street = " ".join(filter(None, [comp.get("route"), comp.get("street_number")])).strip()
    if street:
        hotel["address"] = street
    if comp.get("locality") or comp.get("postal_town"):
        hotel["city"] = comp.get("locality") or comp.get("postal_town")
    if comp.get("postal_code"):
        hotel["zip"] = comp["postal_code"]
    if comp.get("country"):
        hotel["country"] = comp["country"]
    phone = raw.get("formatted_phone_number") or raw.get("international_phone_number")
    if phone:
        hotel["phone"] = phone
    if raw.get("website"):
        hotel["website"] = raw["website"]
    weekday = raw.get("opening_hours", {}).get("weekday_text", [])
    if weekday:
        hotel["opening_hours"] = weekday
    return hotel
```

- [ ] **Step 4: Run all tests**

```bash
cd hotel-scraper
pytest tests/test_scraper.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hotel-scraper/scraper.py hotel-scraper/tests/test_scraper.py
git commit -m "feat: Google Places search + details integration"
```

---

### Task 4: scraper.py — Website fetch + Claude extraction

**Files:**
- Modify: `hotel-scraper/scraper.py`
- Modify: `hotel-scraper/tests/test_scraper.py`

Fetches the hotel website HTML with requests, sends it to Claude API (claude-sonnet-4-6) for structured JSON extraction.

- [ ] **Step 1: Write failing tests**

Add to `hotel-scraper/tests/test_scraper.py`:

```python
from scraper import fetch_website, claude_extract

def test_fetch_website_returns_html():
    mock_resp = MagicMock()
    mock_resp.text = "<html><body><h1>Welcome to Hotel ABC</h1></body></html>"
    mock_resp.raise_for_status = MagicMock()
    with patch("scraper.requests.get", return_value=mock_resp):
        html = fetch_website("https://example.com")
    assert "Hotel ABC" in html

def test_fetch_website_returns_empty_on_error():
    with patch("scraper.requests.get", side_effect=Exception("timeout")):
        html = fetch_website("https://unreachable.example.com")
    assert html == ""

def test_claude_extract_parses_json_response():
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=(
        '{"description": "Luxury hotel", '
        '"room_types": [{"name": "Deluxe", "description": "Large room", "price_from": "120"}], '
        '"amenities": ["WiFi", "Pool"], "logo_url": null, "photos": [], '
        '"facebook": null, "instagram": "@hotel", "twitter": null, '
        '"short_description": null, "email": null}'
    ))]
    mock_client.messages.create.return_value = mock_msg

    with patch("scraper.anthropic.Anthropic", return_value=mock_client):
        result = claude_extract("<html>some hotel html</html>")

    assert result["description"] == "Luxury hotel"
    assert result["room_types"][0]["name"] == "Deluxe"
    assert result["amenities"] == ["WiFi", "Pool"]
    assert result["instagram"] == "@hotel"

def test_claude_extract_returns_empty_on_invalid_json():
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="I could not find any hotel information.")]
    mock_client.messages.create.return_value = mock_msg

    with patch("scraper.anthropic.Anthropic", return_value=mock_client):
        result = claude_extract("<html></html>")

    assert result == {}
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd hotel-scraper
pytest tests/test_scraper.py::test_fetch_website_returns_html -v
```

Expected: `FAILED` with `ImportError: cannot import name 'fetch_website'`

- [ ] **Step 3: Implement fetch_website() and claude_extract() in scraper.py**

Add imports at the very top of `hotel-scraper/scraper.py`:

```python
import json
import anthropic
```

Add these functions to `hotel-scraper/scraper.py` (after `_parse_google_result`):

```python
_EXTRACTION_PROMPT = """Extract hotel information from this HTML. Return ONLY valid JSON with exactly these keys:
{
  "description": "full hotel description or null",
  "short_description": "brief tagline/slogan or null",
  "room_types": [{"name": "...", "description": "...", "price_from": "..."}],
  "amenities": ["WiFi", "Pool"],
  "logo_url": "absolute URL or null",
  "photos": ["url1", "url2"],
  "facebook": "URL or handle or null",
  "instagram": "URL or handle or null",
  "twitter": "URL or handle or null",
  "email": "email address or null"
}
Use null for missing scalar fields. Use [] for missing list fields. No explanation, only JSON.

HTML:
"""

def fetch_website(url: str) -> str:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""

def claude_extract(html: str) -> dict:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": _EXTRACTION_PROMPT + html[:15000]}],
    )
    text = message.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return {}
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return {}
```

- [ ] **Step 4: Run all tests**

```bash
cd hotel-scraper
pytest tests/test_scraper.py -v
```

Expected: all 16 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hotel-scraper/scraper.py hotel-scraper/tests/test_scraper.py
git commit -m "feat: website fetch + Claude extraction"
```

---

### Task 5: scraper.py — Booking.com (optional Playwright)

**Files:**
- Modify: `hotel-scraper/scraper.py`
- Modify: `hotel-scraper/tests/test_scraper.py`

Playwright fetches a Booking.com search page; Claude extracts room types. If Playwright is not installed, silently returns `""`. Only triggered when `room_types` is empty after website extraction.

- [ ] **Step 1: Write failing tests**

Add to `hotel-scraper/tests/test_scraper.py`:

```python
from scraper import booking_search_url, playwright_fetch

def test_booking_search_url_format():
    url = booking_search_url("Hotel Adlon", "Berlin")
    assert "booking.com" in url
    assert "Hotel" in url
    assert "Adlon" in url

def test_playwright_fetch_returns_empty_when_not_installed():
    with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
        result = playwright_fetch("https://www.booking.com/hotel/de/test.html")
    assert result == ""
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd hotel-scraper
pytest tests/test_scraper.py::test_booking_search_url_format -v
```

Expected: `FAILED` with `ImportError: cannot import name 'booking_search_url'`

- [ ] **Step 3: Implement Booking.com functions in scraper.py**

Add import at the top of `hotel-scraper/scraper.py`:

```python
from urllib.parse import quote_plus
```

Add functions after `claude_extract`:

```python
def booking_search_url(name: str, city: str) -> str:
    query = quote_plus(f"{name} {city}")
    return f"https://www.booking.com/search.html?ss={query}&lang=en-gb"

def playwright_fetch(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            html = page.content()
            browser.close()
        return html
    except Exception:
        return ""
```

- [ ] **Step 4: Run all tests**

```bash
cd hotel-scraper
pytest tests/test_scraper.py -v
```

Expected: all 18 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hotel-scraper/scraper.py hotel-scraper/tests/test_scraper.py
git commit -m "feat: optional Booking.com Playwright scraper"
```

---

### Task 6: scraper.py — scrape() orchestrator

**Files:**
- Modify: `hotel-scraper/scraper.py`
- Modify: `hotel-scraper/tests/test_scraper.py`

The main `scrape()` ties together all three sources: Google Places → website → Booking.com (optional). Accepts either a text `query` or a direct `url`.

- [ ] **Step 1: Write failing tests**

Add to `hotel-scraper/tests/test_scraper.py`:

```python
from scraper import scrape

def _google_search_mock():
    m = MagicMock()
    m.json.return_value = {"results": [{"place_id": "ChIJ_test"}]}
    return m

def _google_details_mock():
    m = MagicMock()
    m.json.return_value = {
        "result": {
            "name": "Hotel Test",
            "address_components": [
                {"types": ["locality"], "long_name": "Berlin"},
                {"types": ["country"], "long_name": "Germany"},
            ],
            "website": "https://hotel-test.de",
        }
    }
    return m

def _website_mock(html="<html></html>"):
    m = MagicMock()
    m.text = html
    m.raise_for_status = MagicMock()
    return m

def _claude_mock(description="Test desc"):
    m = MagicMock()
    m.content = [MagicMock(text=(
        f'{{"description": "{description}", "room_types": [{{"name": "Standard", "description": "Basic room", "price_from": "90"}}], '
        '"amenities": ["WiFi"], "logo_url": null, "photos": [], '
        '"facebook": null, "instagram": null, "twitter": null, "short_description": null, "email": null}'
    ))]
    return m

def test_scrape_query_returns_merged_dict():
    with patch("scraper.requests.get", side_effect=[_google_search_mock(), _google_details_mock(), _website_mock()]), \
         patch("scraper.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = _claude_mock("Cozy hotel")
        result = scrape(query="Hotel Test Berlin")

    assert result["name"] == "Hotel Test"
    assert result["city"] == "Berlin"
    assert result["description"] == "Cozy hotel"
    assert result["_sources"]["name"] == "google"
    assert result["_sources"]["description"] == "website"

def test_scrape_with_direct_url_skips_google():
    with patch("scraper.requests.get", return_value=_website_mock()), \
         patch("scraper.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = _claude_mock("Direct URL hotel")
        result = scrape(url="https://hotel-direct.de")

    assert result["description"] == "Direct URL hotel"
    assert result["_sources"].get("name") != "google"

def test_scrape_returns_empty_when_all_fail():
    with patch("scraper.requests.get", side_effect=Exception("network error")), \
         patch("scraper.anthropic.Anthropic", side_effect=Exception("api error")):
        result = scrape(query="impossible hotel xyz")
    assert result["name"] is None
    assert result["room_types"] == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd hotel-scraper
pytest tests/test_scraper.py::test_scrape_query_returns_merged_dict -v
```

Expected: `FAILED` — current `scrape()` returns `empty_hotel()` without calling anything.

- [ ] **Step 3: Replace placeholder scrape() in scraper.py**

Replace the existing `scrape()` stub in `hotel-scraper/scraper.py`:

```python
def scrape(query: str | None = None, url: str | None = None) -> dict:
    google_data: dict = {}
    website_data: dict = {}
    booking_data: dict = {}
    website_url = url

    if query and not url:
        try:
            place_id = places_search(query)
            if place_id:
                google_data = places_details(place_id)
                website_url = google_data.get("website")
        except Exception:
            pass

    if website_url:
        try:
            html = fetch_website(website_url)
            if html:
                website_data = claude_extract(html)
        except Exception:
            pass

    if not website_data.get("room_types") and query:
        name = google_data.get("name") or query
        city = google_data.get("city") or ""
        try:
            bhtml = playwright_fetch(booking_search_url(name, city))
            if bhtml:
                booking_data = claude_extract(bhtml)
        except Exception:
            pass

    return merge(google_data, website_data, booking_data)
```

- [ ] **Step 4: Run all tests**

```bash
cd hotel-scraper
pytest tests/test_scraper.py -v
```

Expected: all 21 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hotel-scraper/scraper.py hotel-scraper/tests/test_scraper.py
git commit -m "feat: scrape() orchestrator — Google + website + Booking.com"
```

---

### Task 7: Flask route tests

**Files:**
- Create: `hotel-scraper/tests/test_app.py`

- [ ] **Step 1: Write Flask route tests**

Create `hotel-scraper/tests/test_app.py`:

```python
import json
import pytest
from unittest.mock import patch
from app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"

def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"html" in resp.data.lower()

def test_scrape_requires_query_or_url(client):
    resp = client.post("/scrape", json={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()

def test_scrape_returns_hotel_dict(client):
    from scraper import empty_hotel
    mock_result = {**empty_hotel(), "name": "Mocked Hotel", "city": "Berlin"}
    with patch("app.scrape", return_value=mock_result):
        resp = client.post("/scrape", json={"query": "Mocked Hotel Berlin"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Mocked Hotel"

def test_export_returns_json_file(client):
    hotel = {"name": "Test Hotel", "city": "Munich", "stars": 4}
    resp = client.post("/export", json={"data": hotel})
    assert resp.status_code == 200
    assert resp.content_type == "application/json"
    assert b"Test Hotel" in resp.data

def test_export_strips_underscore_fields(client):
    hotel = {"name": "Test Hotel", "_sources": {"name": "google"}}
    resp = client.post("/export", json={"data": hotel})
    exported = json.loads(resp.data)
    assert "name" in exported
    assert "_sources" not in exported
```

- [ ] **Step 2: Run tests**

```bash
cd hotel-scraper
pytest tests/test_app.py -v
```

Expected:
```
tests/test_app.py::test_healthz PASSED
tests/test_app.py::test_index_returns_html PASSED
tests/test_app.py::test_scrape_requires_query_or_url PASSED
tests/test_app.py::test_scrape_returns_hotel_dict PASSED
tests/test_app.py::test_export_returns_json_file PASSED
tests/test_app.py::test_export_strips_underscore_fields PASSED
6 passed
```

- [ ] **Step 3: Commit**

```bash
git add hotel-scraper/tests/test_app.py
git commit -m "test: Flask route smoke tests"
```

---

### Task 8: Frontend — Complete 3-Screen UI

**Files:**
- Modify: `hotel-scraper/templates/index.html`

Replace the placeholder with the full UI. Design tokens are identical to the import-tool.

- [ ] **Step 1: Write the complete index.html**

Replace `hotel-scraper/templates/index.html` with:

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <title>Hotel Scraper</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary:       #2a6fdb;
      --primary-hover: #1e5bbf;
      --primary-light: #ddeaff;
      --success:       #1a9e5c;
      --success-light: #d4f0e3;
      --warning:       #d97706;
      --warning-light: #fef3c7;
      --danger:        #dc2626;
      --danger-light:  #fee2e2;
      --text:          #0b1b3a;
      --text-muted:    #4a5878;
      --border:        #dde3ee;
      --bg:            #f4f6fb;
      --white:         #ffffff;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Roboto', sans-serif; font-size: 14px; line-height: 1.6; color: var(--text); background: var(--bg); }

    .navbar {
      background: linear-gradient(90deg, var(--text) 0%, var(--text-muted) 100%);
      height: 52px; display: flex; align-items: center; padding: 0 24px;
      position: sticky; top: 0; z-index: 100;
    }
    .nav-title { color: #fff; font-size: 15px; font-weight: 700; }

    .container { max-width: 720px; margin: 0 auto; padding: 32px 16px; }
    .card { background: var(--white); border: 1px solid var(--border); border-radius: 10px; padding: 28px; margin-bottom: 20px; }
    .card-title { font-size: 16px; font-weight: 700; margin-bottom: 20px; }

    label { display: block; font-weight: 500; margin-bottom: 4px; margin-top: 14px; font-size: 13px; }
    label:first-child { margin-top: 0; }
    input[type=text], input[type=number], textarea {
      width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px;
      font-size: 14px; font-family: inherit; color: var(--text); background: var(--white);
    }
    input:focus, textarea:focus { outline: none; border-color: var(--primary); }
    input.field-error { border-color: var(--danger); }
    textarea { resize: vertical; min-height: 70px; }

    .divider { display: flex; align-items: center; gap: 12px; margin: 20px 0; color: var(--text-muted); font-size: 13px; }
    .divider::before, .divider::after { content: ''; flex: 1; border-top: 1px solid var(--border); }

    .btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 9px 20px; border: none; border-radius: 6px; cursor: pointer;
      font-size: 14px; font-weight: 500; font-family: inherit;
    }
    .btn-primary { background: var(--primary); color: #fff; }
    .btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
    .btn-secondary { background: var(--border); color: var(--text); }
    .btn-secondary:hover:not(:disabled) { background: #c8d0de; }
    .btn-success { background: var(--success); color: #fff; }
    .btn:disabled { opacity: .5; cursor: not-allowed; }

    .field-row { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 12px; }
    .field-label { font-weight: 500; font-size: 13px; min-width: 140px; padding-top: 9px; flex-shrink: 0; }
    .field-input { flex: 1; }
    .field-input input, .field-input textarea { margin: 0; }
    .badge {
      display: inline-block; font-size: 11px; font-weight: 600;
      padding: 2px 7px; border-radius: 4px; white-space: nowrap;
      flex-shrink: 0; margin-top: 9px;
    }
    .badge-google  { background: #e8f0fe; color: #1a56db; }
    .badge-website { background: var(--success-light); color: #1a6b3c; }
    .badge-booking { background: var(--warning-light); color: #92400e; }
    .badge-manual  { background: var(--bg); color: var(--text-muted); border: 1px solid var(--border); }

    .section-heading {
      font-size: 12px; font-weight: 700; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: .05em;
      margin: 24px 0 12px; border-bottom: 1px solid var(--border); padding-bottom: 6px;
    }
    .room-entry {
      border: 1px solid var(--border); border-radius: 8px; padding: 14px;
      margin-bottom: 10px; position: relative; background: var(--bg);
    }
    .room-remove { position: absolute; top: 10px; right: 10px; background: none; border: none; cursor: pointer; color: var(--danger); font-size: 16px; }
    .room-row { display: flex; gap: 10px; }
    .room-row input { flex: 1; }

    .spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }

    .alert { padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; }
    .alert-danger { background: var(--danger-light); color: var(--danger); border: 1px solid #fca5a5; }

    .actions { display: flex; gap: 12px; margin-top: 24px; }
    [data-screen] { display: none; }
    [data-screen].active { display: block; }
  </style>
</head>
<body>
<nav class="navbar">
  <span class="nav-title">Hotel Scraper</span>
</nav>

<div class="container">

  <!-- Screen 1: Suche -->
  <div data-screen="search" class="active">
    <div class="card">
      <div class="card-title">Hotel suchen</div>
      <div id="search-error" class="alert alert-danger" style="display:none"></div>
      <label>Hotel-Name</label>
      <input type="text" id="hotel-name" placeholder="z.B. Hotel Adlon">
      <label>Stadt</label>
      <input type="text" id="hotel-city" placeholder="z.B. Berlin">
      <div class="divider">oder</div>
      <label>URL direkt eingeben</label>
      <input type="text" id="hotel-url" placeholder="https://www.hotel-adlon.de">
      <div class="actions">
        <button class="btn btn-primary" id="search-btn" onclick="startSearch()">Suchen →</button>
      </div>
    </div>
  </div>

  <!-- Screen 2: Review & Edit -->
  <div data-screen="review">
    <div class="card">
      <div class="card-title">Hotel-Daten prüfen &amp; bearbeiten</div>
      <div id="review-error" class="alert alert-danger" style="display:none"></div>
      <div id="review-fields"></div>
      <div class="actions">
        <button class="btn btn-secondary" onclick="showScreen('search')">← Zurück</button>
        <button class="btn btn-success" id="export-btn" onclick="exportData()">JSON exportieren</button>
      </div>
    </div>
  </div>

</div>

<script>
  let hotelData = {};

  function showScreen(name) {
    document.querySelectorAll('[data-screen]').forEach(el => el.classList.remove('active'));
    document.querySelector(`[data-screen="${name}"]`).classList.add('active');
  }

  async function startSearch() {
    const name = document.getElementById('hotel-name').value.trim();
    const city = document.getElementById('hotel-city').value.trim();
    const url  = document.getElementById('hotel-url').value.trim();
    const err  = document.getElementById('search-error');

    if (!name && !url) {
      err.textContent = 'Bitte Hotel-Name oder URL eingeben.';
      err.style.display = 'block';
      return;
    }
    err.style.display = 'none';

    const btn = document.getElementById('search-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Wird gesucht…';

    const payload = {};
    if (name) payload.query = city ? `${name} ${city}` : name;
    if (url)  payload.url   = url;

    try {
      const resp = await fetch('scrape', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Unbekannter Fehler');
      hotelData = data;
      renderReview();
      showScreen('review');
    } catch (e) {
      err.textContent = `Fehler: ${e.message}`;
      err.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Suchen →';
    }
  }

  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function sourceBadge(key) {
    const src = (hotelData._sources || {})[key];
    if (!src) return '<span class="badge badge-manual">manuell</span>';
    return `<span class="badge badge-${src}">${src}</span>`;
  }

  function fieldRow(labelText, key, type = 'text') {
    const val = hotelData[key] ?? '';
    const required = ['name','address','city'].includes(key);
    const errClass = required && !val ? ' field-error' : '';
    return `
      <div class="field-row">
        <span class="field-label">${esc(labelText)}${required ? ' *' : ''}</span>
        <div class="field-input">
          <input type="${type}" class="${errClass.trim()}" data-key="${key}"
            value="${esc(val)}" oninput="onField(this)">
        </div>
        ${sourceBadge(key)}
      </div>`;
  }

  function textareaRow(labelText, key) {
    const val = hotelData[key] ?? '';
    return `
      <div class="field-row">
        <span class="field-label">${esc(labelText)}</span>
        <div class="field-input">
          <textarea data-key="${key}" oninput="onField(this)">${esc(val)}</textarea>
        </div>
        ${sourceBadge(key)}
      </div>`;
  }

  function roomHtml(room, idx) {
    return `
      <div class="room-entry" data-room="${idx}">
        <button class="room-remove" onclick="removeRoom(${idx})">✕</button>
        <div class="room-row">
          <input type="text" placeholder="Zimmertyp-Name" value="${esc(room.name)}"
            oninput="onRoom(${idx},'name',this.value)">
          <input type="text" placeholder="Preis ab (€)" style="max-width:110px" value="${esc(room.price_from)}"
            oninput="onRoom(${idx},'price_from',this.value)">
        </div>
        <input type="text" style="margin-top:8px" placeholder="Beschreibung" value="${esc(room.description)}"
          oninput="onRoom(${idx},'description',this.value)">
      </div>`;
  }

  function renderReview() {
    const amenities = (hotelData.amenities || []).join(', ');
    const rooms     = hotelData.room_types || [];
    let html = '';

    html += '<div class="section-heading">Stammdaten</div>';
    html += fieldRow('Name', 'name');
    html += fieldRow('Adresse', 'address');
    html += fieldRow('Stadt', 'city');
    html += fieldRow('PLZ', 'zip');
    html += fieldRow('Land', 'country');
    html += fieldRow('Telefon', 'phone');
    html += fieldRow('E-Mail', 'email');
    html += fieldRow('Website', 'website');
    html += fieldRow('Sterne', 'stars', 'number');
    html += fieldRow('Check-in', 'checkin_time');
    html += fieldRow('Check-out', 'checkout_time');

    html += '<div class="section-heading">Beschreibung</div>';
    html += textareaRow('Kurzbeschreibung', 'short_description');
    html += textareaRow('Beschreibung', 'description');

    html += '<div class="section-heading">Zimmertypen</div>';
    html += '<div id="rooms-container">';
    rooms.forEach((r, i) => { html += roomHtml(r, i); });
    html += '</div>';
    html += '<button class="btn btn-secondary" style="margin-top:8px" onclick="addRoom()">+ Zimmertyp hinzufügen</button>';

    html += '<div class="section-heading">Ausstattung</div>';
    html += `<input type="text" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:14px;font-family:inherit"
      placeholder="WiFi, Pool, Spa, …" value="${esc(amenities)}" oninput="onAmenities(this)">`;

    html += '<div class="section-heading">Social Media</div>';
    html += fieldRow('Facebook', 'facebook');
    html += fieldRow('Instagram', 'instagram');
    html += fieldRow('Twitter / X', 'twitter');

    document.getElementById('review-fields').innerHTML = html;
    updateExportBtn();
  }

  function onField(el) {
    hotelData[el.dataset.key] = el.value;
    const required = ['name','address','city'].includes(el.dataset.key);
    if (required) {
      el.className = el.value.trim() ? '' : 'field-error';
      updateExportBtn();
    }
  }

  function onAmenities(el) {
    hotelData.amenities = el.value.split(',').map(s => s.trim()).filter(Boolean);
  }

  function onRoom(idx, field, val) {
    if (hotelData.room_types?.[idx]) hotelData.room_types[idx][field] = val;
  }

  function addRoom() {
    hotelData.room_types = hotelData.room_types || [];
    const idx = hotelData.room_types.length;
    hotelData.room_types.push({name:'', description:'', price_from:''});
    document.getElementById('rooms-container').insertAdjacentHTML(
      'beforeend', roomHtml({name:'',description:'',price_from:''}, idx)
    );
  }

  function removeRoom(idx) {
    hotelData.room_types.splice(idx, 1);
    renderReview();
  }

  function updateExportBtn() {
    const ok = ['name','address','city'].every(k => (hotelData[k] || '').toString().trim());
    document.getElementById('export-btn').disabled = !ok;
  }

  async function exportData() {
    const btn = document.getElementById('export-btn');
    btn.disabled = true;
    btn.textContent = 'Wird exportiert…';
    try {
      const resp = await fetch('export', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({data: hotelData}),
      });
      const blob = await resp.blob();
      const slug = (hotelData.name || 'hotel').replace(/\s+/g,'_').toLowerCase();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${slug}.json`;
      a.click();
    } catch (e) {
      const err = document.getElementById('review-error');
      err.textContent = `Export fehlgeschlagen: ${e.message}`;
      err.style.display = 'block';
    } finally {
      updateExportBtn();
      btn.textContent = 'JSON exportieren';
    }
  }
</script>
</body>
</html>
```

- [ ] **Step 2: Start the dev server and verify manually**

```bash
cd hotel-scraper
FLASK_DEBUG=1 python app.py
```

Open http://localhost:5055 in the browser and check:
- Screen 1 renders Name + Stadt fields, divider, URL field, Suchen button
- Submitting without input shows the error "Bitte Hotel-Name oder URL eingeben."
- The `/scrape` endpoint can be hit manually: `curl -s -X POST http://localhost:5055/scrape -H 'Content-Type: application/json' -d '{"query":"test"}' | python3 -m json.tool` — should return the empty hotel structure
- Screen 2 renders all field groups with badges, rooms section with add/remove buttons, amenities input, export button
- Export button is disabled when Name/Adresse/Stadt are empty; enabled when all three are filled
- Clicking "JSON exportieren" (with fields filled) downloads a .json file

- [ ] **Step 3: Run all tests**

```bash
cd hotel-scraper
pytest tests/ -v
```

Expected: all 27 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add hotel-scraper/templates/index.html
git commit -m "feat: complete frontend — search + review/edit screens"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Name + Stadt query input | Task 8 — Screen 1 |
| URL direkt input | Task 8 — Screen 1 |
| Loading-Spinner | Task 8 — `startSearch()` |
| Google Places → Stammdaten | Task 3 |
| Hotel-Website + Claude extraction | Task 4 |
| Booking.com optional (Playwright) | Task 5 |
| merge() mit _sources | Task 2 |
| scrape() Orchestrator | Task 6 |
| Fehlerbehandlung — alle Quellen | Task 6 (try/except blocks) |
| Leeres Formular wenn alle Quellen fehlschlagen | Task 6 returns `empty_hotel()` via merge |
| Review & Edit — alle Felder editierbar | Task 8 — Screen 2 |
| Quelle-Badges pro Feld | Task 8 — `sourceBadge()` |
| Zimmertypen — hinzufügen/entfernen | Task 8 — `addRoom()`, `removeRoom()` |
| Pflichtfelder (name, address, city) rot markiert | Task 8 — `field-error` class |
| Export-Button gesperrt bis Pflichtfelder OK | Task 8 — `updateExportBtn()` |
| JSON-Export als Datei-Download | Task 7 + Task 8 |
| `_sources` aus Export herausgefiltert | Task 7 — `test_export_strips_underscore_fields` |
| scraper.py Flask-agnostisch (V2-ready) | Task 1 — `scrape()` returns dict |
| /healthz Route | Task 7 |

**Placeholder scan:** Keine TBDs. Alle Schritte haben vollständigen Code.

**Type consistency:**
- `empty_hotel() -> dict` — Task 1, referenziert in Tasks 2, 4, 6, 7 ✓
- `merge(google: dict, website: dict, booking: dict) -> dict` — Task 2, aufgerufen in Task 6 ✓
- `scrape(query: str | None, url: str | None) -> dict` — Task 1 (Stub), Task 6 (Impl), aufgerufen in Task 7 ✓
- `claude_extract(html: str) -> dict` — Task 4, aufgerufen in Task 6 ✓
- `_parse_google_result(raw: dict) -> dict` — Task 3, aufgerufen in `places_details()` ✓
