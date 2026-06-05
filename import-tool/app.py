import io
import csv
import zipfile
import tempfile
import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from transformer import get_fields, suggest_mapping, transform, ENTITY_TYPES
from hs3_reader import read_hs3
from hs3_csv_reader import read_hs3_csv, is_hs3_csv_zip
from mews_reader import is_mews_xlsx, read_mews
from bookinglist_reader import is_bookinglist_xlsx, read_bookinglist


def rows_to_csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")  # BOM für Excel-Kompatibilität


def pad_to_schema(rows: list[dict], entity_type: str) -> list[dict]:
    """Ensure every row contains all HotelFriend schema fields (missing ones → empty string)."""
    fields = [f["name"] for f in get_fields(entity_type)]
    return [{field: row.get(field, "") for field in fields} for row in rows]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 700 * 1024 * 1024  # 700 MB (.fdb-Direktdateien bis ~600 MB)

@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/preview")
def preview():
    return render_template("preview.html")

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    entity_type = request.form.get("entity_type")
    if not f or entity_type not in ENTITY_TYPES:
        return jsonify({"error": "Ungültige Anfrage"}), 400

    filename = f.filename or ""
    try:
        if filename.endswith(".csv"):
            raw = f.read()
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
                keep_default_na=False, on_bad_lines="skip"
            )
        elif filename.lower().endswith(".xlsx"):
            raw = f.read()
            buf = io.BytesIO(raw)
            if is_mews_xlsx(buf):
                buf.seek(0)
                rows = read_mews(buf, entity_type)
                if not rows:
                    return jsonify({"error": "Keine Datensätze gefunden."}), 400
                return jsonify({
                    "rows":        rows,
                    "preview":     rows[:5],
                    "valid_count": len(rows),
                    "source":      "mews",
                })
            buf.seek(0)
            if is_bookinglist_xlsx(buf):
                buf.seek(0)
                rows = read_bookinglist(buf, entity_type)
                if not rows:
                    return jsonify({"error": "Keine Datensätze gefunden."}), 400
                return jsonify({
                    "rows":        rows,
                    "preview":     rows[:5],
                    "valid_count": len(rows),
                    "source":      "bookinglist",
                })
            buf.seek(0)
            df = pd.read_excel(buf, dtype=str, keep_default_na=False)
        elif filename.lower().endswith(".txt"):
            raw = f.read()
            try:
                sample = raw[:2048].decode("utf-8-sig")
            except UnicodeDecodeError:
                sample = raw[:2048].decode("cp1252", errors="replace")
            encoding = "utf-8-sig" if "Ã" not in sample else "cp1252"
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(
                io.BytesIO(raw), sep=sep, encoding=encoding, dtype=str,
                keep_default_na=False, on_bad_lines="skip"
            )
        else:
            df = pd.read_excel(f, dtype=str, keep_default_na=False)
    except Exception as e:
        return jsonify({"error": f"Datei konnte nicht gelesen werden: {e}"}), 400

    df = df.fillna("")
    columns = list(df.columns)
    preview = df.head(5).to_dict(orient="records")
    all_rows = df.to_dict(orient="records")
    suggestions = suggest_mapping(columns, entity_type)
    target_fields = get_fields(entity_type)

    return jsonify({
        "columns": columns,
        "preview": preview,
        "all_rows": all_rows,
        "suggestions": suggestions,
        "target_fields": target_fields,
    })

@app.route("/upload_hs3", methods=["POST"])
def upload_hs3():
    f = request.files.get("file")
    entity_type = request.form.get("entity_type")
    if not f or entity_type not in ENTITY_TYPES:
        return jsonify({"error": "Ungültige Anfrage"}), 400

    import tempfile, os
    suffix = ".hsb" if (f.filename or "").lower().endswith(".hsb") else ".fdb"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        f.save(tmp.name)
        tmp.close()
        rows = read_hs3(tmp.name, entity_type)
    except Exception as e:
        return jsonify({"error": f"HS3-Datei konnte nicht gelesen werden: {e}"}), 400
    finally:
        os.unlink(tmp.name)

    if not rows:
        return jsonify({"error": "Keine Datensätze gefunden."}), 400

    return jsonify({
        "rows": rows,
        "preview": rows[:5],
        "valid_count": len(rows),
        "source": "hs3",
    })


@app.route("/upload_hs3_csv", methods=["POST"])
def upload_hs3_csv():
    f = request.files.get("file")
    entity_type = request.form.get("entity_type")
    if not f or entity_type not in ENTITY_TYPES:
        return jsonify({"error": "Ungültige Anfrage"}), 400

    suffix = ".zip"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        f.save(tmp.name)
        tmp.close()
        rows = read_hs3_csv(tmp.name, entity_type)
    except Exception as e:
        return jsonify({"error": f"ZIP konnte nicht gelesen werden: {e}"}), 400
    finally:
        os.unlink(tmp.name)

    if not rows:
        return jsonify({"error": "Keine Datensätze gefunden."}), 400

    return jsonify({
        "rows": rows,
        "preview": rows[:5],
        "valid_count": len(rows),
        "source": "hs3",
    })


@app.route("/validate", methods=["POST"])
def validate():
    data = request.get_json()
    rows = data.get("rows", [])
    entity_type = data.get("entity_type")
    mapping = data.get("mapping", {})

    if entity_type not in ENTITY_TYPES:
        return jsonify({"error": "Unbekannter Entitätstyp"}), 400

    result = transform(rows, entity_type, mapping)
    return jsonify({
        "valid_rows": result.valid_rows,
        "error_rows": result.error_rows,
        "valid_count": len(result.valid_rows),
        "error_count": len(result.error_rows),
    })

@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    # Strip internal meta-fields (prefixed with _) before export
    entity_type = data.get("entity_type", "data")
    valid_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in data.get("valid_rows", [])]
    skipped_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in data.get("skipped_rows", [])]
    # Fill missing schema fields with empty string so HotelFriend gets the expected column structure
    if entity_type in ENTITY_TYPES and valid_rows:
        valid_rows = pad_to_schema(valid_rows, entity_type)
    if entity_type in ENTITY_TYPES and skipped_rows:
        skipped_rows = pad_to_schema(skipped_rows, entity_type)

    if len(valid_rows) <= 100:
        csv_bytes = rows_to_csv_bytes(valid_rows)
        return send_file(
            io.BytesIO(csv_bytes),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{entity_type}_import.csv",
        )

    # Mehr als 100 Zeilen → ZIP mit Chunks
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        chunks = [valid_rows[i:i+100] for i in range(0, len(valid_rows), 100)]
        for idx, chunk in enumerate(chunks, 1):
            zf.writestr(f"{entity_type}_teil_{idx}.csv", rows_to_csv_bytes(chunk).decode("utf-8-sig"))
        if skipped_rows:
            zf.writestr(f"{entity_type}_fehler.csv", rows_to_csv_bytes(skipped_rows).decode("utf-8-sig"))
    zip_buf.seek(0)
    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{entity_type}_import.zip",
    )

@app.route("/download_all", methods=["POST"])
def download_all():
    """
    Upload a single HS3 or Mews file and get a ZIP with valid CSVs
    for all three entity types (guests, companies, reservations).
    """
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "Keine Datei"}), 400

    filename = f.filename or ""
    suffix = Path(filename).suffix.lower()

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        f.save(tmp.name)
        tmp.close()

        if suffix in (".hsb", ".fdb"):
            def reader(et):
                return read_hs3(tmp.name, et)
        elif suffix == ".xlsx":
            with open(tmp.name, "rb") as fh:
                raw = fh.read()
            if not is_mews_xlsx(io.BytesIO(raw)):
                return jsonify({"error": "XLSX ist kein Mews Reservierungsbericht"}), 400
            def reader(et):
                return read_mews(io.BytesIO(raw), et)
        else:
            return jsonify({"error": "Nur HS3 (.hsb/.fdb) und Mews (.xlsx) werden unterstützt"}), 400

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for entity_type in ENTITY_TYPES:
                rows = reader(entity_type)
                if not rows:
                    continue
                fields = [k for k in rows[0] if not k.startswith("_")]
                mapping = {field: field for field in fields}
                result = transform(rows, entity_type, mapping)

                valid_clean = pad_to_schema(
                    [{k: v for k, v in r.items() if not k.startswith("_")} for r in result.valid_rows],
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
                        row = {k: v for k, v in e["row_data"].items() if not k.startswith("_")}
                        row["fehler"] = "; ".join(f'{err["field"]}: {err["reason"]}' for err in e["errors"])
                        err_rows.append(row)
                    zf.writestr(
                        f"{entity_type}_fehler.csv",
                        rows_to_csv_bytes(err_rows).decode("utf-8-sig"),
                    )

        zip_buf.seek(0)
        stem = Path(filename).stem
        return send_file(
            zip_buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{stem}_alle.zip",
        )
    finally:
        os.unlink(tmp.name)


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, port=5050)
