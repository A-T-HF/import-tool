"""
Mews XLSX Reader

Reads a Mews 'Reservierungsbericht' Excel export and returns rows
pre-mapped to HotelFriend import format for guests, companies, and reservations.

Usage:
    from mews_reader import is_mews_xlsx, read_mews
    if is_mews_xlsx(path):
        rows = read_mews(path, "guest")
"""

import re
from datetime import date, datetime
from pathlib import Path

import openpyxl

from guests_importer import is_company_name, derive_name_from_email


# ── Mews XLSX detection ──────────────────────────────────────────────────────

_MEWS_SHEETS    = {"Reservierungen", "Parameter", "Nächte"}
_MEWS_COLS      = {"Nummer", "Anreise", "Abreise", "Kennung", "Raumkategorie"}


def is_mews_xlsx(file_or_path) -> bool:
    """Return True if the file is a Mews Reservierungsbericht XLSX."""
    try:
        wb = openpyxl.load_workbook(file_or_path, read_only=True, data_only=True)
        if not _MEWS_SHEETS.issubset(set(wb.sheetnames)):
            return False
        ws = wb["Reservierungen"]
        header_row = next(ws.iter_rows(max_row=1, values_only=True), None)
        if not header_row:
            return False
        return _MEWS_COLS.issubset(set(header_row))
    except Exception:
        return False


# ── German country names → ISO 3166-1 alpha-2 ────────────────────────────────

_DE_COUNTRY = {
    "deutschland": "DE",
    "österreich": "AT",
    "schweiz": "CH",
    "frankreich": "FR",
    "italien": "IT",
    "spanien": "ES",
    "portugal": "PT",
    "niederlande": "NL",
    "belgien": "BE",
    "luxemburg": "LU",
    "dänemark": "DK",
    "schweden": "SE",
    "norwegen": "NO",
    "finnland": "FI",
    "island": "IS",
    "irland": "IE",
    "vereinigtes königreich großbritannien und nordirland": "GB",
    "vereinigtes königreich": "GB",
    "großbritannien": "GB",
    "vereinigte staaten von amerika": "US",
    "vereinigte staaten": "US",
    "usa": "US",
    "kanada": "CA",
    "australien": "AU",
    "neuseeland": "NZ",
    "japan": "JP",
    "china": "CN",
    "südkorea": "KR",
    "indien": "IN",
    "brasilien": "BR",
    "argentinien": "AR",
    "mexiko": "MX",
    "türkei": "TR",
    "russland": "RU",
    "ukraine": "UA",
    "polen": "PL",
    "tschechien": "CZ",
    "tschechische republik": "CZ",
    "slowakei": "SK",
    "ungarn": "HU",
    "rumänien": "RO",
    "bulgarien": "BG",
    "kroatien": "HR",
    "serbien": "RS",
    "slowenien": "SI",
    "bosnien und herzegowina": "BA",
    "griechenland": "GR",
    "zypern": "CY",
    "malta": "MT",
    "lettland": "LV",
    "litauen": "LT",
    "estland": "EE",
    "weißrussland": "BY",
    "moldawien": "MD",
    "georgien": "GE",
    "armenien": "AM",
    "aserbaidschan": "AZ",
    "israel": "IL",
    "saudi-arabien": "SA",
    "vereinigte arabische emirate": "AE",
    "ägypten": "EG",
    "marokko": "MA",
    "tunesien": "TN",
    "südafrika": "ZA",
    "nigeria": "NG",
    "kenia": "KE",
    "singapur": "SG",
    "thailand": "TH",
    "indonesien": "ID",
    "malaysia": "MY",
    "philippinen": "PH",
    "vietnam": "VN",
    "kolumbien": "CO",
    "chile": "CL",
    "peru": "PE",
    "venezuela": "VE",
    "liechtenstein": "LI",
    "monaco": "MC",
    "andorra": "AD",
    "san marino": "SM",
    "nordmazedonien": "MK",
    "albanien": "AL",
    "montenegro": "ME",
}


def _map_nationality(german_name) -> str | None:
    if not german_name:
        return None
    return _DE_COUNTRY.get(str(german_name).strip().lower())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(v) -> str:
    return (str(v) if v is not None else "").strip()


def _fmt_date(v) -> str | None:
    """Convert openpyxl datetime/date or string to YYYY-MM-DD."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    s = _clean(v)
    return s if s else None


def _parse_person_name(nachname, vorname) -> tuple[str, str]:
    """
    Returns (first_name, last_name).

    Mews writes 'Company, Person Name' in Nachname when booked via company.
    In that case Vorname contains 'First Last' for the real person.
    """
    n = _clean(nachname)
    v = _clean(vorname)
    if "," in n and v:
        parts = v.rsplit(" ", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return "", v
    return v, n


def _group_display_name(gruppenname) -> str:
    """Strip Mews suffix '-NN-NN-XXXX' from group/booking name."""
    return re.sub(r"-\d+-\d+-[A-F0-9]{4}$", "", _clean(gruppenname)).strip()


# ── Sheet loading ─────────────────────────────────────────────────────────────

def _load_rows(file_or_path) -> list[dict]:
    """Load 'Reservierungen' sheet and return list of row dicts.
    Skips footer/summary rows (e.g. Mews appends a 'Gesamtbetrag' totals row).
    """
    wb = openpyxl.load_workbook(file_or_path, read_only=True, data_only=True)
    ws = wb["Reservierungen"]
    raw = list(ws.iter_rows(values_only=True))
    if not raw:
        return []
    headers = [str(h) if h is not None else "" for h in raw[0]]
    # Find Anreise column index to filter companion/address sub-rows
    anreise_idx = headers.index("Anreise") if "Anreise" in headers else -1
    rows = []
    for row in raw[1:]:
        # Skip rows where the first cell is not a reservation number (summary/footer rows)
        first = str(row[0]).strip() if row[0] is not None else ""
        if not first.isdigit():
            continue
        # Skip companion/address sub-rows: openpyxl returns real dates as datetime objects.
        # Only keep rows where Anreise is an actual date — skip None and non-date strings.
        if anreise_idx >= 0:
            anreise_val = row[anreise_idx]
            if not isinstance(anreise_val, (date, datetime)):
                continue
        rows.append(dict(zip(headers, row)))
    return rows


# ── Guest extraction ──────────────────────────────────────────────────────────

def _read_guests(rows: list[dict]) -> list[dict]:
    """
    One guest per unique (first_name_lower, last_name_lower, email_lower).
    Skips company bookings. Derives first name from email when missing.
    """
    seen: dict[tuple, bool] = {}
    result = []
    for row in rows:
        first, last = _parse_person_name(row.get("Nachname"), row.get("Vorname"))
        first, last = first.strip(), last.strip()

        # Skip rows that look like company/organisation bookings
        if last and is_company_name(last):
            continue

        email = _clean(row.get("E-Mail"))

        # Try to derive first name from email when it's missing
        name_source = "original" if first else "none"
        if not first and last and email:
            derived = derive_name_from_email(email, last)
            if derived:
                first = derived
                name_source = "derived_from_email"

        key = (first.lower(), last.lower(), email.lower())
        if key in seen:
            continue
        seen[key] = True

        sys: dict = {}
        raw_first = _parse_person_name(row.get("Nachname"), row.get("Vorname"))[0].strip()

        if name_source == "derived_from_email":
            sys["first_name"] = ""          # original: no first name
        elif not first:
            sys["first_name"] = ""          # placeholder "-" auto-set

        if not last:
            sys["last_name"] = ""           # placeholder "-" auto-set

        nat_raw = _clean(row.get("Staatsangehörigkeit des Gastes"))
        nat = _map_nationality(nat_raw)
        if nat:
            sys["nationality"] = nat_raw    # original: German name → mapped to ISO

        g: dict = {
            "first_name":      first or "-",
            "last_name":       last  or "-",
            "_name_source":    name_source,
            "_system_changes": sys,
        }
        if email:
            g["email"] = email
        phone = _clean(row.get("Telefon"))
        if phone:
            g["phone"] = phone
        if nat:
            g["nationality"] = nat
        mews_id = _clean(row.get("Kennung"))
        if mews_id:
            g["_mews_id"] = mews_id
        result.append(g)
    return result


# ── Company / Group extraction ────────────────────────────────────────────────

def _read_companies(rows: list[dict]) -> list[dict]:
    """
    Collect companies from two sources:
    1. 'Firma' column — explicit company bookings
    2. 'Gruppenname' that appears on ≥2 reservations — group bookings
    """
    companies: dict[str, dict] = {}

    # 1. Explicit Firma entries
    for row in rows:
        firma = _clean(row.get("Firma"))
        if firma and firma not in companies:
            companies[firma] = {
                "name":     firma,
                "_mews_id": _clean(row.get("Firma Kennung")) or None,
            }

    # 2. Groups (same Gruppenname on ≥2 rows)
    group_rows: dict[str, list[dict]] = {}
    for row in rows:
        gname = _clean(row.get("Gruppenname"))
        if gname:
            group_rows.setdefault(gname, []).append(row)

    for gname, glist in group_rows.items():
        if len(glist) < 2:
            continue
        display = _group_display_name(gname)
        if display and display not in companies:
            sys: dict = {}
            if display != gname:                # suffix was stripped
                sys["name"] = gname
            companies[display] = {
                "name":            display,
                "_mews_id":        _clean(glist[0].get("Kennung")) or None,
                "_system_changes": sys,
            }

    return [{k: v for k, v in c.items() if v} for c in companies.values()]


# ── Reservation extraction ────────────────────────────────────────────────────

def _read_reservations(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        raw_nachname = _clean(row.get("Nachname"))
        raw_vorname  = _clean(row.get("Vorname"))
        first, last  = _parse_person_name(raw_nachname, raw_vorname)
        first, last  = first.strip(), last.strip()

        sys: dict = {}
        # Name was split out of compound "Company, Person Name" Nachname
        if "," in raw_nachname and raw_vorname:
            sys["first_name"] = raw_nachname
        elif not first:
            sys["first_name"] = ""          # placeholder "-"
        if not last:
            sys["last_name"] = ""           # placeholder "-"

        r: dict = {
            "first_name":      first or "-",
            "last_name":       last  or "-",
            "Check In":        _fmt_date(row.get("Anreise")),
            "Check Out":       _fmt_date(row.get("Abreise")),
            "Zimmer":          _clean(row.get("Raumnummer")),
            "Zimmertyp":       _clean(row.get("Raumkategorie")),
            "_system_changes": sys,
        }
        email = _clean(row.get("E-Mail"))
        if email:
            r["email"] = email
        summe = row.get("Gesamtbetrag")
        if summe is not None and summe != "":
            r["Summe"] = str(summe)
        status = _clean(row.get("Status"))
        if status:
            r["Status"] = status
        mews_id = _clean(row.get("Kennung"))
        if mews_id:
            r["_mews_id"] = mews_id
        result.append({k: v for k, v in r.items() if v})
    return result


# ── Entry point ───────────────────────────────────────────────────────────────

def read_mews(file_or_path, entity_type: str) -> list[dict]:
    """
    Read a Mews Reservierungsbericht XLSX and return rows pre-mapped to
    HotelFriend import format.

    file_or_path: path string, Path, or file-like object (BytesIO)
    entity_type:  "guest" | "company" | "reservation"
    """
    rows = _load_rows(file_or_path)
    if entity_type == "guest":
        return _read_guests(rows)
    if entity_type == "company":
        return _read_companies(rows)
    if entity_type == "reservation":
        return _read_reservations(rows)
    raise ValueError(f"Unbekannter Entitätstyp: {entity_type}")
