import json
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

import fitz
import pytest

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
        "<mark>Survey</mark> responses include data."
    )


def test_build_public_pdf_viewer_url_uses_configured_url_and_page(tmp_path):
    pdf_dir = tmp_path / "papers"
    pdf_dir.mkdir()
    pdf_path = pdf_dir / "report with spaces.pdf"
    pdf_path.write_bytes(b"%PDF")

    viewer_url = app.build_public_pdf_viewer_url(
        pdf_path,
        12,
        "survey & response",
        "https://documents.example.org/working-papers/",
        pdf_dir,
    )

    parsed_viewer_url = urlsplit(viewer_url)
    viewer_query = parse_qs(parsed_viewer_url.query)
    assert parsed_viewer_url.netloc == "mozilla.github.io"
    assert viewer_query["file"][0] == (
        "https://documents.example.org/working-papers/report%20with%20spaces.pdf"
    )
    assert parse_qs(parsed_viewer_url.fragment) == {
        "page": ["12"],
        "search": ["survey & response"],
        "phrase": ["true"],
    }


def test_build_public_pdf_viewer_url_rejects_paths_outside_pdf_directory(tmp_path):
    with pytest.raises(ValueError):
        app.build_public_pdf_viewer_url(
            tmp_path.parent / "report.pdf",
            1,
            "",
            "https://documents.example.org/papers",
            tmp_path,
        )


def test_default_pdf_directory_is_bundled_static_pdf_folder():
    from data_config import BUNDLED_PDF_DIR

    assert BUNDLED_PDF_DIR.name == "pdfs"
    assert BUNDLED_PDF_DIR.parent.name == "static"
    assert {path.name for path in BUNDLED_PDF_DIR.glob("*.pdf")} == {
        "rsm2023-11.pdf",
        "rsm2023-12.pdf",
        "rsm2023-13.pdf",
        "rsm2023-14.pdf",
        "rsm2024-01.pdf",
        "rsm2024-02.pdf",
    }


def test_build_local_pdf_url_serves_pdf_in_browser(tmp_path):
    pdf_dir = tmp_path / "papers"
    pdf_dir.mkdir()
    pdf_path = pdf_dir / "report with spaces.pdf"
    pdf_path.write_bytes(b"%PDF local test")

    pdf_url = app.build_local_pdf_url(pdf_path, 7, pdf_dir)

    parsed_url = urlsplit(pdf_url)
    assert parsed_url.netloc.startswith("127.0.0.1:")
    assert parsed_url.path == "/report%20with%20spaces.pdf"
    assert parsed_url.fragment == "page=7"
    with urlopen(f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}") as response:
        assert response.read() == b"%PDF local test"

    server_key = str(pdf_dir.resolve())
    server = app._PDF_SERVERS.pop(server_key)
    server.shutdown()
    server.server_close()


def test_build_local_pdf_url_rejects_paths_outside_pdf_directory(tmp_path):
    with pytest.raises(ValueError):
        app.build_local_pdf_url(tmp_path.parent / "report.pdf", 1, tmp_path)


def test_sort_documents_by_matching_pages_title_author_and_year():
    documents = [
        {
            "title": "Zebra",
            "author": "Taylor",
            "year": 2022,
            "pages": [1, 2],
        },
        {"title": "Alpha", "author": "", "year": None, "pages": [1]},
        {
            "title": "Middle",
            "author": "Anderson",
            "year": 2024,
            "pages": [1, 2, 3],
        },
        {
            "title": "Beta",
            "author": "Brown",
            "year": 2024,
            "pages": [1, 2, 3],
        },
    ]

    assert [
        document["title"]
        for document in app._sort_documents(documents, "Most matching pages")
    ] == ["Beta", "Middle", "Zebra", "Alpha"]
    assert [
        document["title"]
        for document in app._sort_documents(documents, "Title (A-Z)")
    ] == ["Alpha", "Beta", "Middle", "Zebra"]
    assert [
        document["title"]
        for document in app._sort_documents(documents, "Author (A-Z)")
    ] == ["Middle", "Beta", "Zebra", "Alpha"]
    assert [
        document["title"]
        for document in app._sort_documents(documents, "Year (newest first)")
    ] == ["Beta", "Middle", "Zebra", "Alpha"]
    assert [
        document["title"]
        for document in app._sort_documents(documents, "Year (oldest first)")
    ] == ["Zebra", "Beta", "Middle", "Alpha"]


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
    page.insert_text((72, 200), "Report issued: September 2024")
    body_page = doc.new_page()
    body_page.insert_text(
        (72, 72), "This is a survey response test for the research project."
    )
    doc.save(pdf_path)
    doc.close()

    index_path = tmp_path / "index.json"
    records = build_index(tmp_path, index_path)

    assert len(records) == 1
    assert records[0]["document"] == "sample.pdf"
    assert records[0]["title"] == (
        "Testing SNAP Client Messaging and Application Forms: Cognitive Interview Results"
    )
    assert records[0]["author"] == "Kristen Giombi"
    assert records[0]["year"] == 2024
    assert records[0]["file_path"] == "sample.pdf"
    assert records[0]["page"] == 2

    results = find_keyword("response", index_path, pdf_dir=tmp_path)
    assert len(results) >= 1
    assert results[0]["document"] == "sample.pdf"
    assert results[0]["title"] == records[0]["title"]
    assert results[0]["author"] == records[0]["author"]
    assert results[0]["year"] == records[0]["year"]
    assert results[0]["page"] == 2
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


def test_search_terms_match_whole_words_and_consistent_counts(tmp_path):
    index_path = tmp_path / "index.json"
    records = [
        {
            "document": "partial.pdf",
            "title": "Partial",
            "file_path": "partial.pdf",
            "index_version": INDEX_VERSION,
            "page": 1,
            "text": "Combining survey data.",
        },
        {
            "document": "whole.pdf",
            "title": "Whole",
            "file_path": "whole.pdf",
            "index_version": INDEX_VERSION,
            "page": 1,
            "text": "OMB guidance and OMB-related survey data.",
        },
    ]
    index_path.write_text(json.dumps(records), encoding="utf-8")

    results = find_keyword("OMB", index_path, pdf_dir=tmp_path)

    assert [result["document"] for result in results] == ["whole.pdf"]
    assert results[0]["match_count"] == 2
    assert "Combining" not in results[0]["snippet"]
    assert app._highlight_snippet_html("combining OMB", ["OMB"]) == (
        "combining <mark>OMB</mark>"
    )


def test_build_index_uses_report_number_when_issue_date_is_missing(tmp_path):
    pdf_path = tmp_path / "report.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "RESEARCH REPORT SERIES")
    page.insert_text((72, 87), "(Survey Methodology #2025-02)")
    page.insert_text((72, 125), "A Census Research Report", fontsize=16, fontname="hebo")
    doc.new_page().insert_text((72, 72), "Report text about surveys.")
    doc.save(pdf_path)
    doc.close()

    records = build_index(tmp_path, tmp_path / "index.json")

    assert records[0]["year"] == 2025


def test_suggested_citation_authors_override_generic_pdf_metadata(tmp_path):
    pdf_path = tmp_path / "report.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "RESEARCH REPORT SERIES")
    page.insert_text((72, 87), "(Survey Methodology #2023-12)")
    page.insert_text((72, 125), "Research on Public Opinion of Administrative Records")
    page.insert_text((72, 150), "Y. Patrick Hsieh")
    page.insert_text((72, 165), "Sample report contents.")
    citation_page = doc.new_page()
    citation_lines = (
        "Suggested Citation: Y. Patrick Hsieh, Katherine Blackburn, Patty LeBaron",
        "and Aleia Clark Fobia. RTI International and U.S. Census Bureau.",
        "(2023). Research on Public Opinion of Administrative Records.",
    )
    for line_number, line in enumerate(citation_lines):
        citation_page.insert_text((72, 72 + line_number * 15), line)
    doc.set_metadata({"author": "U.S. Census Bureau"})
    doc.save(pdf_path)
    doc.close()

    records = build_index(tmp_path, tmp_path / "index.json")

    assert records[0]["author"] == (
        "Y. Patrick Hsieh, Katherine Blackburn, Patty LeBaron and Aleia Clark Fobia"
    )


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


def test_keyword_search_returns_more_than_twenty_matching_pages(tmp_path):
    index_path = tmp_path / "index.json"
    records = [
        {
            "document": f"doc-{page:02}.pdf",
            "title": f"Document {page}",
            "file_path": f"doc-{page:02}.pdf",
            "index_version": INDEX_VERSION,
            "page": 1,
            "text": "survey response",
        }
        for page in range(25)
    ]
    index_path.write_text(json.dumps(records), encoding="utf-8")

    results = find_keyword("survey", index_path, pdf_dir=tmp_path)

    assert len(results) == 25


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
    assert all(record["index_version"] == 6 for record in records)

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
        record["index_version"] == 6
        for record in json.loads(index_path.read_text(encoding="utf-8"))
    )


def test_index_excludes_title_page_and_abstract(tmp_path):
    pdf_path = tmp_path / "front-matter.pdf"
    doc = fitz.open()

    def add_page(lines):
        page = doc.new_page()
        for line_number, line in enumerate(lines):
            page.insert_text((72, 72 + line_number * 18), line)

    add_page(["RESEARCH REPORT SERIES", "alpha title page"])
    add_page(["Abstract", "alpha abstract content"])
    add_page(["Introduction", "alpha main content"])
    add_page(["The abstract discusses alpha, but this is regular body text."])
    doc.save(pdf_path)
    doc.close()

    records = build_index(tmp_path, tmp_path / "index.json")

    assert [record["page"] for record in records] == [3, 4]
    assert [
        result["page"]
        for result in find_keyword(
            "alpha", tmp_path / "index.json", pdf_dir=tmp_path
        )
    ] == [3, 4]


def test_index_excludes_split_contents_continuation_and_second_title_page(tmp_path):
    pdf_path = tmp_path / "front-matter.pdf"
    doc = fitz.open()

    def add_page(lines):
        page = doc.new_page()
        for line_number, line in enumerate(lines):
            page.insert_text((72, 72 + line_number * 18), line)

    add_page(["RESEARCH REPORT SERIES", "alpha first title page"])
    add_page(["Abstract", "alpha abstract"])
    add_page(["Final Report", "Prepared for:", "alpha second title page"])
    add_page(["iii", "Contents", "1. Introduction ........ 1-1"])
    add_page(
        [
            "iv",
            "4.8",
            "Summary and Recommendations ................................ 4-18",
            "5.",
            "Pennsylvania Cognitive Testing Results",
            "5-1",
            "5.1",
            "Materials ............................................................ 5-1",
            "alpha toc entry",
        ]
    )
    add_page(["1-1", "Introduction", "alpha main content"])
    doc.save(pdf_path)
    doc.close()

    records = build_index(tmp_path, tmp_path / "index.json")

    assert [record["page"] for record in records] == [6]
    assert [
        result["page"]
        for result in find_keyword(
            "alpha", tmp_path / "index.json", pdf_dir=tmp_path
        )
    ] == [6]
