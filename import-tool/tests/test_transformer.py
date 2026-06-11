from transformer import get_fields, ENTITY_TYPES, validate_field
from transformer import (
    transform_date, transform_country, transform_gender,
    transform_title, transform_reservation_status
)
from transformer import transform, TransformResult
from transformer import generate_fallback_email

def test_guest_required_fields():
    fields = get_fields("guest")
    required = [f["name"] for f in fields if f["required"]]
    assert set(required) == {"first_name", "last_name"}

def test_company_required_fields():
    fields = get_fields("company")
    required = [f["name"] for f in fields if f["required"]]
    assert set(required) == {"name"}

def test_reservation_required_fields():
    fields = get_fields("reservation")
    required = [f["name"] for f in fields if f["required"]]
    # Zimmer ist optional — HotelFriend akzeptiert unallokierte Buchungen ohne Zimmernummer
    assert set(required) == {"first_name", "last_name", "Check In", "Check Out", "Zimmertyp"}

def test_entity_types_known():
    assert set(ENTITY_TYPES) == {"guest", "company", "reservation"}

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

# --- Named-Month-Datumsformat (z.B. Direktbuchung-Export) ---
def test_date_named_month_abbreviated_en():
    assert transform_date("02 Feb. 2026") == "2026-02-02"

def test_date_named_month_abbreviated_en_no_dot():
    assert transform_date("14 Jun 2026") == "2026-06-14"

def test_date_named_month_german_maerz():
    assert transform_date("23 März 2026") == "2026-03-23"

def test_date_named_month_german_mai():
    assert transform_date("01 Mai 2026") == "2026-05-01"

def test_date_named_month_german_juni():
    assert transform_date("22 Juni 2026") == "2026-06-22"

def test_date_named_month_german_juli():
    assert transform_date("02 Juli 2026") == "2026-07-02"

def test_date_named_month_german_aug():
    assert transform_date("08 Aug. 2026") == "2026-08-08"

def test_date_named_month_german_dez():
    assert transform_date("18 Dez. 2026") == "2026-12-18"

def test_date_named_month_day_padding():
    assert transform_date("5 Apr. 2026") == "2026-04-05"

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

# --- Gender-Ableitung aus Title ---
def _guest_row(title="", gender="", email="test@example.com"):
    row = {"first_name": "Max", "last_name": "Müller", "email": email,
           "title": title, "gender": gender}
    mapping = {k: k for k in row}
    return transform([row], "guest", mapping).valid_rows

def test_gender_derived_from_mr():
    rows = _guest_row(title="mr")
    assert rows[0]["gender"] == "1"

def test_gender_derived_from_mrs():
    rows = _guest_row(title="mrs")
    assert rows[0]["gender"] == "2"

def test_gender_derived_from_miss():
    rows = _guest_row(title="miss")
    assert rows[0]["gender"] == "2"

def test_gender_explicit_takes_priority():
    rows = _guest_row(title="mr", gender="2")
    assert rows[0]["gender"] == "2"

def test_gender_not_derived_without_title():
    rows = _guest_row(title="", gender="")
    assert rows[0].get("gender", "") == ""

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

def test_transform_missing_name_auto_fills_placeholder():
    # Empty first_name → auto-filled with "-" so import never fails on missing names
    rows = [{"Vorname": "", "Nachname": "Müller", "E-Mail": ""}]
    result = transform(rows, "guest", _guest_mapping())
    assert len(result.valid_rows) == 1
    assert result.valid_rows[0]["first_name"] == "-"

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

from transformer import suggest_mapping

# --- generate_fallback_email ---

def test_fallback_email_normal_name():
    assert generate_fallback_email("Felix", "Marggraf", 1) == "felix.marggraf@import-hotelfriend.de"

def test_fallback_email_umlaut():
    assert generate_fallback_email("Jörg", "Müller", 1) == "joerg.mueller@import-hotelfriend.de"

def test_fallback_email_parenthetical_stripped():
    assert generate_fallback_email("Felix", "Marggraf (XL)", 1) == "felix.marggraf@import-hotelfriend.de"

def test_fallback_email_no_first_name():
    assert generate_fallback_email("", "Müller", 5) == "gast.mueller.5@import-hotelfriend.de"

def test_fallback_email_placeholder_first_name():
    assert generate_fallback_email("-", "Müller", 3) == "gast.mueller.3@import-hotelfriend.de"

def test_fallback_email_nn_placeholder():
    assert generate_fallback_email("N. n.", "N. n.", 7) == "gast.7@import-hotelfriend.de"

def test_fallback_email_no_name():
    # "no" / "name" als separate Felder → werden als echte Namen behandelt
    assert generate_fallback_email("no", "name", 9) == "no.name@import-hotelfriend.de"

def test_fallback_email_no_last_name():
    assert generate_fallback_email("Felix", "", 2) == "felix.gast.2@import-hotelfriend.de"

def test_fallback_email_in_reservation_transform():
    """Reservierungen ohne E-Mail bekommen automatisch eine Fallback-Adresse."""
    rows = [{
        "Vorname": "Felix", "Nachname": "Marggraf",
        "Check In": "2025-01-01", "Check Out": "2025-01-05",
        "Zimmertyp": "Doppelzimmer",
    }]
    mapping = {
        "Vorname": "first_name", "Nachname": "last_name",
        "Check In": "Check In", "Check Out": "Check Out",
        "Zimmertyp": "Zimmertyp",
    }
    result = transform(rows, "reservation", mapping)
    assert len(result.valid_rows) == 1
    assert result.valid_rows[0]["email"] == "felix.marggraf@import-hotelfriend.de"
    assert result.valid_rows[0]["_system_changes"].get("email") == ""

def test_fallback_email_not_overwritten_when_present():
    """Vorhandene E-Mail darf nicht überschrieben werden."""
    rows = [{
        "Vorname": "Felix", "Nachname": "Marggraf", "E-Mail": "felix@example.com",
        "Check In": "2025-01-01", "Check Out": "2025-01-05",
        "Zimmertyp": "Doppelzimmer",
    }]
    mapping = {
        "Vorname": "first_name", "Nachname": "last_name", "E-Mail": "email",
        "Check In": "Check In", "Check Out": "Check Out",
        "Zimmertyp": "Zimmertyp",
    }
    result = transform(rows, "reservation", mapping)
    assert result.valid_rows[0]["email"] == "felix@example.com"

def test_fallback_email_no_name_uses_index():
    """Einträge ohne Namen bekommen gast.{index}@import-hotelfriend.de."""
    rows = [
        {"Vorname": "N. n.", "Nachname": "N. n.",
         "Check In": "2025-01-01", "Check Out": "2025-01-05", "Zimmertyp": "EZ"},
        {"Vorname": "N. n.", "Nachname": "N. n.",
         "Check In": "2025-02-01", "Check Out": "2025-02-05", "Zimmertyp": "EZ"},
    ]
    mapping = {
        "Vorname": "first_name", "Nachname": "last_name",
        "Check In": "Check In", "Check Out": "Check Out", "Zimmertyp": "Zimmertyp",
    }
    result = transform(rows, "reservation", mapping)
    emails = [r["email"] for r in result.valid_rows]
    assert emails[0] == "gast.1@import-hotelfriend.de"
    assert emails[1] == "gast.2@import-hotelfriend.de"
    assert emails[0] != emails[1]  # eindeutig durch Index

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
