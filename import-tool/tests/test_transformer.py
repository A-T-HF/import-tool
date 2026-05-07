from transformer import get_fields, ENTITY_TYPES
from transformer import (
    transform_date, transform_country, transform_gender,
    transform_title, transform_reservation_status
)

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
