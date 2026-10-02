import http.client
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import fitz

import app
from document_search import build_index, find_keyword, normalize_query


def test_normalize_query():
    assert normalize_query("  Survey   Response  ") == "survey response"


def test_highlight_snippet_escapes_text_and_marks_every_match():
    highlighted = app._highlight_snippet_html(
        "Survey <response> and SURVEY <response>", "survey <response>"
    )

    assert highlighted == (
        "<mark>Survey &lt;response&gt;</mark> and "
        "<mark>SURVEY &lt;response&gt;</mark>"
    )


def test_build_index_and_keyword_search(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "RESEARCH REPORT SERIES")
    page.insert_text((72, 87), "(Survey Methodology #2024-06)")
    page.insert_text(
        (72, 125),
        "Testing SNAP Client Messaging and Application Forms:",
        fontsize=16,
        fontname="hebo",
    )
    page.insert_text((72, 145), "Cognitive Interview Results", fontsize=16, fontname="hebo")
    page.insert_text((72, 185), "Kristen Giombi")
    page.insert_text((72, 215), "This is a survey response test for the research project.")
    doc.save(pdf_path)
    doc.close()

    index_path = tmp_path / "index.json"
    records = build_index(tmp_path, index_path)

    assert len(records) == 1
    assert records[0]["document"] == "sample.pdf"
    assert records[0]["title"] == (
        "Testing SNAP Client Messaging and Application Forms: Cognitive Interview Results"
    )
    assert records[0]["file_path"] == "sample.pdf"
    assert records[0]["page"] == 1

    results = find_keyword("response", index_path, pdf_dir=tmp_path)
    assert len(results) >= 1
    assert results[0]["document"] == "sample.pdf"
    assert results[0]["title"] == records[0]["title"]
    assert results[0]["page"] == 1
    assert "response" in results[0]["snippet"].lower()

    legacy_records = [
        {key: value for key, value in record.items() if key != "title"}
        for record in records
    ]
    index_path.write_text(json.dumps(legacy_records), encoding="utf-8")
    legacy_results = find_keyword("response", index_path, pdf_dir=tmp_path)
    assert legacy_results[0]["title"] == records[0]["title"]


def test_open_pdf_at_page_uses_browser_viewer(monkeypatch, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")

    captured = {}

    def fake_open(url):
        captured["url"] = url
        return True

    monkeypatch.setattr(app.webbrowser, "open_new_tab", fake_open)
    monkeypatch.setattr(app, "_get_or_create_pdf_server", lambda pdf_dir: ("http://127.0.0.1:9999", pdf_dir))

    assert app.open_pdf_at_page(str(pdf_path), 12, "survey & response") is True
    assert captured["url"].startswith("https://mozilla.github.io/pdf.js/web/viewer.html?")
    assert "page=12" in captured["url"]
    assert "sample.pdf" in captured["url"]
    assert parse_qs(urlsplit(captured["url"]).fragment) == {
        "page": ["12"],
        "search": ["survey & response"],
        "phrase": ["true"],
    }


def test_pdf_server_allows_cross_origin_access(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")

    server_url, _ = app._get_or_create_pdf_server(tmp_path)
    host, port = server_url.split("://", 1)[1].split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=5)
    conn.request("GET", "/sample.pdf", headers={"Origin": "https://mozilla.github.io"})
    response = conn.getresponse()
    headers = response.getheaders()
    assert response.status == 200
    assert any(name.lower() == "access-control-allow-origin" and value == "*" for name, value in headers)
    conn.close()
