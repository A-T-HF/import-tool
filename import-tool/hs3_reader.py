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
import subprocess
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

    result = subprocess.run(
        [str(gbak), "-c", "-user", "sysdba", "-password", "masterkey",
         str(bak_path), str(fdb_path)],
        env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gbak Fehler: {result.stderr or result.stdout}")


def _connect(fdb_path: Path):
    _load_firebird()
    from firebird.driver import connect
    return connect(str(fdb_path), user="sysdba", password="masterkey", charset="WIN1252")


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


def _fmt_decimal(v) -> str:
    if v is None:
        return ""
    return str(v.quantize(Decimal("0.01"))) if isinstance(v, Decimal) else str(v)


# ── Public reader functions ────────────────────────────────────────────────

def _build_language_map(con) -> dict[int, str]:
    """Build {hs3_language_id: iso639_code} from SYS_LANGUAGES."""
    cur = con.cursor()
    cur.execute("SELECT ID, ISO639 FROM SYS_LANGUAGES WHERE ISO639 IS NOT NULL AND ISO639 <> ''")
    return {r[0]: r[1].strip().lower() for r in cur.fetchall()}


def read_guests(con) -> list[dict]:
    """Return BAS_CUSTOMERS persons (CUSTTYPE=1) mapped to HotelFriend guest fields."""
    lang_map = _build_language_map(con)
    cur = con.cursor()
    cur.execute("""
        SELECT ID, SALUTATION, NAME1, NAME2, EMAIL, PHONE1,
               COUNTRY, CITY, STREET, ZIPCODE,
               BIRTHDAY, GENDER, NATIONALITY, LANGUAGE
        FROM BAS_CUSTOMERS
        WHERE ID > 0
    """)
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        # Skip entries without a real name
        if not r.get("NAME1"):
            continue
        title_raw = (r.get("SALUTATION") or "").strip().lower()
        # Detect if this is a company entry by salutation
        if title_raw in ("firma", "company"):
            continue
        rows.append({
            "last_name":    (r.get("NAME1") or "").strip(),
            "first_name":   (r.get("NAME2") or "").strip(),
            "email":        (r.get("EMAIL") or "").strip(),
            "phone":        (r.get("PHONE1") or "").strip(),
            "country":      (r.get("COUNTRY") or "").strip(),
            "city":         (r.get("CITY") or "").strip(),
            "date_of_birth": _fmt_date(r.get("BIRTHDAY")),
            "gender":       _GENDER_MAP.get(r.get("GENDER"), ""),
            "title":        _TITLE_MAP.get(title_raw, ""),
            "nationality":  (r.get("NATIONALITY") or "").replace("---", "").strip(),
            "language":     lang_map.get(r.get("LANGUAGE"), ""),
        })
    return rows


def read_companies(con) -> list[dict]:
    """Return BAS_CUSTOMERS companies (CUSTTYPE=2) mapped to HotelFriend company fields."""
    cur = con.cursor()
    cur.execute("""
        SELECT ID, NAME1, EMAIL, PHONE1, COUNTRY, CITY, STREET, ZIPCODE, IBAN, BIC
        FROM BAS_CUSTOMERS
        WHERE ID > 0 AND CUSTTYPE = 2
    """)
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        if not r.get("NAME1"):
            continue
        rows.append({
            "name":     (r.get("NAME1") or "").strip(),
            "email":    (r.get("EMAIL") or "").strip(),
            "phone":    (r.get("PHONE1") or "").strip(),
            "country":  (r.get("COUNTRY") or "").strip(),
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

        name1 = (r.get("NAME1") or "").strip()
        # Split "Lastname Firstname" pattern if NAME2 is empty
        name2 = (r.get("NAME2") or "").strip()

        product_id = r.get("PRODUCTID")
        room_type = roomtype_map.get(product_id, str(product_id) if product_id else "")

        rows.append({
            "last_name":  name1,
            "first_name": name2,
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
                return read_guests(con)
            elif entity_type == "company":
                return read_companies(con)
            elif entity_type == "reservation":
                return read_reservations(con)
            else:
                raise ValueError(f"Unbekannter Entitätstyp: {entity_type}")
        finally:
            con.close()

    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
