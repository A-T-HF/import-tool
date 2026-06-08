"""Import Tool — FastAPI-App.

Wandelt CSV/XLSX/HSB/FDB/ZIP-Dateien aus fremden PMS-Systemen in das
HotelFriend-Importformat um. Kein externer Zustand, keine DB — reine
Datei-Transformation (file in → file out).

ROOT_PATH wird über Uvicorn gesetzt (siehe Dockerfile), nicht hier —
damit bleiben die Routen unter ihren kurzen Pfaden und der Nginx-Proxy
funktioniert sauber.
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.transformer import get_fields, suggest_mapping, transform, ENTITY_TYPES
from app.hs3_reader import read_hs3
from app.hs3_csv_reader import read_hs3_csv, is_hs3_csv_zip
from app.mews_reader import is_mews_xlsx, read_mews
from app.bookinglist_reader import is_bookinglist_xlsx, read_bookinglist

# ── Jinja2 + Static ───────────────────────────────────────────────────────

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

app = FastAPI(title="Import Tool")
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")


# ── Helpers ───────────────────────────────────────────────────────────────

def rows_to_csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")  # BOM für Excel-Kompatibilität


def pad_to_schema(rows: list[dict], entity_type: str) -> list[dict]:
    """Ensure every row contains all HotelFriend schema fields (missing → empty string)."""
    fields = [f["name"] for f in get_fields(entity_type)]
    return [{field: row.get(field, "") for field in fields} for row in rows]


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/preview")
def preview(request: Request):
    return templates.TemplateResponse(request, "preview.html")


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    entity_type: str = Form(...),
):
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail="Ungültige Anfrage")

    filename = file.filename or ""
    raw = await file.read()

    try:
        if filename.endswith(".csv"):
            # Auto-detect encoding: try UTF-8, fall back to cp1252 (Windows/Mews exports)
            try:
                sample = raw[:2048].decode("utf-8-sig")
            except UnicodeDecodeError:
                sample = raw[:2048].decode("cp1252", errors="replace")
            encoding = "utf-8-sig" if "Ã" not in sample else "cp1252"
            # Auto-detect separator: semicolon (German Excel) or comma
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(
                io.BytesIO(raw), sep=sep, encoding=encoding, dtype=str,
                keep_default_na=False, on_bad_lines="skip",
            )

        elif filename.lower().endswith(".xlsx"):
            buf = io.BytesIO(raw)
            if is_mews_xlsx(buf):
                buf.seek(0)
                rows = read_mews(buf, entity_type)
                if not rows:
                    raise HTTPException(status_code=400, detail="Keine Datensätze gefunden.")
                return {
                    "rows":        rows,
                    "preview":     rows[:5],
                    "valid_count": len(rows),
                    "source":      "mews",
                }
            buf.seek(0)
            if is_bookinglist_xlsx(buf):
                buf.seek(0)
                rows = read_bookinglist(buf, entity_type)
                if not rows:
                    raise HTTPException(status_code=400, detail="Keine Datensätze gefunden.")
                return {
                    "rows":        rows,
                    "preview":     rows[:5],
                    "valid_count": len(rows),
                    "source":      "bookinglist",
                }
            buf.seek(0)
            df = pd.read_excel(buf, dtype=str, keep_default_na=False)

        elif filename.lower().endswith(".txt"):
            try:
                sample = raw[:2048].decode("utf-8-sig")
            except UnicodeDecodeError:
                sample = raw[:2048].decode("cp1252", errors="replace")
            encoding = "utf-8-sig" if "Ã" not in sample else "cp1252"
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(
                io.BytesIO(raw), sep=sep, encoding=encoding, dtype=str,
                keep_default_na=False, on_bad_lines="skip",
            )

        else:
            df = pd.read_excel(io.BytesIO(raw), dtype=str, keep_default_na=False)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Datei konnte nicht gelesen werden: {exc}"
        ) from exc

    df = df.fillna("")
    columns = list(df.columns)
    preview = df.head(5).to_dict(orient="records")
    all_rows = df.to_dict(orient="records")
    suggestions = suggest_mapping(columns, entity_type)
    target_fields = get_fields(entity_type)

    return {
        "columns":       columns,
        "preview":       preview,
        "all_rows":      all_rows,
        "suggestions":   suggestions,
        "target_fields": target_fields,
    }


@app.post("/upload_hs3")
async def upload_hs3(
    file: UploadFile = File(...),
    entity_type: str = Form(...),
):
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail="Ungültige Anfrage")

    filename = file.filename or ""
    suffix = ".hsb" if filename.lower().endswith(".hsb") else ".fdb"

    # Stream direkt auf Disk — kein raw=file.read(), damit kein RAM-Spike bei großen .fdb
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_name = tmp.name

    try:
        rows = read_hs3(tmp_name, entity_type)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"HS3-Datei konnte nicht gelesen werden: {exc}"
        ) from exc
    finally:
        os.unlink(tmp_name)

    if not rows:
        raise HTTPException(status_code=400, detail="Keine Datensätze gefunden.")

    return {
        "rows":        rows,
        "preview":     rows[:5],
        "valid_count": len(rows),
        "source":      "hs3",
    }


@app.post("/upload_hs3_csv")
async def upload_hs3_csv(
    file: UploadFile = File(...),
    entity_type: str = Form(...),
):
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail="Ungültige Anfrage")

    # Stream direkt auf Disk — kein raw=file.read()
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_name = tmp.name

    try:
        rows = read_hs3_csv(tmp_name, entity_type)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"ZIP konnte nicht gelesen werden: {exc}"
        ) from exc
    finally:
        os.unlink(tmp_name)

    if not rows:
        raise HTTPException(status_code=400, detail="Keine Datensätze gefunden.")

    return {
        "rows":        rows,
        "preview":     rows[:5],
        "valid_count": len(rows),
        "source":      "hs3",
    }


@app.post("/validate")
async def validate(data: dict):
    rows        = data.get("rows", [])
    entity_type = data.get("entity_type")
    mapping     = data.get("mapping", {})

    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail="Unbekannter Entitätstyp")

    result = transform(rows, entity_type, mapping)
    return {
        "valid_rows":   result.valid_rows,
        "error_rows":   result.error_rows,
        "valid_count":  len(result.valid_rows),
        "error_count":  len(result.error_rows),
    }


@app.post("/download")
async def download(data: dict):
    entity_type  = data.get("entity_type", "data")
    valid_rows   = [{k: v for k, v in row.items() if not k.startswith("_")}
                    for row in data.get("valid_rows", [])]
    skipped_rows = [{k: v for k, v in row.items() if not k.startswith("_")}
                    for row in data.get("skipped_rows", [])]

    if entity_type in ENTITY_TYPES and valid_rows:
        valid_rows = pad_to_schema(valid_rows, entity_type)
    if entity_type in ENTITY_TYPES and skipped_rows:
        skipped_rows = pad_to_schema(skipped_rows, entity_type)

    if len(valid_rows) <= 100:
        csv_bytes = rows_to_csv_bytes(valid_rows)
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{entity_type}_import.csv"',
            },
        )

    # Mehr als 100 Zeilen → ZIP mit Chunks
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        chunks = [valid_rows[i:i + 100] for i in range(0, len(valid_rows), 100)]
        for idx, chunk in enumerate(chunks, 1):
            zf.writestr(
                f"{entity_type}_teil_{idx}.csv",
                rows_to_csv_bytes(chunk).decode("utf-8-sig"),
            )
        if skipped_rows:
            zf.writestr(
                f"{entity_type}_fehler.csv",
                rows_to_csv_bytes(skipped_rows).decode("utf-8-sig"),
            )
    zip_buf.seek(0)
    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{entity_type}_import.zip"',
        },
    )


@app.post("/download_all")
async def download_all(file: UploadFile = File(...)):
    """Upload a single HS3 or Mews file → ZIP with valid CSVs for all three entity types."""
    filename = file.filename or ""
    suffix   = Path(filename).suffix.lower()

    # Stream direkt auf Disk — kein raw=file.read() für große Dateien
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_name = tmp.name

    try:
        if suffix in (".hsb", ".fdb"):
            def reader(et: str) -> list[dict]:
                return read_hs3(tmp_name, et)

        elif suffix == ".xlsx":
            with open(tmp_name, "rb") as f:
                if not is_mews_xlsx(f):
                    raise HTTPException(
                        status_code=400,
                        detail="XLSX ist kein Mews Reservierungsbericht",
                    )
            def reader(et: str) -> list[dict]:
                with open(tmp_name, "rb") as f:
                    return read_mews(f, et)

        else:
            raise HTTPException(
                status_code=400,
                detail="Nur HS3 (.hsb/.fdb) und Mews (.xlsx) werden unterstützt",
            )

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for entity_type in ENTITY_TYPES:
                rows = reader(entity_type)
                if not rows:
                    continue
                fields  = [k for k in rows[0] if not k.startswith("_")]
                mapping = {field: field for field in fields}
                result  = transform(rows, entity_type, mapping)

                valid_clean = pad_to_schema(
                    [{k: v for k, v in r.items() if not k.startswith("_")}
                     for r in result.valid_rows],
                    entity_type,
                )
                if valid_clean:
                    zf.writestr(
                        f"{entity_type}_valid.csv",
                        rows_to_csv_bytes(valid_clean).decode("utf-8-sig"),
                    )

                if result.error_rows:
                    err_rows = []
                    for e in result.error_rows:
                        row = {k: v for k, v in e["row_data"].items()
                               if not k.startswith("_")}
                        row["fehler"] = "; ".join(
                            f'{err["field"]}: {err["reason"]}' for err in e["errors"]
                        )
                        err_rows.append(row)
                    zf.writestr(
                        f"{entity_type}_fehler.csv",
                        rows_to_csv_bytes(err_rows).decode("utf-8-sig"),
                    )

        zip_buf.seek(0)
        stem = Path(filename).stem
        return Response(
            content=zip_buf.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}_alle.zip"',
            },
        )

    finally:
        os.unlink(tmp_name)
