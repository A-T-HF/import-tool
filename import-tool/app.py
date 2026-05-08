import io
import csv
import zipfile
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from transformer import get_fields, suggest_mapping, transform, ENTITY_TYPES
from hs3_reader import read_hs3

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB (HSB-Backups bis ~30 MB)

@app.route("/")
def index():
    return render_template("index.html")

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
    valid_rows = data.get("valid_rows", [])
    skipped_rows = data.get("skipped_rows", [])
    entity_type = data.get("entity_type", "data")

    def rows_to_csv_bytes(rows: list[dict]) -> bytes:
        if not rows:
            return b""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8-sig")  # BOM für Excel-Kompatibilität

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

if __name__ == "__main__":
    app.run(debug=True, port=5050)
