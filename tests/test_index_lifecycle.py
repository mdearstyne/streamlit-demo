import importlib
import json
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest

import app
import document_search
from document_search import build_index, find_keyword, load_index


def write_pdf(path, pages):
    with fitz.open() as doc:
        for text in pages:
            doc.new_page().insert_text((72, 72), text)
        doc.save(path)


def test_switching_folders_does_not_reuse_old_text(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    write_pdf(first / "report.pdf", ["alpha"])
    write_pdf(second / "report.pdf", ["beta"])
    index = tmp_path / "index.json"

    assert find_keyword("alpha", index, first)
    assert find_keyword("alpha", index, second) == []
    assert find_keyword("beta", index, second)[0]["path"] == str(second / "report.pdf")


def test_added_edited_and_deleted_pdfs_refresh_results(tmp_path):
    index = tmp_path / "index.json"
    pdf = tmp_path / "report.pdf"
    write_pdf(pdf, ["alpha"])
    assert find_keyword("alpha", index, tmp_path)

    write_pdf(pdf, ["beta replacement text"])
    assert find_keyword("alpha", index, tmp_path) == []
    assert find_keyword("beta", index, tmp_path)

    other = tmp_path / "other.pdf"
    write_pdf(other, ["gamma"])
    assert find_keyword("gamma", index, tmp_path)
    other.unlink()
    assert find_keyword("gamma", index, tmp_path) == []
    pdf.unlink()
    assert load_index(index, tmp_path) == []


@pytest.mark.parametrize("damaged", ["{", "[]", "null", '{"records": null}'])
def test_damaged_or_old_index_is_rebuilt(tmp_path, damaged):
    write_pdf(tmp_path / "report.pdf", ["alpha"])
    index = tmp_path / "index.json"
    index.write_text(damaged, encoding="utf-8")
    assert find_keyword("alpha", index, tmp_path)
    assert json.loads(index.read_text(encoding="utf-8"))["index_version"] == document_search.INDEX_VERSION


def test_invalid_current_record_is_rebuilt(tmp_path):
    write_pdf(tmp_path / "report.pdf", ["alpha"])
    index = tmp_path / "index.json"
    build_index(tmp_path, index)
    payload = json.loads(index.read_text(encoding="utf-8"))
    del payload["records"][0]["title"]
    index.write_text(json.dumps(payload), encoding="utf-8")
    assert find_keyword("alpha", index, tmp_path)[0]["title"] == "report.pdf"


def test_failed_write_preserves_old_index_and_removes_temporary_file(tmp_path, monkeypatch):
    write_pdf(tmp_path / "report.pdf", ["alpha"])
    index = tmp_path / "index.json"
    build_index(tmp_path, index)
    original = index.read_bytes()

    def fail_replace(self, target):
        raise OSError("replacement failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        build_index(tmp_path, index)
    assert index.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_unreadable_pdf_preserves_index_and_reports_filename(tmp_path):
    write_pdf(tmp_path / "report.pdf", ["alpha"])
    index = tmp_path / "index.json"
    build_index(tmp_path, index)
    original = index.read_bytes()
    (tmp_path / "broken.pdf").write_bytes(b"not a PDF")
    with pytest.raises(ValueError, match="broken.pdf"):
        load_index(index, tmp_path)
    assert index.read_bytes() == original


def test_unchanged_index_is_cached_without_extracting_pdfs(tmp_path):
    write_pdf(tmp_path / "report.pdf", ["alpha"])
    index = tmp_path / "index.json"
    build_index(tmp_path, index)
    with patch.object(document_search.fitz, "open", side_effect=AssertionError("unexpected extraction")):
        assert find_keyword("alpha", index, tmp_path)
        assert find_keyword("alpha", index, tmp_path)
    assert document_search._read_index.cache_info().hits >= 1


def test_appendix_after_references_remains_searchable(tmp_path):
    write_pdf(tmp_path / "report.pdf", [
        "alpha main text", "References\nalpha reference", "alpha continued reference",
        "Appendix A: Questionnaire\nalpha question", "alpha continued appendix",
    ])
    assert [item["page"] for item in find_keyword("alpha", tmp_path / "index.json", tmp_path)] == [1, 4, 5]


def test_queries_are_evaluated_per_page(tmp_path):
    write_pdf(tmp_path / "report.pdf", ["alpha", "beta"])
    index = tmp_path / "index.json"
    assert find_keyword("alpha AND beta", index, tmp_path) == []
    assert [item["page"] for item in find_keyword("alpha AND NOT beta", index, tmp_path)] == [1]


def test_importing_app_has_no_ui_or_indexing_side_effects():
    with patch.object(app.st, "set_page_config", side_effect=AssertionError("UI ran")):
        with patch.object(document_search, "build_index", side_effect=AssertionError("indexing ran")):
            importlib.reload(app)


def test_cached_search_changes_when_indexed_text_changes(tmp_path):
    write_pdf(tmp_path / "report.pdf", ["alpha"])
    index = tmp_path / "index.json"
    first = load_index(index, tmp_path)
    assert app.cached_search("alpha", first, str(tmp_path))
    write_pdf(tmp_path / "report.pdf", ["beta replacement text"])
    second = load_index(index, tmp_path)
    assert app.cached_search("alpha", second, str(tmp_path)) == []

