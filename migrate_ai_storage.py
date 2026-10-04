"""Split legacy AI storage while retaining the original database as a backup."""
import argparse
import sqlite3
from pathlib import Path

from data_config import LOCAL_DATA_DIR, _configured_path
from export_demo_embeddings import write_database
from report_answers import EMBEDDINGS_PATH, SPENDING_PATH


def migrate(source: Path) -> None:
    if EMBEDDINGS_PATH == SPENDING_PATH or source.resolve() in {EMBEDDINGS_PATH, SPENDING_PATH}:
        raise ValueError("Migration requires three distinct database paths.")
    if EMBEDDINGS_PATH.exists() or SPENDING_PATH.exists():
        raise ValueError("Destination databases already exist. Migration will not overwrite them.")
    db = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        # Read both tables from one snapshot, including in-flight cost reservations.
        db.execute("BEGIN")
        vectors = list(db.execute("SELECT key, vector FROM vectors"))
        spending = list(db.execute("SELECT id, day, category, amount FROM spend"))
    finally:
        db.close()
    # Publish the ledger first: a partial migration must never erase budget history.
    write_database(SPENDING_PATH,
                   "CREATE TABLE spend (id INTEGER PRIMARY KEY, day TEXT, category TEXT, amount REAL)",
                   "INSERT INTO spend VALUES (?, ?, ?, ?)", spending)
    write_database(EMBEDDINGS_PATH,
                   "CREATE TABLE vectors (key TEXT PRIMARY KEY, vector TEXT NOT NULL)",
                   "INSERT INTO vectors VALUES (?, ?)", vectors)
    print(f"Migrated {len(vectors)} embeddings and {len(spending)} spending records.")
    print("Original database retained unchanged as a backup. Restart the app before further paid requests.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=_configured_path("AI_DATA_PATH", LOCAL_DATA_DIR / "report_answers.sqlite3"))
    migrate(parser.parse_args().source)


if __name__ == "__main__":
    main()
