import http.client
import json
from urllib.parse import parse_qs, urlsplit

import fitz

import app
from document_search import (
    INDEX_VERSION,
    QuerySyntaxError,
    build_index,
    find_keyword,
)


def test_highlight_snippet_escapes_text_and_marks_every_match():
    highlighted = app._highlight_snippet_html(
        "Survey <response> and SURVEY <response>", ["survey <response>"]
    )

    assert highlighted == (
        "<mark>Survey &lt;response&gt;</mark> and "
        "<mark>SURVEY &lt;response&gt;</mark>"
    )


def test_highlight_snippet_marks_multiple_boolean_terms():
    highlighted = app._highlight_snippet_html(
        "Survey responses include data.", ["survey", "response"]
    )

    assert highlighted == (
        "<mark>Survey</mark> <mark>response</mark>s include data."
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
    assert results[0]["matched_terms"] == ["response"]
    assert "response" in results[0]["snippet"].lower()

    assert find_keyword("survey AND response", index_path, pdf_dir=tmp_path)
    assert find_keyword(
        'survey AND ("response test" OR "missing phrase")',
        index_path,
        pdf_dir=tmp_path,
    )
    assert find_keyword(
        "survey AND NOT phone", index_path, pdf_dir=tmp_path
    )
    assert find_keyword(
        'survey AND ("response test" OR "missing phrase") AND NOT phone',
        index_path,
        pdf_dir=tmp_path,
    )
    assert find_keyword(
        "survey OR phone", index_path, pdf_dir=tmp_path
    )[0]["matched_terms"] == ["survey"]
    assert find_keyword(
        'NOT "missing phrase"', index_path, pdf_dir=tmp_path
    )

    for invalid_query in (
        "survey response",
        "survey AND",
        "survey OR OR phone",
        '(survey OR response',
        '"unclosed phrase',
    ):
        try:
            find_keyword(invalid_query, index_path, pdf_dir=tmp_path)
        except QuerySyntaxError:
            pass
        else:
            raise AssertionError(f"Expected invalid query: {invalid_query}")

    legacy_records = [
        {key: value for key, value in record.items() if key != "title"}
        for record in records
    ]
    index_path.write_text(json.dumps(legacy_records), encoding="utf-8")
    legacy_results = find_keyword("response", index_path, pdf_dir=tmp_path)
    assert legacy_results[0]["title"] == records[0]["title"]


def test_boolean_search_operators_precedence_and_phrases(tmp_path):
    index_path = tmp_path / "index.json"
    records = [
        {
            "document": f"doc-{page}.pdf",
            "title": f"Document {page}",
            "file_path": f"doc-{page}.pdf",
            "index_version": INDEX_VERSION,
            "page": 1,
            "text": text,
        }
        for page, text in enumerate(
            (
                "alpha beta",
                "gamma",
                "alpha gamma",
                "alpha beta gamma",
            ),
            start=1,
        )
    ]
    index_path.write_text(json.dumps(records), encoding="utf-8")

    precedence_results = find_keyword(
        "alpha OR beta AND gamma", index_path, pdf_dir=tmp_path
    )
    assert {result["document"] for result in precedence_results} == {
        "doc-1.pdf",
        "doc-3.pdf",
        "doc-4.pdf",
    }

    not_results = find_keyword(
        "alpha AND NOT beta", index_path, pdf_dir=tmp_path
    )
    assert [result["document"] for result in not_results] == ["doc-3.pdf"]

    phrase_results = find_keyword('"alpha beta"', index_path, pdf_dir=tmp_path)
    assert {result["document"] for result in phrase_results} == {
        "doc-1.pdf",
        "doc-4.pdf",
    }


def test_index_excludes_contents_and_references_and_sorts_by_page(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()

    def add_page(lines):
        page = doc.new_page()
        for line_number, line in enumerate(lines):
            page.insert_text((72, 72 + line_number * 18), line)

    add_page(["alpha introduction"])
    add_page(
        [
            "Contents",
            "1 Overview ........ 2",
            "2 Findings ........ 4",
            "References ........ 5",
        ]
    )
    add_page(
        [
            "3 Recommendations ........ 5",
            "4 Appendix ........ 6",
            "5 Survey questions ........ 7",
        ]
    )
    add_page(["alpha main text"])
    add_page(["References", "alpha cited source"])
    add_page(["alpha continued reference"])
    add_page(["alpha appendix"])
    doc.save(pdf_path)
    doc.close()

    index_path = tmp_path / "index.json"
    records = build_index(tmp_path, index_path)
    assert [record["page"] for record in records] == [1, 4]
    assert all(record["index_version"] == 2 for record in records)

    results = find_keyword("alpha", index_path, pdf_dir=tmp_path)
    assert [result["page"] for result in results] == [1, 4]

    outdated_records = [
        {key: value for key, value in record.items() if key != "index_version"}
        for record in records
    ]
    outdated_records.append(
        {
            "document": "sample.pdf",
            "title": "sample",
            "file_path": "sample.pdf",
            "page": 2,
            "text": "alpha outdated contents page",
        }
    )
    index_path.write_text(json.dumps(outdated_records), encoding="utf-8")

    refreshed_results = find_keyword("alpha", index_path, pdf_dir=tmp_path)
    assert [result["page"] for result in refreshed_results] == [1, 4]
    assert all(
        record["index_version"] == 2
        for record in json.loads(index_path.read_text(encoding="utf-8"))
    )


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
