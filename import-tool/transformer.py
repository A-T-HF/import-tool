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
