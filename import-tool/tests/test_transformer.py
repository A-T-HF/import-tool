from transformer import get_fields, ENTITY_TYPES, validate_field
from transformer import (
    transform_date, transform_country, transform_gender,
    transform_title, transform_reservation_status
)
from transformer import transform, TransformResult

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
