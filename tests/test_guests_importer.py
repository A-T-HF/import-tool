from app.guests_importer import (
    is_company_name,
    resolve_names,
    derive_name_from_email,
    compute_display_name,
    _resolve_all,
)


# ── is_company_name ──────────────────────────────────────────────────────────

def test_company_suffix_ag():
    assert is_company_name("Muster AG")

def test_company_suffix_gmbh():
    assert is_company_name("Beispiel GmbH")

def test_company_suffix_ug():
    assert is_company_name("Startup UG")

def test_company_suffix_gGmbH():
    assert is_company_name("Verein gGmbH")

def test_company_exact_match():
    assert is_company_name("GmbH")

def test_company_person_name():
    assert not is_company_name("Müller")

def test_company_person_with_ag_in_middle():
    assert not is_company_name("Hagen")   # ends in "gen", not " AG"


# ── resolve_names ────────────────────────────────────────────────────────────

def test_resolve_prefers_both_fields_over_partial():
    candidates = [
        {"first_name": "",    "last_name": "Müller"},
        {"first_name": "Max", "last_name": "Müller"},
    ]
    assert resolve_names(candidates) == ("Max", "Müller")

def test_resolve_longer_name_wins_on_tie():
    candidates = [
        {"first_name": "M",          "last_name": "Müller"},
        {"first_name": "Maximilian", "last_name": "Müller"},
    ]
    assert resolve_names(candidates) == ("Maximilian", "Müller")

def test_resolve_empty_candidates():
    assert resolve_names([]) == ("", "")

def test_resolve_single_candidate():
    assert resolve_names([{"first_name": "Anna", "last_name": "Meier"}]) == ("Anna", "Meier")

def test_resolve_merges_across_sources():
    # first source has last name only, second has both
    candidates = [
        {"first_name": "",    "last_name": "Schmidt"},
        {"first_name": "Eva", "last_name": "Schmidt"},
    ]
    first, last = resolve_names(candidates)
    assert first == "Eva" and last == "Schmidt"


# ── derive_name_from_email ───────────────────────────────────────────────────

def test_derive_full_name_pattern():
    assert derive_name_from_email("max.mueller@example.com", "Müller") == "Max"

def test_derive_initial_pattern():
    assert derive_name_from_email("m.mueller@example.com", "Müller") == "M."

def test_derive_no_match_wrong_last_name():
    assert derive_name_from_email("max.schmidt@example.com", "Müller") is None

def test_derive_generic_info():
    assert derive_name_from_email("info@hotel.de", "Müller") is None

def test_derive_generic_buchung():
    assert derive_name_from_email("buchung@hotel.de", "Müller") is None

def test_derive_no_dot_pattern():
    assert derive_name_from_email("maxmueller@example.com", "Müller") is None

def test_derive_missing_email():
    assert derive_name_from_email("", "Müller") is None

def test_derive_missing_last_name():
    assert derive_name_from_email("max.mueller@example.com", "") is None

def test_derive_case_insensitive():
    # Email local parts are lowercased before matching
    assert derive_name_from_email("Max.Mueller@example.com", "Müller") == "Max"


# ── compute_display_name ─────────────────────────────────────────────────────

def test_display_full_name():
    assert compute_display_name(1, "Hans", "Müller", None) == "Hans Müller"

def test_display_initial_plus_last():
    # "H." comes from email derivation — still treated as first_name
    assert compute_display_name(1, "H.", "Müller", None) == "H. Müller"

def test_display_last_only():
    assert compute_display_name(1, None, "Müller", None) == "Müller"

def test_display_email_fallback():
    assert compute_display_name(1, None, None, "hans@example.com") == "hans@example.com"

def test_display_gast_fallback():
    assert compute_display_name(42, None, None, None) == "Gast #42"


# ── _resolve_all (integration) ───────────────────────────────────────────────

def _make_guest(custid, first="", last="", email=None, salutation=None):
    return {
        "custid":     custid,
        "email":      email,
        "salutation": salutation,
        "candidates": [{"first_name": first, "last_name": last}],
    }

def test_resolve_all_original_source():
    rows = _resolve_all({1: _make_guest(1, "Max", "Müller")})
    assert rows[0]["name_source"] == "original"
    assert rows[0]["display_name"] == "Max Müller"

def test_resolve_all_derived_from_email():
    rows = _resolve_all({
        2: _make_guest(2, "", "Meier", email="anna.meier@example.com")
    })
    assert rows[0]["first_name"] == "Anna"
    assert rows[0]["name_source"] == "derived_from_email"

def test_resolve_all_none_source():
    rows = _resolve_all({3: _make_guest(3, "", "")})
    assert rows[0]["name_source"] == "none"
    assert rows[0]["display_name"] == "Gast #3"

def test_resolve_all_email_display_when_no_name():
    rows = _resolve_all({
        4: _make_guest(4, "", "", email="info@hotel.de")
    })
    # Generic mailbox → no derivation, but email used for display
    assert rows[0]["name_source"] == "none"
    assert rows[0]["display_name"] == "info@hotel.de"
