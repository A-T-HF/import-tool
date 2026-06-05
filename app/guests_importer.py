"""
HS3 → SQLite Guest Importer

Reads guests from an HS3 Firebird database (.hsb or .fdb), resolves names
from three sources (BAS_CUSTOMERS, MOV_RESERVATIONS, MOV_RESERVATIONS_GUESTS),
and writes the merged result to a local SQLite database.

Usage:
    python guests_importer.py <file.hsb|file.fdb> [output.sqlite]
"""

import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from app.hs3_reader import _connect, _extract_bak_from_hsb, _restore_bak

# ── Company heuristics ──────────────────────────────────────────────────────

_COMPANY_SUFFIXES = (" AG", " GmbH", " KG", " OHG", " UG", " SE", " mbH", " gGmbH")
_COMPANY_EXACT    = {"AG", "GmbH", "KG", "OHG", "UG", "SE", "mbH", "gGmbH"}


def is_company_name(name: str) -> bool:
    """True when the name looks like a legal entity rather than a person."""
    for suffix in _COMPANY_SUFFIXES:
        if name.endswith(suffix):
            return True
    return name.strip() in _COMPANY_EXACT


# ── Name resolution ─────────────────────────────────────────────────────────

_GENERIC_MAILBOXES = {
    "info", "kontakt", "office", "mail",
    "hotel", "buchung", "reservierung",
}

_UMLAUT_TABLE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

def _ascii_fold(s: str) -> str:
    """Lowercase + fold German umlauts so 'Müller' matches 'mueller'."""
    return s.lower().translate(_UMLAUT_TABLE)


def _clean(v) -> str:
    return (v or "").strip()


def resolve_names(candidates: list[dict]) -> tuple[str, str]:
    """
    Pick the most complete (first_name, last_name) from a list of candidates.
    Each candidate: {"first_name": str, "last_name": str}

    Preference:
    1. Candidates where both fields are present (score 2) over partial (score 1)
    2. Among equal score: longer combined length wins
    """
    best_first, best_last, best_score = "", "", -1
    for c in candidates:
        f = _clean(c.get("first_name"))
        l = _clean(c.get("last_name"))
        score = (1 if f else 0) + (1 if l else 0)
        if score > best_score or (
            score == best_score and len(f) + len(l) > len(best_first) + len(best_last)
        ):
            best_first, best_last, best_score = f, l, score
    return best_first, best_last


def derive_name_from_email(email: str, last_name: str) -> str | None:
    """
    Try to extract first_name from the email local part when last_name is known.

    Supported patterns (case-insensitive):
      vorname.nachname@... → "Vorname"   (if nachname matches last_name)
      v.nachname@...       → "V."        (if nachname matches last_name)

    Generic mailboxes (info@, hotel@, …) are ignored.
    Returns None when no pattern matches.
    """
    if not email or not last_name:
        return None
    local = _ascii_fold(email.split("@")[0])
    if local in _GENERIC_MAILBOXES:
        return None

    last_folded = _ascii_fold(last_name)

    # "vorname.nachname" — first part two or more letters
    m = re.match(r"^([a-z][a-z-]+)\.([a-z][a-z-]*)$", local)
    if m and m.group(2) == last_folded:
        return m.group(1).capitalize()

    # "v.nachname" — first part is a single letter
    m2 = re.match(r"^([a-z])\.([a-z][a-z-]*)$", local)
    if m2 and m2.group(2) == last_folded:
        return f"{m2.group(1).upper()}."

    return None


def compute_display_name(
    custid: int,
    first_name: str | None,
    last_name: str | None,
    email: str | None,
) -> str:
    """
    Fallback chain:
      "Hans Müller"  — first + last
      "H. Müller"    — initial-only first (e.g. derived) + last  [covered by same branch]
      "Müller"       — last only
      email          — no name at all
      "Gast #N"      — nothing available
    """
    f = (first_name or "").strip()
    l = (last_name or "").strip()
    if f and l:
        return f"{f} {l}"
    if l:
        return l
    if f:
        return f
    if email:
        return email
    return f"Gast #{custid}"


# ── Data loading ─────────────────────────────────────────────────────────────

def _load_from_firebird(con) -> list[dict]:
    """
    Read all three sources from the open Firebird connection and return
    a list of guest dicts ready for write_to_sqlite().
    """
    guests: dict[int, dict] = {}

    cur = con.cursor()

    # 1. BAS_CUSTOMERS — base records (CUSTTYPE=1, not archived)
    cur.execute("""
        SELECT ID, NAME1, NAME2, EMAIL, SALUTATION
        FROM BAS_CUSTOMERS
        WHERE CUSTTYPE = 1
          AND COALESCE(ARCHIVE, 0) = 0
          AND ID > 0
    """)
    for custid, name1, name2, email, salutation in cur.fetchall():
        last  = _clean(name1)
        first = _clean(name2)
        if not last or is_company_name(last):
            continue
        guests[custid] = {
            "custid":     custid,
            "email":      _clean(email) or None,
            "salutation": _clean(salutation) or None,
            "candidates": [{"first_name": first, "last_name": last}],
        }

    # 2. MOV_RESERVATIONS — booking holder names (NAME1=last, NAME2=first)
    cur.execute("SELECT CUSTID, NAME1, NAME2 FROM MOV_RESERVATIONS WHERE CUSTID > 0")
    for custid, name1, name2 in cur.fetchall():
        if custid not in guests:
            continue
        last  = _clean(name1)
        first = _clean(name2)
        if last and not is_company_name(last):
            guests[custid]["candidates"].append({"first_name": first, "last_name": last})

    # 3. MOV_RESERVATIONS_GUESTS — additional guests on registration form
    cur.execute(
        "SELECT CUSTID, LASTNAME, FIRSTNAME FROM MOV_RESERVATIONS_GUESTS WHERE CUSTID > 0"
    )
    for custid, lastname, firstname in cur.fetchall():
        if custid not in guests:
            continue
        last  = _clean(lastname)
        first = _clean(firstname)
        if last and not is_company_name(last):
            guests[custid]["candidates"].append({"first_name": first, "last_name": last})

    return _resolve_all(guests)


def _resolve_all(guests: dict[int, dict]) -> list[dict]:
    rows = []
    for custid, g in guests.items():
        first_name, last_name = resolve_names(g["candidates"])
        email      = g.get("email")
        name_source = "original" if (first_name or last_name) else "none"

        if not first_name and last_name and email:
            derived = derive_name_from_email(email, last_name)
            if derived:
                first_name  = derived
                name_source = "derived_from_email"

        rows.append({
            "custid":       custid,
            "first_name":   first_name or None,
            "last_name":    last_name  or None,
            "email":        email,
            "salutation":   g.get("salutation"),
            "name_source":  name_source,
            "display_name": compute_display_name(custid, first_name, last_name, email),
        })
    return rows


# ── SQLite persistence ───────────────────────────────────────────────────────

_SCHEMA = Path(__file__).with_name("guests_schema.sql").read_text()

_INSERT = """
    INSERT OR REPLACE INTO guests
        (custid, first_name, last_name, email, salutation, name_source, display_name)
    VALUES
        (:custid, :first_name, :last_name, :email, :salutation, :name_source, :display_name)
"""


def write_to_sqlite(rows: list[dict], db_path: str | Path) -> int:
    """Write guest rows to SQLite. Returns number of rows written."""
    con = sqlite3.connect(db_path)
    con.executescript(_SCHEMA)
    con.executemany(_INSERT, rows)
    con.commit()
    con.close()
    return len(rows)


# ── Entry point ──────────────────────────────────────────────────────────────

def import_hs3_guests(hs3_path: str | Path, db_path: str | Path) -> int:
    """Read guests from hs3_path, write to db_path. Returns row count."""
    hs3_path = Path(hs3_path)
    tmp_dir  = None
    try:
        if hs3_path.suffix.lower() == ".hsb":
            tmp_dir  = Path(tempfile.mkdtemp(prefix="hs3_guests_"))
            bak_path = _extract_bak_from_hsb(hs3_path, tmp_dir)
            fdb_path = tmp_dir / "database.fdb"
            _restore_bak(bak_path, fdb_path)
        elif hs3_path.suffix.lower() in (".fdb", ".gdb"):
            fdb_path = hs3_path
        else:
            raise ValueError(f"Unbekanntes Dateiformat: {hs3_path.suffix}")

        con = _connect(fdb_path)
        try:
            rows = _load_from_firebird(con)
        finally:
            con.close()

        return write_to_sqlite(rows, db_path)
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python guests_importer.py <file.hsb|fdb> [output.sqlite]")
        sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else "guests.sqlite"
    n = import_hs3_guests(src, dst)
    print(f"{n} Gäste importiert → {dst}")
