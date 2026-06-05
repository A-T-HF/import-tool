"""
HS3 CSV-Reader — liest DBeaver-Exporte statt native Firebird-Verbindung.

Akzeptiert eine ZIP-Datei mit CSV-Exporten der HS3-Datenbanktabellen.
Gibt dieselbe Ausgabe zurück wie hs3_reader.read_hs3().

Mindest-Tabellen je Entitätstyp:
  guest:       BAS_CUSTOMERS
  company:     BAS_CUSTOMERS
  reservation: BAS_CUSTOMERS + MOV_RESERVATIONS + MOV_RESERVATIONS_OCCUPATION

Optionale Tabellen (fehlen → stille Fallbacks):
  MOV_RESERVATIONS             — Namensauflösung Gäste + Reservierungskopf
  MOV_RESERVATIONS_GUESTS      — Namensauflösung Gäste
  MOV_RESERVATIONS_OCCUPATION  — Belegungs-Zeilen für Reservierungen
  BAS_PRODUCTS_OBJECTS         — Zimmernummern
  BAS_PRODUCTS_DESCRIPTIONS    — Zimmertypen
  SYS_LANGUAGES                — ISO-Sprachcodes
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.hs3_reader import (
    _GENDER_MAP,
    _STATUS_MAP,
    _TITLE_MAP,
    _country_from_postcode,
    _split_names,
)


# ---------------------------------------------------------------------------
# Interne Hilfs-Funktionen
# ---------------------------------------------------------------------------

def _s(v) -> str:
    """Pandas-Zellwert → sauberer String; NaN/NULL/None → leer."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s in ("nan", "None", "NULL", "<NA>") else s


def _i(v) -> int | None:
    """String → int; leer/ungültig → None."""
    s = _s(v)
    if not s:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _date(v) -> str:
    """String → ISO-Datum (YYYY-MM-DD); leer/unbekanntes Format → ''."""
    s = _s(v)
    if not s:
        return ""
    for fmt in (
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _amount(v) -> str:
    """String → normalisierter Dezimal-String; leer → ''."""
    import re
    s = _s(v)
    if not s:
        return ""
    cleaned = re.sub(r"[€$£\s]", "", s).replace(",", ".")
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    return cleaned if cleaned else ""


# ---------------------------------------------------------------------------
# ZIP laden
# ---------------------------------------------------------------------------

def _load_zip(zip_path: Path) -> dict[str, pd.DataFrame]:
    """Extrahiert alle CSVs aus dem ZIP; Key = Tabellenname in GROSSBUCHSTABEN."""
    tables: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for entry in zf.namelist():
            if not entry.lower().endswith(".csv"):
                continue
            table_name = Path(entry).stem.upper()
            with zf.open(entry) as f:
                raw = f.read()
            for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    df = pd.read_csv(
                        io.BytesIO(raw),
                        dtype=str,
                        keep_default_na=False,
                        encoding=enc,
                        on_bad_lines="skip",
                    )
                    df.columns = [c.upper().strip() for c in df.columns]
                    tables[table_name] = df
                    break
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
    return tables


def _require(tables: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    if name not in tables:
        raise ValueError(
            f"Tabelle '{name}' fehlt im ZIP. "
            f"Bitte in DBeaver exportieren: Rechtsklick auf Tabelle → Export Data → CSV."
        )
    return tables[name]


def _optional(tables: dict[str, pd.DataFrame], name: str) -> pd.DataFrame | None:
    return tables.get(name)


# ---------------------------------------------------------------------------
# Gäste
# ---------------------------------------------------------------------------

def _read_guests(tables: dict[str, pd.DataFrame]) -> list[dict]:
    from app.guests_importer import is_company_name, resolve_names, derive_name_from_email

    customers = _require(tables, "BAS_CUSTOMERS")
    reservations = _optional(tables, "MOV_RESERVATIONS")
    reg_guests = _optional(tables, "MOV_RESERVATIONS_GUESTS")
    languages_df = _optional(tables, "SYS_LANGUAGES")

    # Sprachkarte aufbauen
    lang_map: dict[int, str] = {}
    if languages_df is not None and "ID" in languages_df.columns and "ISO639" in languages_df.columns:
        for _, row in languages_df.iterrows():
            lid = _i(row.get("ID"))
            iso = _s(row.get("ISO639")).lower()
            if lid is not None and iso:
                lang_map[lid] = iso

    # Basis-Records (Typ 1 = Person, nicht archiviert)
    base: dict[int, dict] = {}
    for _, row in customers.iterrows():
        if _s(row.get("CUSTTYPE")) != "1":
            continue
        archive_val = _s(row.get("ARCHIVE", ""))
        if archive_val not in ("", "0"):
            continue
        cid = _i(row.get("ID"))
        if cid is None or cid <= 0:
            continue
        last = _s(row.get("NAME1"))
        if not last or is_company_name(last):
            continue
        base[cid] = {
            "row": row,
            "candidates": [
                {"first_name": _s(row.get("NAME2")), "last_name": last}
            ],
        }

    # Buchungsinhaber aus MOV_RESERVATIONS
    if reservations is not None:
        for _, row in reservations.iterrows():
            cid = _i(row.get("CUSTID"))
            if cid not in base:
                continue
            last = _s(row.get("NAME1"))
            if last and not is_company_name(last):
                base[cid]["candidates"].append(
                    {"first_name": _s(row.get("NAME2")), "last_name": last}
                )

    # Meldezettel-Gäste aus MOV_RESERVATIONS_GUESTS
    if reg_guests is not None:
        for _, row in reg_guests.iterrows():
            cid = _i(row.get("CUSTID"))
            if cid not in base:
                continue
            last = _s(row.get("LASTNAME"))
            if last and not is_company_name(last):
                base[cid]["candidates"].append(
                    {"first_name": _s(row.get("FIRSTNAME")), "last_name": last}
                )

    # Mapping → HotelFriend-Format
    rows = []
    for cid, g in base.items():
        r = g["row"]
        first_name, last_name = resolve_names(g["candidates"])
        email = _s(r.get("EMAIL"))

        name_source = "original" if (first_name or last_name) else "none"
        if not first_name and last_name and email:
            derived = derive_name_from_email(email, last_name)
            if derived:
                first_name = derived
                name_source = "derived_from_email"
        if not first_name:
            first_name = "-"
            if name_source == "original":
                name_source = "placeholder"

        title_raw = _s(r.get("SALUTATION")).lower()
        title = _TITLE_MAP.get(title_raw, "")
        gender_raw = _i(r.get("GENDER"))
        raw_gender = _GENDER_MAP.get(gender_raw, "")
        gender = raw_gender or {"mr": "1", "mrs": "2", "miss": "2"}.get(title, "")

        raw_country = _s(r.get("COUNTRY"))
        country = _country_from_postcode(raw_country, _s(r.get("ZIPCODE")))

        lang_id = _i(r.get("LANGUAGE"))
        language = lang_map.get(lang_id, "") if lang_id is not None else ""

        sys: dict = {}
        if name_source in ("derived_from_email", "placeholder"):
            sys["first_name"] = ""
        if not raw_gender and gender:
            sys["gender"] = ""
        if country != raw_country:
            sys["country"] = raw_country

        rows.append({
            "_hs3_id": cid,
            "_name_source": name_source,
            "_system_changes": sys,
            "last_name": last_name,
            "first_name": first_name,
            "email": email,
            "phone": _s(r.get("PHONE1")),
            "country": country,
            "city": _s(r.get("CITY")),
            "date_of_birth": _date(r.get("BIRTHDAY")),
            "gender": gender,
            "title": title,
            "nationality": _s(r.get("NATIONALITY")).replace("---", "").strip(),
            "language": language,
        })
    return rows


# ---------------------------------------------------------------------------
# Firmen
# ---------------------------------------------------------------------------

def _read_companies(tables: dict[str, pd.DataFrame]) -> list[dict]:
    customers = _require(tables, "BAS_CUSTOMERS")
    rows = []
    for _, row in customers.iterrows():
        if _s(row.get("CUSTTYPE")) != "2":
            continue
        archive_val = _s(row.get("ARCHIVE", ""))
        if archive_val not in ("", "0"):
            continue
        cid = _i(row.get("ID"))
        if cid is None or cid <= 0:
            continue
        raw_name = _s(row.get("NAME1"))
        name = raw_name or "-"
        raw_country = _s(row.get("COUNTRY"))
        country = _country_from_postcode(raw_country, _s(row.get("ZIPCODE")))
        sys: dict = {}
        if not raw_name:
            sys["name"] = ""
        if country != raw_country:
            sys["country"] = raw_country
        rows.append({
            "_hs3_id": cid,
            "_system_changes": sys,
            "name": name,
            "email": _s(row.get("EMAIL")),
            "phone": _s(row.get("PHONE1")),
            "country": country,
            "city": _s(row.get("CITY")),
            "address": _s(row.get("STREET")),
            "postcode": _s(row.get("ZIPCODE")),
            "iban": _s(row.get("IBAN")),
            "bic": _s(row.get("BIC")),
            "type": "Company",
        })
    return rows


# ---------------------------------------------------------------------------
# Reservierungen
# ---------------------------------------------------------------------------

def _read_reservations(tables: dict[str, pd.DataFrame]) -> list[dict]:
    reservations = _require(tables, "MOV_RESERVATIONS")
    occupation = _require(tables, "MOV_RESERVATIONS_OCCUPATION")
    customers = _optional(tables, "BAS_CUSTOMERS")
    objects_df = _optional(tables, "BAS_PRODUCTS_OBJECTS")
    descriptions_df = _optional(tables, "BAS_PRODUCTS_DESCRIPTIONS")

    # Hilfsmaps aufbauen
    email_map: dict[int, str] = {}
    if customers is not None:
        for _, row in customers.iterrows():
            cid = _i(row.get("ID"))
            email = _s(row.get("EMAIL"))
            if cid and email:
                email_map[cid] = email

    roomno_map: dict[int, str] = {}  # objectid → room_no
    productid_map: dict[int, int] = {}  # objectid → productid
    if objects_df is not None:
        for _, row in objects_df.iterrows():
            oid = _i(row.get("ID"))
            if oid is not None:
                roomno_map[oid] = _s(row.get("OBJECT"))
                pid = _i(row.get("PRODUCTID"))
                if pid is not None:
                    productid_map[oid] = pid

    roomtype_map: dict[int, str] = {}  # productid → description
    if descriptions_df is not None:
        for _, row in descriptions_df.iterrows():
            pid = _i(row.get("PRODUCTID"))
            desc = _s(row.get("DESCRIPTION_L01"))
            if pid is not None and desc:
                roomtype_map[pid] = desc

    # Reservierungskopf-Index
    res_index: dict[int, dict] = {}
    for _, row in reservations.iterrows():
        rid = _i(row.get("ID"))
        if rid is not None:
            res_index[rid] = row

    # Zeilen aus Belegung aufbauen
    rows = []
    for _, occ in occupation.iterrows():
        resid = _i(occ.get("RESID"))
        if resid not in res_index:
            continue

        status_code = _i(occ.get("RESSTATUS"))
        hf_status = _STATUS_MAP.get(status_code)
        if hf_status is None:
            continue  # geblockt / Aufbau-/Abbauzeit

        res = res_index[resid]
        raw_last, raw_first = _split_names(_s(res.get("NAME1")), _s(res.get("NAME2")))
        last_name = raw_last or "-"
        first_name = raw_first or "-"

        sys: dict = {}
        if not raw_first:
            sys["first_name"] = ""
        if not raw_last:
            sys["last_name"] = ""

        cid = _i(res.get("CUSTID"))
        email = email_map.get(cid, "") if cid else ""

        object_id = _i(occ.get("OBJECTID"))
        room_no = roomno_map.get(object_id, "") if object_id else ""
        product_id = productid_map.get(object_id) if object_id else None
        room_type = roomtype_map.get(product_id, str(product_id) if product_id else "") if product_id else ""

        rows.append({
            "_hs3_id": resid,
            "_system_changes": sys,
            "last_name": last_name,
            "first_name": first_name,
            "email": email,
            "Check In": _date(occ.get("DATE_FROM")),
            "Check Out": _date(occ.get("DATE_TO")),
            "Zimmer": room_no,
            "Zimmertyp": room_type,
            "Summe": _amount(res.get("TOTAL_GROSS_LC")),
            "Status": hf_status,
        })
    return rows


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def read_hs3_csv(zip_path: str | Path, entity_type: str) -> list[dict]:
    """
    Liest HS3-Daten aus einer ZIP-Datei mit DBeaver-CSV-Exporten.

    entity_type: "guest" | "company" | "reservation"
    Gibt dieselbe Struktur zurück wie hs3_reader.read_hs3().
    """
    zip_path = Path(zip_path)
    tables = _load_zip(zip_path)

    if entity_type == "guest":
        rows = _read_guests(tables)
    elif entity_type == "company":
        rows = _read_companies(tables)
    elif entity_type == "reservation":
        rows = _read_reservations(tables)
    else:
        raise ValueError(f"Unbekannter Entitätstyp: {entity_type}")

    # Leere Strings entfernen (gleiche Normalisierung wie hs3_reader)
    return [{k: v for k, v in row.items() if v != ""} for row in rows]


def is_hs3_csv_zip(zip_path: str | Path) -> bool:
    """Prüft ob ein ZIP HS3-Tabellen enthält (heuristisch: BAS_CUSTOMERS.csv vorhanden)."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names_upper = [Path(n).stem.upper() for n in zf.namelist()]
            return "BAS_CUSTOMERS" in names_upper
    except Exception:
        return False
