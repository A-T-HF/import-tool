"""Tests für hs3_csv_reader — liest DBeaver-CSV-Exporte als ZIP."""
import io
import zipfile

import pandas as pd
import pytest


def _make_zip(tables: dict[str, str]) -> bytes:
    """Erstellt ein ZIP-Bytes-Objekt mit den gegebenen CSV-Strings."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in tables.items():
            zf.writestr(f"{name}.csv", content.encode("utf-8"))
    return buf.getvalue()


def _write_zip(tmp_path, tables: dict[str, str]):
    p = tmp_path / "export.zip"
    p.write_bytes(_make_zip(tables))
    return p


# ---------------------------------------------------------------------------
# is_hs3_csv_zip
# ---------------------------------------------------------------------------

def test_is_hs3_csv_zip_positive(tmp_path):
    from hs3_csv_reader import is_hs3_csv_zip
    z = _write_zip(tmp_path, {"BAS_CUSTOMERS": "ID,NAME1\n1,Müller"})
    assert is_hs3_csv_zip(z) is True


def test_is_hs3_csv_zip_negative(tmp_path):
    from hs3_csv_reader import is_hs3_csv_zip
    z = _write_zip(tmp_path, {"OTHER_TABLE": "ID,NAME1\n1,Müller"})
    assert is_hs3_csv_zip(z) is False


def test_is_hs3_csv_zip_invalid_file(tmp_path):
    from hs3_csv_reader import is_hs3_csv_zip
    p = tmp_path / "notazip.zip"
    p.write_bytes(b"not a zip")
    assert is_hs3_csv_zip(p) is False


# ---------------------------------------------------------------------------
# Firmen
# ---------------------------------------------------------------------------

COMPANIES_CSV = """ID,CUSTTYPE,ARCHIVE,NAME1,EMAIL,PHONE1,COUNTRY,CITY,STREET,ZIPCODE,IBAN,BIC
10,2,,Musterhotel GmbH,hotel@example.com,+49123,DE,Berlin,Hauptstr. 1,10115,DE1234,BEXDE
11,2,,Reisebüro AG,reise@example.com,,AT,Wien,,,,
12,1,,Privatperson,,,,,,,,
"""


def test_read_companies(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {"BAS_CUSTOMERS": COMPANIES_CSV})
    rows = read_hs3_csv(z, "company")
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert "Musterhotel GmbH" in names
    assert "Reisebüro AG" in names


def test_read_companies_skips_persons(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {"BAS_CUSTOMERS": COMPANIES_CSV})
    rows = read_hs3_csv(z, "company")
    assert all(r.get("type") == "Company" for r in rows)
    # Person (CUSTTYPE=1) darf nicht enthalten sein
    assert not any("Privatperson" in str(r) for r in rows)


def test_read_companies_archived_excluded(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    csv = "ID,CUSTTYPE,ARCHIVE,NAME1\n10,2,1,Archiviert\n11,2,,Aktiv\n"
    z = _write_zip(tmp_path, {"BAS_CUSTOMERS": csv})
    rows = read_hs3_csv(z, "company")
    assert len(rows) == 1
    assert rows[0]["name"] == "Aktiv"


def test_read_companies_missing_table_raises(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {"OTHER": "ID\n1"})
    with pytest.raises(ValueError, match="BAS_CUSTOMERS"):
        read_hs3_csv(z, "company")


# ---------------------------------------------------------------------------
# Gäste
# ---------------------------------------------------------------------------

CUSTOMERS_CSV = """ID,CUSTTYPE,ARCHIVE,SALUTATION,NAME1,NAME2,EMAIL,PHONE1,COUNTRY,CITY,ZIPCODE,BIRTHDAY,GENDER,NATIONALITY,LANGUAGE
1,1,,Herr,Müller,Max,max@example.com,+49123,DE,München,80331,1985-03-12,2,,
2,1,,Frau,Schmidt,Anna,anna@example.com,,DE,Berlin,10115,,,1,
3,2,,,Firma GmbH,,,,,,,,,,
4,1,1,,Archiviert,,,,,,,,,,
"""


def test_read_guests_basic(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {"BAS_CUSTOMERS": CUSTOMERS_CSV})
    rows = read_hs3_csv(z, "guest")
    # Firma und Archivierter werden übersprungen
    assert len(rows) == 2
    last_names = {r["last_name"] for r in rows}
    assert "Müller" in last_names
    assert "Schmidt" in last_names


def test_read_guests_gender_mapping(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {"BAS_CUSTOMERS": CUSTOMERS_CSV})
    rows = read_hs3_csv(z, "guest")
    mueller = next(r for r in rows if r["last_name"] == "Müller")
    # HS3 GENDER 2=männlich → HF gender "1"
    assert mueller.get("gender") == "1"


def test_read_guests_date_of_birth(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {"BAS_CUSTOMERS": CUSTOMERS_CSV})
    rows = read_hs3_csv(z, "guest")
    mueller = next(r for r in rows if r["last_name"] == "Müller")
    assert mueller.get("date_of_birth") == "1985-03-12"


# ---------------------------------------------------------------------------
# Reservierungen
# ---------------------------------------------------------------------------

RESERVATIONS_CSV = """ID,NAME1,NAME2,TOTAL_GROSS_LC,CUSTID
100,Weber,Klaus,250.00,1
101,Huber,Petra,180.50,2
"""

OCCUPATION_CSV = """ID,RESID,DATE_FROM,DATE_TO,RESSTATUS,OBJECTID
200,100,2024-06-01,2024-06-03,3,10
201,101,2024-07-10,2024-07-12,9,11
202,100,2024-06-01,2024-06-03,7,12
"""

OBJECTS_CSV = """ID,OBJECT,PRODUCTID
10,101,50
11,202,51
12,303,52
"""

DESCRIPTIONS_CSV = """PRODUCTID,DESCRIPTION_L01
50,Einzelzimmer
51,Doppelzimmer
"""


def test_read_reservations_basic(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {
        "BAS_CUSTOMERS": CUSTOMERS_CSV,
        "MOV_RESERVATIONS": RESERVATIONS_CSV,
        "MOV_RESERVATIONS_OCCUPATION": OCCUPATION_CSV,
        "BAS_PRODUCTS_OBJECTS": OBJECTS_CSV,
        "BAS_PRODUCTS_DESCRIPTIONS": DESCRIPTIONS_CSV,
    })
    rows = read_hs3_csv(z, "reservation")
    # RESSTATUS 7 = geblockt → wird übersprungen
    assert len(rows) == 2
    names = {r["last_name"] for r in rows}
    assert "Weber" in names
    assert "Huber" in names


def test_read_reservations_status_mapping(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {
        "BAS_CUSTOMERS": CUSTOMERS_CSV,
        "MOV_RESERVATIONS": RESERVATIONS_CSV,
        "MOV_RESERVATIONS_OCCUPATION": OCCUPATION_CSV,
    })
    rows = read_hs3_csv(z, "reservation")
    statuses = {r["Status"] for r in rows}
    assert "confirmed" in statuses   # RESSTATUS 3
    assert "check_out" in statuses   # RESSTATUS 9


def test_read_reservations_room_info(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {
        "BAS_CUSTOMERS": CUSTOMERS_CSV,
        "MOV_RESERVATIONS": RESERVATIONS_CSV,
        "MOV_RESERVATIONS_OCCUPATION": OCCUPATION_CSV,
        "BAS_PRODUCTS_OBJECTS": OBJECTS_CSV,
        "BAS_PRODUCTS_DESCRIPTIONS": DESCRIPTIONS_CSV,
    })
    rows = read_hs3_csv(z, "reservation")
    weber = next(r for r in rows if r["last_name"] == "Weber")
    assert weber.get("Zimmer") == "101"
    assert weber.get("Zimmertyp") == "Einzelzimmer"


def test_read_reservations_missing_occupation_raises(tmp_path):
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {
        "BAS_CUSTOMERS": CUSTOMERS_CSV,
        "MOV_RESERVATIONS": RESERVATIONS_CSV,
    })
    with pytest.raises(ValueError, match="MOV_RESERVATIONS_OCCUPATION"):
        read_hs3_csv(z, "reservation")


def test_read_reservations_without_optional_tables(tmp_path):
    """Reservierungen funktionieren auch ohne Zimmer-Tabellen."""
    from hs3_csv_reader import read_hs3_csv
    z = _write_zip(tmp_path, {
        "MOV_RESERVATIONS": RESERVATIONS_CSV,
        "MOV_RESERVATIONS_OCCUPATION": OCCUPATION_CSV,
    })
    rows = read_hs3_csv(z, "reservation")
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Datum-Parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("2024-06-01", "2024-06-01"),
    ("01.06.2024", "2024-06-01"),
    ("2024-06-01 00:00:00", "2024-06-01"),
    ("", ""),
    ("NULL", ""),
])
def test_date_parsing(raw, expected):
    from hs3_csv_reader import _date
    assert _date(raw) == expected
