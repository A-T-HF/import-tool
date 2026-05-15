from dataclasses import dataclass, field
from typing import Any
from rapidfuzz import process, fuzz

ENTITY_TYPES = ["guest", "company", "reservation"]

_GUEST_FIELDS = [
    {"name": "first_name",    "required": True,  "transformer": None,        "validator": None},
    {"name": "last_name",     "required": True,  "transformer": None,        "validator": None},
    {"name": "email",         "required": False, "transformer": None,        "validator": "email"},
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
    {"name": "email",          "required": False, "transformer": None,      "validator": "email"},
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
    {"name": "email",      "required": False, "transformer": None,   "validator": "email"},
    {"name": "Check In",   "required": True,  "transformer": "date", "validator": None},
    {"name": "Check Out",  "required": True,  "transformer": "date", "validator": None},
    {"name": "Zimmer",     "required": False, "transformer": None,   "validator": None},
    {"name": "Zimmertyp",  "required": True,  "transformer": None,   "validator": None},
    {"name": "Summe",      "required": False, "transformer": "amount", "validator": None},
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
    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",  # Mews: "29.01.2026 15:00"
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
    # Englisch (HotelFriend-Zielwerte)
    "new": "new",
    "confirmed": "confirmed",
    "due_in": "due_in",
    "check_in": "check_in",
    "due_out": "due_out",
    "check_out": "check_out",
    "cancelled_by_guest": "cancelled_by_guest",
    "cancelled_by_hf": "cancelled_by_hf",
    "no_show": "no_show",
    "booking_offer": "booking_offer",
    # Deutsch (HotelFriend / Mews)
    "neu": "new",
    "bestätigt": "confirmed",
    "fällig (anreise)": "due_in",
    "fällig anreise": "due_in",
    "eingecheckt": "check_in",
    "fällig (abreise)": "due_out",
    "fällig abreise": "due_out",
    "ausgecheckt": "check_out",
    "storniert (gast)": "cancelled_by_guest",
    "storniert": "cancelled_by_guest",   # generisch → Gast
    "storniert (hotel)": "cancelled_by_hf",
    "no show": "no_show",
    "optional": "booking_offer",
    "angebot": "booking_offer",
}

def transform_amount(value: str) -> str | None:
    """Strip currency symbols and convert German decimal comma to dot. '€129,00' → '129.00'"""
    if not value or not value.strip():
        return None
    v = re.sub(r"[€$£\s]", "", value.strip()).replace(",", ".")
    # If there are multiple dots (thousands separator), keep only last
    parts = v.split(".")
    if len(parts) > 2:
        v = "".join(parts[:-1]) + "." + parts[-1]
    return v if v else None


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

_TRANSFORMERS = {
    "date":                 transform_date,
    "country":              transform_country,
    "gender":               transform_gender,
    "title":                transform_title,
    "reservation_status":   transform_reservation_status,
    "amount":               transform_amount,
}

@dataclass
class TransformResult:
    valid_rows: list[dict[str, Any]] = field(default_factory=list)
    error_rows: list[dict[str, Any]] = field(default_factory=list)


def transform(rows: list[dict], entity_type: str, mapping: dict[str, str]) -> TransformResult:
    """
    rows:        list of dicts with source column names as keys
    entity_type: "guest" | "company" | "reservation"
    mapping:     {source_col: target_field} — target "_ignore" or "" means skip column
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

        # Apply "-" placeholder for missing name fields so imports never fail on empty names
        if entity_type in ("guest", "reservation"):
            for fname in ("first_name", "last_name"):
                if not mapped.get(fname):
                    mapped[fname] = "-"

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

        # Derive cancellation status from row content when Status is empty (reservations only)
        if entity_type == "reservation" and not mapped.get("Status"):
            row_text = " ".join(str(v) for v in raw_row.values()).lower()
            if "storniert" in row_text or "cancelled" in row_text or "canceled" in row_text:
                mapped["Status"] = "cancelled_by_guest"

        # Derive gender from title when gender is missing (guests only)
        if entity_type == "guest" and not mapped.get("gender"):
            title = mapped.get("title", "").lower()
            if title == "mr":
                mapped["gender"] = "1"
            elif title in ("mrs", "miss"):
                mapped["gender"] = "2"

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
    "Zimmer":       ["Room", "Zimmer", "Zimmer-Nr", "Room Number", "Raumnummer"],
    "Zimmertyp":    ["Room Type", "Zimmertyp", "Kategorie", "Raumkategorie"],
    "Summe":        ["Total", "Betrag", "Preis", "Sum", "Amount", "Gesamtbetrag"],
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

    # Build lookup: alias (lowercase) → field name
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
