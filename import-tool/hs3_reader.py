"""
HS3 Firebird Database Reader
Reads guests, companies, and reservations from HS3 .hsb backup files
and returns them pre-mapped to HotelFriend import format.

Requires: Firebird 5 arm64 embedded at HS3_FIREBIRD_HOME env var
          (defaults to /tmp/fb5_arm64/Firebird.pkg/Versions/A/Resources)
"""

import os
import ctypes
import zipfile
import subprocess  # nosec B404
import tempfile
import shutil
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal

_HERE = Path(__file__).parent
HS3_FIREBIRD_HOME = os.environ.get(
    "HS3_FIREBIRD_HOME",
    str(_HERE / "firebird"),
)

_fb_loaded = False


def _load_firebird():
    global _fb_loaded
    if _fb_loaded:
        return
    lib_dir = Path(HS3_FIREBIRD_HOME) / "lib"
    if not lib_dir.exists():
        raise RuntimeError(
            f"Firebird nicht gefunden unter {HS3_FIREBIRD_HOME}. "
            "Bitte HS3_FIREBIRD_HOME setzen."
        )
    for dep in [
        "libtommath.dylib", "libtomcrypt.dylib",
        "libicudata.71.dylib", "libicuuc.71.dylib", "libicui18n.71.dylib",
        "libfbclient.dylib",
    ]:
        path = lib_dir / dep
        if path.exists():
            ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)

    os.environ["FIREBIRD"] = HS3_FIREBIRD_HOME
    lock_dir = Path(tempfile.gettempdir()) / "hs3_fb_lock"
    lock_dir.mkdir(exist_ok=True)
    os.environ.setdefault("FIREBIRD_LOCK", str(lock_dir))

    from firebird.driver import driver_config
    driver_config.fb_client_library.value = str(lib_dir / "libfbclient.dylib")
    _fb_loaded = True


def _extract_bak_from_hsb(hsb_path: Path, tmp_dir: Path) -> Path:
    """Extract the .bak file from a .hsb ZIP archive. Returns path to .bak."""
    with zipfile.ZipFile(hsb_path) as zf:
        bak_entries = [e for e in zf.namelist() if e.endswith(".bak")]
        if not bak_entries:
            raise ValueError("Keine .bak-Datei im HSB-Archiv gefunden.")
        # Use the largest .bak (= main database, not demo data)
        bak_entry = max(bak_entries, key=lambda e: zf.getinfo(e).file_size)
        bak_path = tmp_dir / "database.bak"
        with zf.open(bak_entry) as src, open(bak_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return bak_path


def _restore_bak(bak_path: Path, fdb_path: Path):
    """Restore a Firebird .bak backup to a new .fdb using gbak."""
    gbak = Path(HS3_FIREBIRD_HOME) / "bin" / "gbak"
    if not gbak.exists():
        raise RuntimeError(f"gbak nicht gefunden: {gbak}")

    env = os.environ.copy()
    env["DYLD_LIBRARY_PATH"] = str(Path(HS3_FIREBIRD_HOME) / "lib")
    env["FIREBIRD"] = HS3_FIREBIRD_HOME

    result = subprocess.run(  # nosec B603
        [str(gbak), "-c", "-user", "sysdba", "-password", "masterkey",
         str(bak_path), str(fdb_path)],
        env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gbak Fehler: {result.stderr or result.stdout}")


def _connect(fdb_path: Path):
    _load_firebird()
    from firebird.driver import connect
    return connect(str(fdb_path), user="sysdba", password="masterkey", charset="WIN1252")  # nosec B106


# ── Status mapping ──────────────────────────────────────────────────────────

# HS3 RESSTATUS → HotelFriend status code
_STATUS_MAP = {
    0: "booking_offer",    # Angebot
    1: "booking_offer",    # Option
    2: "booking_offer",    # Option überfällig
    3: "confirmed",        # Definitiv
    4: "confirmed",        # Garantiert
    8: "check_out",        # Abgerechnet
    9: "check_out",        # Ausgecheckt
    10: "check_in",        # Eingecheckt (Abgerechnet)
    # 5/6 = Aufbau-/Abbauzeit (setup/teardown) → skip
    # 7   = Gesperrt (blocked) → skip
}

# HS3 GENDER (BAS_CUSTOMERS) → HotelFriend gender code
# HS3: 1=weiblich, 2=männlich  ↔  HF: 1=männlich, 2=weiblich
_GENDER_MAP = {1: "2", 2: "1"}

# HS3 SALUTATION → HotelFriend title
_TITLE_MAP = {
    "herr": "mr",
    "frau": "mrs",
    "mr": "mr",
    "mrs": "mrs",
    "ms": "mrs",
    "miss": "miss",
}


def _fmt_date(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return str(v)


def _country_from_postcode(country: str, postcode: str) -> str:
    """Infer DE if country is empty but postcode is exactly 5 digits."""
    if not country and postcode and postcode.strip().isdigit() and len(postcode.strip()) == 5:
        return "DE"
    return country


def _fmt_decimal(v) -> str:
    if v is None:
        return ""
    return str(v.quantize(Decimal("0.01"))) if isinstance(v, Decimal) else str(v)


def _split_names(name1: str, name2: str) -> tuple[str, str]:
    """
    Return (last_name, first_name).
    If name2 is empty but name1 contains a space, split on the last space:
      "Max Müller" → first="Max", last="Müller"
    If name2 is empty and name1 has no space, first_name stays empty
    (row will fail required-field validation and surface as an error).
    """
    last = name1.strip()
    first = name2.strip()
    if not first and " " in last:
        idx = last.rfind(" ")
        first = last[:idx].strip()
        last = last[idx + 1:].strip()
    return last, first


# ── Public reader functions ────────────────────────────────────────────────

def _build_language_map(con) -> dict[int, str]:
    """Build {hs3_language_id: iso639_code} from SYS_LANGUAGES."""
    cur = con.cursor()
    cur.execute("SELECT ID, ISO639 FROM SYS_LANGUAGES WHERE ISO639 IS NOT NULL AND ISO639 <> ''")
    return {r[0]: r[1].strip().lower() for r in cur.fetchall()}


def read_guests(con) -> list[dict]:
    """
    Return persons from BAS_CUSTOMERS (CUSTTYPE=1, not archived) mapped to
    HotelFriend guest fields.

    Names are resolved from three sources per CUSTID and enriched via email
    pattern matching — see guests_importer for the full resolution logic.
    """
    from guests_importer import is_company_name, resolve_names, derive_name_from_email

    lang_map = _build_language_map(con)
    cur = con.cursor()

    # ── 1. Base records ────────────────────────────────────────────────────
    cur.execute("""
        SELECT ID, SALUTATION, NAME1, NAME2, EMAIL, PHONE1,
               COUNTRY, CITY, ZIPCODE, BIRTHDAY, GENDER, NATIONALITY, LANGUAGE
        FROM BAS_CUSTOMERS
        WHERE ID > 0
          AND CUSTTYPE = 1
          AND COALESCE(ARCHIVE, 0) = 0
    """)
    cols = [d[0] for d in cur.description]
    base: dict[int, dict] = {}
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        last = (r.get("NAME1") or "").strip()
        if not last or is_company_name(last):
            continue
        custid = r["ID"]
        base[custid] = {
            "r":          r,
            "candidates": [{"first_name": (r.get("NAME2") or "").strip(),
                            "last_name":  last}],
        }

    # ── 2. Booking-holder names from MOV_RESERVATIONS ─────────────────────
    cur.execute("SELECT CUSTID, NAME1, NAME2 FROM MOV_RESERVATIONS WHERE CUSTID > 0")
    for custid, name1, name2 in cur.fetchall():
        if custid not in base:
            continue
        last = (name1 or "").strip()
        if last and not is_company_name(last):
            base[custid]["candidates"].append(
                {"first_name": (name2 or "").strip(), "last_name": last}
            )

    # ── 3. Registration-form guests from MOV_RESERVATIONS_GUESTS ──────────
    cur.execute(
        "SELECT CUSTID, LASTNAME, FIRSTNAME FROM MOV_RESERVATIONS_GUESTS WHERE CUSTID > 0"
    )
    for custid, lastname, firstname in cur.fetchall():
        if custid not in base:
            continue
        last = (lastname or "").strip()
        if last and not is_company_name(last):
            base[custid]["candidates"].append(
                {"first_name": (firstname or "").strip(), "last_name": last}
            )

    # ── 4. Resolve + build HotelFriend rows ───────────────────────────────
    rows = []
    for custid, g in base.items():
        r = g["r"]
        first_name, last_name = resolve_names(g["candidates"])
        email = (r.get("EMAIL") or "").strip()

        name_source = "original" if (first_name or last_name) else "none"
        if not first_name and last_name and email:
            derived = derive_name_from_email(email, last_name)
            if derived:
                first_name  = derived
                name_source = "derived_from_email"
        if not first_name:
            first_name  = "-"
            if name_source == "original":
                name_source = "placeholder"

        title_raw = (r.get("SALUTATION") or "").strip().lower()
        title  = _TITLE_MAP.get(title_raw, "")
        raw_gender = _GENDER_MAP.get(r.get("GENDER"), "")
        gender = raw_gender or {"mr": "1", "mrs": "2", "miss": "2"}.get(title, "")

        raw_country = (r.get("COUNTRY") or "").strip()
        country = _country_from_postcode(raw_country, (r.get("ZIPCODE") or "").strip())

        sys = {}
        if name_source in ("derived_from_email", "placeholder"):
            sys["first_name"] = ""
        if not raw_gender and gender:
            sys["gender"] = ""
        if country != raw_country:
            sys["country"] = raw_country

        rows.append({
            "_hs3_id":        custid,
            "_name_source":   name_source,
            "_system_changes": sys,
            "last_name":      last_name,
            "first_name":     first_name,
            "email":          email,
            "phone":          (r.get("PHONE1") or "").strip(),
            "country":        country,
            "city":           (r.get("CITY") or "").strip(),
            "date_of_birth":  _fmt_date(r.get("BIRTHDAY")),
            "gender":         gender,
            "title":          title,
            "nationality":    (r.get("NATIONALITY") or "").replace("---", "").strip(),
            "language":       lang_map.get(r.get("LANGUAGE"), ""),
        })
    return rows


def read_companies(con) -> list[dict]:
    """Return BAS_CUSTOMERS companies (CUSTTYPE=2, not archived) mapped to HotelFriend company fields."""
    cur = con.cursor()
    cur.execute("""
        SELECT ID, NAME1, EMAIL, PHONE1, COUNTRY, CITY, STREET, ZIPCODE, IBAN, BIC
        FROM BAS_CUSTOMERS
        WHERE ID > 0
          AND CUSTTYPE = 2
          AND COALESCE(ARCHIVE, 0) = 0
    """)
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        raw_name    = (r.get("NAME1") or "").strip()
        name        = raw_name or "-"
        raw_country = (r.get("COUNTRY") or "").strip()
        country     = _country_from_postcode(raw_country, (r.get("ZIPCODE") or "").strip())
        sys = {}
        if not raw_name:
            sys["name"] = ""
        if country != raw_country:
            sys["country"] = raw_country
        rows.append({
            "_hs3_id":         r.get("ID"),
            "_system_changes": sys,
            "name":            name,
            "email":           (r.get("EMAIL") or "").strip(),
            "phone":           (r.get("PHONE1") or "").strip(),
            "country":         country,
            "city":     (r.get("CITY") or "").strip(),
            "address":  (r.get("STREET") or "").strip(),
            "postcode": (r.get("ZIPCODE") or "").strip(),
            "iban":     (r.get("IBAN") or "").strip(),
            "bic":      (r.get("BIC") or "").strip(),
            "type":     "Company",
        })
    return rows


def _build_roomtype_map(con) -> dict[int, str]:
    """Build {productid: room_type_name} from BAS_PRODUCTS_DESCRIPTIONS."""
    cur = con.cursor()
    cur.execute("SELECT PRODUCTID, DESCRIPTION_L01 FROM BAS_PRODUCTS_DESCRIPTIONS WHERE DESCRIPTION_L01 IS NOT NULL")
    return {r[0]: r[1].strip() for r in cur.fetchall()}


def read_reservations(con) -> list[dict]:
    """
    Return reservations mapped to HotelFriend reservation fields.
    One row per room-per-reservation (multi-room bookings become multiple rows).
    Skips blocked rooms and setup/teardown slots.
    """
    roomtype_map = _build_roomtype_map(con)

    cur = con.cursor()
    cur.execute("""
        SELECT
            r.ID, r.NAME1, r.NAME2, r.TOTAL_GROSS_LC, r.CUSTID,
            occ.DATE_FROM, occ.DATE_TO, occ.RESSTATUS,
            obj.OBJECT as ROOM_NO, obj.PRODUCTID,
            c.EMAIL
        FROM MOV_RESERVATIONS r
        JOIN MOV_RESERVATIONS_OCCUPATION occ ON occ.RESID = r.ID
        LEFT JOIN BAS_PRODUCTS_OBJECTS obj ON obj.ID = occ.OBJECTID
        LEFT JOIN BAS_CUSTOMERS c ON c.ID = r.CUSTID
        WHERE r.ID > 0 AND occ.ID > 0
        ORDER BY r.ID, occ.ID
    """)
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        status_code = _STATUS_MAP.get(r.get("RESSTATUS"))
        if status_code is None:
            continue  # skip blocked/setup slots

        raw_last, raw_first = _split_names(r.get("NAME1") or "", r.get("NAME2") or "")
        last_name  = raw_last  or "-"
        first_name = raw_first or "-"
        sys = {}
        if not raw_first:
            sys["first_name"] = ""
        if not raw_last:
            sys["last_name"] = ""
        product_id = r.get("PRODUCTID")
        room_type = roomtype_map.get(product_id, str(product_id) if product_id else "")

        rows.append({
            "_hs3_id":         r.get("ID"),
            "_system_changes": sys,
            "last_name":       last_name,
            "first_name":      first_name,
            "email":      (r.get("EMAIL") or "").strip(),
            "Check In":   _fmt_date(r.get("DATE_FROM")),
            "Check Out":  _fmt_date(r.get("DATE_TO")),
            "Zimmer":     (r.get("ROOM_NO") or "").strip(),
            "Zimmertyp":  room_type,
            "Summe":      _fmt_decimal(r.get("TOTAL_GROSS_LC")),
            "Status":     status_code,
        })
    return rows


# ── Main entry point ───────────────────────────────────────────────────────

def read_hs3(file_path: str | Path, entity_type: str) -> list[dict]:
    """
    Read an HS3 .hsb or .fdb file and return rows pre-mapped to HotelFriend format.

    entity_type: "guest" | "company" | "reservation"
    """
    file_path = Path(file_path)
    tmp_dir = None

    try:
        if file_path.suffix.lower() == ".hsb":
            tmp_dir = Path(tempfile.mkdtemp(prefix="hs3_"))
            bak_path = _extract_bak_from_hsb(file_path, tmp_dir)
            fdb_path = tmp_dir / "database.fdb"
            _restore_bak(bak_path, fdb_path)
        elif file_path.suffix.lower() in (".fdb", ".gdb"):
            fdb_path = file_path
        else:
            raise ValueError(f"Unbekanntes Dateiformat: {file_path.suffix}")

        con = _connect(fdb_path)
        try:
            if entity_type == "guest":
                rows = read_guests(con)
            elif entity_type == "company":
                rows = read_companies(con)
            elif entity_type == "reservation":
                rows = read_reservations(con)
            else:
                raise ValueError(f"Unbekannter Entitätstyp: {entity_type}")
            # Strip empty strings so HotelFriend doesn't try to validate blank optional fields
            return [{k: v for k, v in row.items() if v != ""} for row in rows]
        finally:
            con.close()

    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
