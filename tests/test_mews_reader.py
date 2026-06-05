from datetime import datetime, date
from app.mews_reader import (
    _parse_person_name,
    _group_display_name,
    _map_nationality,
    _fmt_date,
    _read_guests,
    _read_companies,
    _read_reservations,
)


# ── _parse_person_name ────────────────────────────────────────────────────────

def test_parse_normal_name():
    assert _parse_person_name("Müller", "Hans") == ("Hans", "Müller")

def test_parse_compound_name_splits_vorname():
    # Mews "Company, Person Name" format
    first, last = _parse_person_name(
        "University Of Hamburg, Christine Quentin", "Christine Quentin"
    )
    assert first == "Christine"
    assert last == "Quentin"

def test_parse_compound_single_word_vorname():
    # Vorname has only one word → first_name empty, last_name = vorname
    first, last = _parse_person_name("ACME Corp, Alice", "Alice")
    assert first == ""
    assert last == "Alice"

def test_parse_empty_nachname():
    assert _parse_person_name("", "Anna Meier") == ("Anna Meier", "")

def test_parse_none_values():
    first, last = _parse_person_name(None, None)
    assert first == "" and last == ""

def test_parse_strips_whitespace():
    first, last = _parse_person_name(" Müller ", " Hans ")
    assert first == "Hans" and last == "Müller"


# ── _group_display_name ───────────────────────────────────────────────────────

def test_group_strips_mews_suffix():
    assert _group_display_name("Hesse – Kastein-9-2-55EE") == "Hesse – Kastein"

def test_group_strips_long_suffix():
    assert _group_display_name("University Of Hamburg Business School-28-1-DD49") == \
        "University Of Hamburg Business School"

def test_group_no_suffix():
    assert _group_display_name("Normalname") == "Normalname"

def test_group_empty():
    assert _group_display_name("") == ""


# ── _map_nationality ──────────────────────────────────────────────────────────

def test_nationality_deutschland():
    assert _map_nationality("Deutschland") == "DE"

def test_nationality_schweiz():
    assert _map_nationality("Schweiz") == "CH"

def test_nationality_long_gb():
    assert _map_nationality(
        "Vereinigtes Königreich Großbritannien und Nordirland"
    ) == "GB"

def test_nationality_case_insensitive():
    assert _map_nationality("DEUTSCHLAND") == "DE"

def test_nationality_unknown():
    assert _map_nationality("Unbekanntes Land") is None

def test_nationality_none():
    assert _map_nationality(None) is None


# ── _fmt_date ─────────────────────────────────────────────────────────────────

def test_fmt_date_datetime():
    assert _fmt_date(datetime(2026, 1, 29, 15, 0)) == "2026-01-29"

def test_fmt_date_date():
    assert _fmt_date(date(2026, 3, 15)) == "2026-03-15"

def test_fmt_date_string_passthrough():
    assert _fmt_date("2026-01-29") == "2026-01-29"

def test_fmt_date_none():
    assert _fmt_date(None) is None

def test_fmt_date_empty_string():
    assert _fmt_date("") is None


# ── _read_guests ──────────────────────────────────────────────────────────────

def _res(nachname, vorname, email="", telefon="", nationalität="", kennung=""):
    return {
        "Nachname": nachname,
        "Vorname": vorname,
        "E-Mail": email,
        "Telefon": telefon,
        "Staatsangehörigkeit des Gastes": nationalität,
        "Kennung": kennung,
        "Anreise": datetime(2026, 1, 1),
        "Abreise": datetime(2026, 1, 2),
        "Raumnummer": "101",
        "Raumkategorie": "Doppelzimmer",
        "Gesamtbetrag": 100,
        "Status": "Bestätigt",
        "Firma": "",
        "Firma Kennung": "",
        "Gruppenname": "",
    }


def test_guests_basic():
    rows = [_res("Müller", "Hans", email="hans@example.com", kennung="uuid-1")]
    guests = _read_guests(rows)
    assert len(guests) == 1
    g = guests[0]
    assert g["first_name"] == "Hans"
    assert g["last_name"] == "Müller"
    assert g["email"] == "hans@example.com"
    assert g["_mews_id"] == "uuid-1"


def test_guests_deduplicated():
    rows = [
        _res("Müller", "Hans", email="hans@example.com"),
        _res("Müller", "Hans", email="hans@example.com"),
    ]
    assert len(_read_guests(rows)) == 1


def test_guests_two_different_people():
    rows = [
        _res("Müller", "Hans", email="hans@example.com"),
        _res("Meier", "Anna", email="anna@example.com"),
    ]
    assert len(_read_guests(rows)) == 2


def test_guests_nationality_mapped():
    rows = [_res("Müller", "Hans", nationalität="Deutschland")]
    g = _read_guests(rows)[0]
    assert g["nationality"] == "DE"


def test_guests_unknown_nationality_omitted():
    rows = [_res("Müller", "Hans", nationalität="Irgendwo")]
    g = _read_guests(rows)[0]
    assert "nationality" not in g


def test_guests_no_email_omitted():
    rows = [_res("Müller", "Hans", email="")]
    g = _read_guests(rows)[0]
    assert "email" not in g


def test_guests_placeholder_when_no_name():
    rows = [_res("", "", email="info@hotel.de")]
    g = _read_guests(rows)[0]
    assert g["first_name"] == "-"
    assert g["last_name"] == "-"


def test_guests_compound_name_parsed():
    rows = [_res("ACME GmbH, Christine Quentin", "Christine Quentin")]
    g = _read_guests(rows)[0]
    assert g["first_name"] == "Christine"
    assert g["last_name"] == "Quentin"


def test_guests_company_only_skipped():
    # Pure company booking — no comma, last_name is a company → should be skipped
    rows = [_res("Muster AG", "Hans Müller")]
    assert _read_guests(rows) == []


def test_guests_gmbh_skipped():
    rows = [_res("Beispiel GmbH", "")]
    assert _read_guests(rows) == []


def test_guests_verein_not_skipped():
    # "Verein" alone is not a legal-entity suffix, should pass through
    rows = [_res("Verein", "Anna")]
    guests = _read_guests(rows)
    assert len(guests) == 1


def test_guests_name_source_original():
    rows = [_res("Müller", "Hans")]
    g = _read_guests(rows)[0]
    assert g["_name_source"] == "original"


def test_guests_name_source_none_when_no_first():
    rows = [_res("Müller", "")]
    g = _read_guests(rows)[0]
    assert g["_name_source"] == "none"


def test_guests_email_derivation():
    # "hans.mueller@example.com" + last_name "Müller" → first_name "Hans"
    rows = [_res("Müller", "", email="hans.mueller@example.com")]
    g = _read_guests(rows)[0]
    assert g["first_name"] == "Hans"
    assert g["_name_source"] == "derived_from_email"


def test_guests_email_derivation_initial():
    rows = [_res("Müller", "", email="h.mueller@example.com")]
    g = _read_guests(rows)[0]
    assert g["first_name"] == "H."
    assert g["_name_source"] == "derived_from_email"


def test_guests_email_no_match_keeps_placeholder():
    rows = [_res("Müller", "", email="info@hotel.de")]
    g = _read_guests(rows)[0]
    assert g["first_name"] == "-"
    assert g["_name_source"] == "none"


# ── _read_companies ───────────────────────────────────────────────────────────

def _res_with_group(gruppenname, kennung="", firma="", firma_kennung=""):
    r = _res("Müller", "Hans")
    r["Gruppenname"] = gruppenname
    r["Kennung"] = kennung
    r["Firma"] = firma
    r["Firma Kennung"] = firma_kennung
    return r


def test_companies_from_firma():
    rows = [_res_with_group("", firma="ACME GmbH", firma_kennung="fk-1")]
    companies = _read_companies(rows)
    assert len(companies) == 1
    assert companies[0]["name"] == "ACME GmbH"
    assert companies[0]["_mews_id"] == "fk-1"


def test_companies_from_group_multi_rows():
    rows = [
        _res_with_group("Muster Hotel-3-2-AB12", kennung="k1"),
        _res_with_group("Muster Hotel-3-2-AB12", kennung="k2"),
    ]
    companies = _read_companies(rows)
    assert len(companies) == 1
    assert companies[0]["name"] == "Muster Hotel"


def test_companies_single_group_row_excluded():
    rows = [_res_with_group("Solo Gast-1-1-FF00", kennung="k1")]
    assert _read_companies(rows) == []


def test_companies_deduplicated():
    rows = [
        _res_with_group("", firma="ACME GmbH"),
        _res_with_group("", firma="ACME GmbH"),
    ]
    assert len(_read_companies(rows)) == 1


def test_companies_group_name_cleaned():
    rows = [
        _res_with_group("Hesse – Kastein-9-2-55EE"),
        _res_with_group("Hesse – Kastein-9-2-55EE"),
    ]
    companies = _read_companies(rows)
    assert companies[0]["name"] == "Hesse – Kastein"


# ── _read_reservations ────────────────────────────────────────────────────────

def _full_res(**kwargs):
    defaults = {
        "Nachname": "Müller",
        "Vorname": "Hans",
        "E-Mail": "hans@example.com",
        "Anreise": datetime(2026, 1, 29, 15, 0),
        "Abreise": datetime(2026, 1, 30, 11, 0),
        "Raumnummer": "101",
        "Raumkategorie": "Doppelzimmer",
        "Gesamtbetrag": 129,
        "Status": "Bestätigt",
        "Kennung": "uuid-abc",
        "Telefon": "",
        "Staatsangehörigkeit des Gastes": "",
        "Firma": "",
        "Firma Kennung": "",
        "Gruppenname": "",
    }
    defaults.update(kwargs)
    return defaults


def test_reservation_basic_fields():
    r = _read_reservations([_full_res()])[0]
    assert r["first_name"] == "Hans"
    assert r["last_name"] == "Müller"
    assert r["Check In"] == "2026-01-29"
    assert r["Check Out"] == "2026-01-30"
    assert r["Zimmer"] == "101"
    assert r["Zimmertyp"] == "Doppelzimmer"
    assert r["Summe"] == "129"
    assert r["Status"] == "Bestätigt"
    assert r["_mews_id"] == "uuid-abc"


def test_reservation_no_email_omitted():
    r = _read_reservations([_full_res(**{"E-Mail": ""})])[0]
    assert "email" not in r


def test_reservation_with_email():
    r = _read_reservations([_full_res()])[0]
    assert r["email"] == "hans@example.com"


def test_reservation_compound_name():
    r = _read_reservations([
        _full_res(**{"Nachname": "ACME, Max Mustermann", "Vorname": "Max Mustermann"})
    ])[0]
    assert r["first_name"] == "Max"
    assert r["last_name"] == "Mustermann"


def test_reservation_placeholder_when_no_name():
    r = _read_reservations([_full_res(**{"Nachname": "", "Vorname": ""})])[0]
    assert r["first_name"] == "-"
    assert r["last_name"] == "-"


def test_reservation_count():
    rows = [_full_res(Kennung=f"uuid-{i}") for i in range(5)]
    assert len(_read_reservations(rows)) == 5
