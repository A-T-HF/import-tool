"""Worker-Skript: HS3-Datei in einem separaten Prozess lesen.

Läuft als eigenständiger Subprozess, damit uvicorn bei einem OOM-Kill
(Speicher reicht für große .fdb-Dateien nicht aus) weiterlaufen kann.
Der Hauptprozess wartet asynchron auf das Ergebnis; bei SIGKILL (OOM)
liefert er eine verständliche Fehlermeldung statt eines 502.

Usage:
    python -m app.hs3_worker <file_path> <entity_type> <output_json_path>
"""

import json
import sys


def main() -> None:
    if len(sys.argv) != 4:
        print(
            f"Usage: {sys.argv[0]} <file_path> <entity_type> <output_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    file_path, entity_type, output_path = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        # Lazy import: kein FastAPI-Overhead, nur das HS3-Modul laden
        from app.hs3_reader import read_hs3

        rows = read_hs3(file_path, entity_type)

        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False)

        sys.exit(0)

    except Exception as exc:  # pylint: disable=broad-except
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
