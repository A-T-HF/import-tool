from bookinglist_reader import (
    _split_guest_name,
    _parse_date,
    _parse_address,
    _map_status,
    _read_reservations,
    _read_guests,
)


# ── _split_guest_name ─────────────────────────────────────────────────────────

def test_split_simple():
    assert _split_guest_name("Gabriele Matzerath") == ("Gabriele", "Matzerath")

def test_split_compound_last_name():
    assert _split_guest_name("Hans von Müller") == ("Hans", "von Müller")

def test_split_single_token():
    first, last = _split_guest_name("Müller")
    assert first == "" and last == "Müller"

def test_split_empty():
    assert _split_guest_name("") == ("", "")

def test_split_strips_whitespace():
    assert _split_guest_name("  Anna  Bartley  ") == ("Anna", "Bartley")


# ── _parse_date ───────────────────────────────────────────────────────────────

def test_parse_date_dd_mm_yy():
    assert _parse_date("04.06.26") == "2026-06-04"

def test_parse_date_dd_mm_yyyy():
    assert _parse_date("04.06.2026") == "2026-06-04"

def test_parse_date_empty():
    assert _parse_date("") is None

def test_parse_date_none():
    assert _parse_date(None) is None


# ── _parse_address ────────────────────────────────────────────────────────────

def test_parse_address_full():
    result = _parse_address("Hans-Böckler-Straße 31, 65468 Trebur, , Deutschland")
    assert result["address"] == "Hans-Böckler-Straße 31"
    assert result["zip_code"] == "65468"
    assert result["city"] == "Trebur"
    assert result["country"] == "DE"

def test_parse_address_no_zip_no_country():
    result = _parse_address("In Kückhoven 11a,  Erkelenz, ,")
    assert result["address"] == "In Kückhoven 11a"
    assert result["city"] == "Erkelenz"
    assert "zip_code" not in result
    assert "country" not in result

def test_parse_address_empty():
    assert _parse_address("") == {}


# ── _map_status ───────────────────────────────────────────────────────────────

def test_map_status_gebucht():
    assert _map_status("Gebucht") == "confirmed"

def test_map_status_storniert():
    assert _map_status("Storniert") == "cancelled_by_guest"

def test_map_status_unknown():
    assert _map_status("Unbekannt") == ""


# ── _read_reservations ────────────────────────────────────────────────────────

_SAMPLE_ROWS = [
    {
        "Position": 1,
        "Gast": "Gabriele Matzerath",
        "Anreise": "04.06.26",
        "Abreise": "06.06.26",
        "Unterkunft": "1.8 Doppelzimmer",
        "E-Mail": "g@example.com",
        "Telefon": "+49 123 456",
        "Preis": 123.12,
        "Status": "Gebucht",
    },
    {
        "Position": 2,
        "Gast": "Kreuter Eventtechnik GmbH",
        "Anreise": "27.05.26",
        "Abreise": "28.05.26",
        "Unterkunft": "1.2 Familienzimmer",
        "E-Mail": "firma@example.de",
        "Telefon": "",
        "Preis": 140.0,
        "Status": "Storniert",
    },
]

def test_read_reservations_person():
    rows = _read_reservations([_SAMPLE_ROWS[0]])
    assert len(rows) == 1
    r = rows[0]
    assert r["first_name"] == "Gabriele"
    assert r["last_name"] == "Matzerath"
    assert r["Check In"] == "2026-06-04"
    assert r["Check Out"] == "2026-06-06"
    assert r["Zimmertyp"] == "1.8 Doppelzimmer"
    assert r["email"] == "g@example.com"
    assert r["Status"] == "confirmed"
    assert r["Summe"] == "123.12"

def test_read_reservations_company_uses_name_as_last():
    rows = _read_reservations([_SAMPLE_ROWS[1]])
    assert len(rows) == 1
    r = rows[0]
    assert r["first_name"] == "-"
    assert r["last_name"] == "Kreuter Eventtechnik GmbH"
    assert r["Status"] == "cancelled_by_guest"


# ── _read_guests ──────────────────────────────────────────────────────────────

def test_read_guests_skips_companies():
    rows = _read_guests(_SAMPLE_ROWS)
    names = [(r["first_name"], r["last_name"]) for r in rows]
    assert ("Gabriele", "Matzerath") in names
    assert all("GmbH" not in r["last_name"] for r in rows)

def test_read_guests_deduplicates():
    duplicate = _SAMPLE_ROWS[0].copy()
    rows = _read_guests([_SAMPLE_ROWS[0], duplicate])
    assert len(rows) == 1

def test_read_guests_includes_phone():
    rows = _read_guests([_SAMPLE_ROWS[0]])
    assert rows[0]["phone"] == "+49 123 456"
