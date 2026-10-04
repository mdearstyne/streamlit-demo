from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from data_config import STATIC_DIR
from pdf_viewer import build_browser_pdf_url


def test_local_link_opens_the_matching_page():
    url = build_browser_pdf_url(STATIC_DIR / "pdfs/rsm2024-06.pdf", 12, ["SNAP"])
    parsed = urlsplit(url)
    assert parsed.scheme == ""
    assert parsed.netloc == ""
    assert parsed.path == "app/static/pdfs/rsm2024-06.pdf"
    assert parse_qs(parsed.fragment) == {"page": ["12"], "search": ["SNAP"]}


def test_link_does_not_need_to_read_a_local_file():
    missing = STATIC_DIR / "pdfs/not-downloaded.pdf"
    assert build_browser_pdf_url(missing, 3, []).endswith("#page=3")


def test_local_url_encodes_filename_and_phrase():
    url = build_browser_pdf_url(
        STATIC_DIR / "pdfs/survey #1 & 50%.pdf", 7, ["data collection", "survey"]
    )
    parsed = urlsplit(url)
    assert parsed.netloc == ""
    assert unquote(parsed.path) == "app/static/pdfs/survey #1 & 50%.pdf"
    assert parse_qs(parsed.fragment) == {"page": ["7"], "search": ["data collection"]}


def test_document_outside_static_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        build_browser_pdf_url(tmp_path / "custom.pdf", 1, [])


@pytest.mark.parametrize("page", [0, -1])
def test_invalid_page_is_rejected(page):
    with pytest.raises(ValueError, match="start at 1"):
        build_browser_pdf_url(STATIC_DIR / "pdfs/rsm2024-06.pdf", page, [])
