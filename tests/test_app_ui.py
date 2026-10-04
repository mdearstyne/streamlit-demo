from unittest.mock import Mock

import fitz
import pytest
import requests
from streamlit.testing.v1 import AppTest

import app
import answer_ui
import pdf_viewer


@pytest.fixture
def local_app(tmp_path, monkeypatch):
    folder = tmp_path / "static/pdfs"
    folder.mkdir(parents=True)
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), "SNAP benefits survey findings")
        doc.save(folder / "report.pdf")
    monkeypatch.setattr(app, "DEFAULT_PDF_DIR", folder)
    monkeypatch.setattr(app, "STATIC_DIR", folder.parent)
    monkeypatch.setattr(pdf_viewer, "STATIC_DIR", folder.parent)
    monkeypatch.setattr(app, "DEFAULT_INDEX_PATH", tmp_path / "index.json")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("Unexpected API call")))
    return folder


@pytest.mark.parametrize("admin", [False, True])
def test_tabs_catalogue_search_and_admin_controls(local_app, monkeypatch, admin):
    monkeypatch.setattr(app, "ENABLE_ADMIN_CONTROLS", admin)
    at = AppTest.from_string("import app\napp.main()", default_timeout=30).run()
    assert not at.exception
    assert [tab.label for tab in at.tabs] == ["Search", "Available documents", "Ask the reports"]
    assert bool(at.sidebar.text_input) == admin
    assert len(at.dataframe[0].value) == 1
    search = next(widget for widget in at.text_input if widget.label == "Search keyword or phrase")
    search.set_value("SNAP").run()
    assert not at.exception
    assert any("Open PDF at page" in button.label for button in at.get("link_button"))
    requests.post.assert_not_called()


def test_no_text_pdf_remains_in_catalogue(local_app):
    with fitz.open() as doc:
        doc.new_page()
        doc.save(local_app / "report.pdf")
    at = AppTest.from_string("import app\napp.main()", default_timeout=30).run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]["Searchable pages"] == 0
    assert any("No searchable text" in item.value for item in at.info)


def test_ai_preparation_is_not_automatic(local_app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(answer_ui, "ENABLE_ADMIN_CONTROLS", True)
    monkeypatch.setattr(answer_ui, "preparation_plan", lambda passages: (passages, 0.01))
    prepare = Mock()
    monkeypatch.setattr(answer_ui, "prepare", prepare)
    at = AppTest.from_string("import app\napp.main()", default_timeout=30).run()
    assert not at.exception
    assert any(b.label == "Prepare report questions" for b in at.button)
    prepare.assert_not_called()
    requests.post.assert_not_called()


def test_empty_collection_has_specific_message(local_app):
    (local_app / "report.pdf").unlink()
    at = AppTest.from_string("import app\napp.main()", default_timeout=30).run()
    assert not at.exception
    assert any("No PDFs available" in item.value for item in at.info)
    assert not at.dataframe
    requests.post.assert_not_called()


def test_question_form_reruns_do_not_make_paid_requests(local_app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(answer_ui, "ENABLE_ADMIN_CONTROLS", False)
    monkeypatch.setattr(answer_ui, "preparation_plan", lambda passages: ([], 0))
    answer = Mock()
    monkeypatch.setattr(answer_ui, "answer_question", answer)
    at = AppTest.from_string("import app\napp.main()", default_timeout=30).run()
    assert not at.exception
    at.text_area[0].set_value("SNAP findings?").run()
    assert not at.exception
    assert all("$" not in caption.value for caption in at.caption if "Quick answer" in caption.value)
    answer.assert_not_called()
    requests.post.assert_not_called()
