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
