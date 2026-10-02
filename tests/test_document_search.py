import http.client
from pathlib import Path

import fitz

import app
from document_search import build_index, find_keyword, normalize_query


def test_normalize_query():
    assert normalize_query("  Survey   Response  ") == "survey response"


def test_build_index_and_keyword_search(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This is a survey response test for the research project.")
    doc.save(pdf_path)
    doc.close()

    index_path = tmp_path / "index.json"
    records = build_index(tmp_path, index_path)

    assert len(records) == 1
    assert records[0]["document"] == "sample.pdf"
    assert records[0]["page"] == 1

    results = find_keyword("response", index_path)
    assert len(results) >= 1
    assert results[0]["document"] == "sample.pdf"
    assert results[0]["page"] == 1
    assert "response" in results[0]["snippet"].lower()


def test_open_pdf_at_page_uses_browser_viewer(monkeypatch, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")

    captured = {}

    def fake_open(url):
        captured["url"] = url
        return True

    monkeypatch.setattr(app.webbrowser, "open_new_tab", fake_open)
    monkeypatch.setattr(app, "_get_or_create_pdf_server", lambda pdf_dir: ("http://127.0.0.1:9999", pdf_dir))

    assert app.open_pdf_at_page(str(pdf_path), 12) is True
    assert captured["url"].startswith("https://mozilla.github.io/pdf.js/web/viewer.html?")
    assert "page=12" in captured["url"]
    assert "sample.pdf" in captured["url"]


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
