"""Export prepared demo embeddings without making API calls."""
import argparse
import sqlite3
import tempfile
from pathlib import Path

from data_config import ROOT_DIR, LOCAL_DATA_DIR
from document_search import load_index
from report_answers import EMBEDDINGS_PATH, passages_from_records


def write_database(destination: Path, schema: str, insert: str, rows: list) -> None:
    """Publish a complete database atomically; callers decide overwrite policy."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".sqlite3", delete=False) as file:
        temporary = Path(file.name)
    try:
        db = sqlite3.connect(temporary)
        try:
            with db:
                db.execute(schema)
                db.executemany(insert, rows)
        finally:
            db.close()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def export_demo(pdf_dir: Path, source: Path, destination: Path) -> int:
    source, destination = source.resolve(), destination.resolve()
    if source == destination:
        raise ValueError("The export must not overwrite the source database.")
    if destination.exists():
        db = sqlite3.connect(destination.as_uri() + "?mode=ro", uri=True)
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != {"vectors"}:
                raise ValueError("Refusing to replace a database that is not an embeddings-only export.")
        finally:
            db.close()
    records = load_index(LOCAL_DATA_DIR / "demo_document_index.json", pdf_dir)
    keys = {passage["key"] for passage in passages_from_records(records)}
    if not keys:
        raise ValueError("The demo collection contains no searchable passages.")
    db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    try:
        rows = [row for row in db.execute("SELECT key, vector FROM vectors") if row[0] in keys]
    finally:
        db.close()
    if len(rows) != len(keys):
        raise ValueError(f"{len(keys) - len(rows)} demo passages need preparation. No export was written.")
    write_database(destination, "CREATE TABLE vectors (key TEXT PRIMARY KEY, vector TEXT NOT NULL)",
                   "INSERT INTO vectors VALUES (?, ?)", rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=ROOT_DIR / "static/demo-pdfs")
    parser.add_argument("--source", type=Path, default=EMBEDDINGS_PATH)
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "demo-data/embeddings.sqlite3")
    args = parser.parse_args()
    count = export_demo(args.pdf_dir, args.source, args.output)
    print(f"Exported {count} demo embeddings to {args.output}. No spending records or API calls.")


if __name__ == "__main__":
    main()
