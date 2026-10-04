import sqlite3

import pytest

import export_demo_embeddings as exporter
import migrate_ai_storage as migration
import report_answers as ai


def database_rows(path, table):
    db = sqlite3.connect(path)
    try:
        return list(db.execute(f"SELECT * FROM {table}"))
    finally:
        db.close()


def test_migration_preserves_records_and_original(tmp_path, monkeypatch):
    source = tmp_path / "old.sqlite3"
    embeddings, spending = tmp_path / "embeddings.sqlite3", tmp_path / "usage.sqlite3"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE vectors (key TEXT PRIMARY KEY, vector TEXT)")
        db.execute("CREATE TABLE spend (id INTEGER PRIMARY KEY, day TEXT, category TEXT, amount REAL)")
        db.execute("INSERT INTO vectors VALUES ('key', '[1.0]')")
        db.execute("INSERT INTO spend VALUES (42, '2026-01-01', 'answers', 0.1)")
    original = source.read_bytes()
    monkeypatch.setattr(migration, "EMBEDDINGS_PATH", embeddings)
    monkeypatch.setattr(migration, "SPENDING_PATH", spending)
    migration.migrate(source)
    assert database_rows(embeddings, "vectors") == [("key", "[1.0]")]
    assert database_rows(spending, "spend") == [(42, "2026-01-01", "answers", 0.1)]
    assert source.read_bytes() == original
    with pytest.raises(ValueError, match="already exist"):
        migration.migrate(source)


@pytest.fixture
def demo_export(tmp_path, monkeypatch):
    record = {"text": "Demo findings", "file_path": "demo.pdf", "title": "Demo", "page": 4}
    key = ai.passages_from_records([record])[0]["key"]
    source, destination = tmp_path / "source.sqlite3", tmp_path / "demo.sqlite3"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE vectors (key TEXT PRIMARY KEY, vector TEXT)")
        db.executemany("INSERT INTO vectors VALUES (?, ?)", [(key, "[1.0]"), ("private-report-key", "[0.0]")])
        db.execute("CREATE TABLE spend (id INTEGER PRIMARY KEY, amount REAL)")
        db.execute("INSERT INTO spend VALUES (1, 0.5)")
    monkeypatch.setattr(exporter, "load_index", lambda *args: [record])
    return source, destination, key, tmp_path


def test_export_contains_only_demo_vectors_and_no_spending(demo_export):
    source, destination, key, folder = demo_export
    original = source.read_bytes()
    assert exporter.export_demo(folder, source, destination) == 1
    assert database_rows(destination, "vectors") == [(key, "[1.0]")]
    with sqlite3.connect(destination) as db:
        assert list(db.execute("SELECT name FROM sqlite_master WHERE type='table'")) == [("vectors",)]
    db.close()
    assert source.read_bytes() == original
    assert exporter.export_demo(folder, source, destination) == 1


def test_export_missing_embeddings_preserves_previous_export(demo_export, monkeypatch):
    source, destination, _, folder = demo_export
    exporter.export_demo(folder, source, destination)
    previous = destination.read_bytes()
    monkeypatch.setattr(exporter, "load_index", lambda *args: [{"text": "New demo text", "file_path": "demo.pdf", "title": "Demo", "page": 1}])
    with pytest.raises(ValueError, match="need preparation"):
        exporter.export_demo(folder, source, destination)
    assert destination.read_bytes() == previous


def test_export_refuses_source_and_spending_overwrite(demo_export):
    source, destination, _, folder = demo_export
    with pytest.raises(ValueError, match="source database"):
        exporter.export_demo(folder, source, source)
    with sqlite3.connect(destination) as db:
        db.execute("CREATE TABLE spend (amount REAL)")
    with pytest.raises(ValueError, match="Refusing"):
        exporter.export_demo(folder, source, destination)
