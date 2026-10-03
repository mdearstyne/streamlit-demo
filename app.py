import functools
import html
import http.server
import socketserver
import threading
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from document_search import (
    DEFAULT_PDF_DIR,
    DEFAULT_INDEX_PATH,
    build_index,
    compile_search_terms_pattern,
    find_keyword,
    QuerySyntaxError,
)

_PDF_SERVERS = {}


def _highlight_snippet_html(snippet: str, search_terms: list[str]) -> str:
    search_terms = sorted(set(search_terms), key=len, reverse=True)
    if not search_terms:
        return html.escape(snippet)

    pattern = compile_search_terms_pattern(search_terms)
    highlighted_parts = []
    cursor = 0
    for match in pattern.finditer(snippet):
        highlighted_parts.append(html.escape(snippet[cursor : match.start()]))
        highlighted_parts.append(f"<mark>{html.escape(match.group())}</mark>")
        cursor = match.end()
    highlighted_parts.append(html.escape(snippet[cursor:]))
    return "".join(highlighted_parts)


def _sort_documents(documents: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "Most matching pages":
        return sorted(
            documents,
            key=lambda document: (
                -len(document.get("pages", [])),
                (document["title"] or "").casefold(),
            ),
        )
    if sort_by == "Title (A-Z)":
        return sorted(
            documents,
            key=lambda document: (document["title"] or "").casefold(),
        )
    if sort_by == "Author (A-Z)":
        return sorted(
            documents,
            key=lambda document: (
                not bool(document.get("author")),
                (document.get("author") or "").casefold(),
                (document["title"] or "").casefold(),
            ),
        )
    if sort_by == "Year (newest first)":
        return sorted(
            documents,
            key=lambda document: (
                document.get("year") is None,
                -(document.get("year") or 0),
                (document["title"] or "").casefold(),
            ),
        )
    if sort_by == "Year (oldest first)":
        return sorted(
            documents,
            key=lambda document: (
                document.get("year") is None,
                document.get("year") or 0,
                (document["title"] or "").casefold(),
            ),
        )
    raise ValueError(f"Unsupported document sort order: {sort_by}")


class QuietDirectoryHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Origin, X-Requested-With, Content-Type, Accept")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


class QuietTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def _get_or_create_pdf_server(pdf_dir: str | Path):
    pdf_dir = Path(pdf_dir).resolve()
    key = str(pdf_dir)
    server = _PDF_SERVERS.get(key)
    if server is not None:
        return f"http://127.0.0.1:{server.server_address[1]}", pdf_dir

    handler = functools.partial(QuietDirectoryHandler, directory=str(pdf_dir))
    server = QuietTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _PDF_SERVERS[key] = server
    return f"http://127.0.0.1:{server.server_address[1]}", pdf_dir


def build_browser_pdf_url(
    pdf_path: str | Path, page_number: int, search_term: str = ""
):
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        return None

    server_url, pdf_dir = _get_or_create_pdf_server(pdf_dir=pdf_path.parent)
    relative_path = pdf_path.relative_to(pdf_dir).as_posix()
    encoded_file = quote(server_url + "/" + relative_path, safe="")
    viewer_options = f"page={page_number}"
    if search_term.strip():
        viewer_options += f"&search={quote(search_term.strip(), safe='')}&phrase=true"
    return (
        "https://mozilla.github.io/pdf.js/web/viewer.html"
        f"?file={encoded_file}#{viewer_options}"
    )


st.set_page_config(
    page_title="Pretested Question Resource", page_icon="📚", layout="wide"
)

st.title("Pretested Question Resource")
st.caption("Search local PDF working papers for keywords and open the matching file directly from the app.")

with st.sidebar:
    st.header("Settings")
    pdf_dir = st.text_input("PDF folder", value=str(DEFAULT_PDF_DIR))
    rebuild_index = st.button("Rebuild index")

pdf_dir_path = Path(pdf_dir)
index_path = DEFAULT_INDEX_PATH

if not pdf_dir_path.exists():
    st.error(f"The PDF folder does not exist: {pdf_dir_path}")
    st.stop()

if rebuild_index or not index_path.exists():
    with st.spinner("Indexing PDF files..."):
        build_index(pdf_dir_path, index_path)
    st.success(f"Indexed documents from {pdf_dir_path}")

query = st.text_input(
    "Search keyword or phrase",
    value="",
    placeholder="Enter a search term or phrase to begin",
)
st.caption(
    'Use AND, OR, NOT, parentheses, and double quotes for exact phrases. '
    'Example: survey AND (response OR "data collection") AND NOT phone'
)
sort_by = st.selectbox(
    "Sort documents by",
    [
        "Most matching pages",
        "Title (A-Z)",
        "Author (A-Z)",
        "Year (newest first)",
        "Year (oldest first)",
    ],
)
if query:
    try:
        results = find_keyword(query, index_path, pdf_dir=pdf_dir_path)
    except QuerySyntaxError as exc:
        st.error(f"Invalid search query: {exc}")
        results = None
    if results == []:
        st.info(f"No matches found for '{query}'.")
    elif results is not None:
        documents = {}
        for result in results:
            document = documents.setdefault(
                result["path"],
                {
                    "title": result.get("title") or result["document"],
                    "author": result.get("author") or "",
                    "year": result.get("year"),
                    "path": result["path"],
                    "pages": [],
                },
            )
            document["pages"].append(result)

        st.write(
            f"Found {len(results)} matching pages across "
            f"{len(documents)} documents."
        )
        sorted_documents = _sort_documents(list(documents.values()), sort_by)
        for document_idx, document in enumerate(sorted_documents):
            page_count = len(document["pages"])
            page_label = "page" if page_count == 1 else "pages"
            with st.expander(
                f"{document['title']} · {page_count} matching {page_label}",
                expanded=False,
            ):
                st.caption(
                    f"Author: {document['author'] or 'Not available'} · "
                    f"Year: {document['year'] or 'Not available'}"
                )
                st.caption(f"File path: {document['path']}")
                for page_idx, result in enumerate(document["pages"]):
                    st.markdown(
                        f"**Page {result['page']}** · "
                        f"Match count: **{result['match_count']}**"
                    )
                    st.html(
                        _highlight_snippet_html(
                            result["snippet"], result["matched_terms"]
                        )
                    )

                    pdf_url = build_browser_pdf_url(
                        document["path"],
                        result["page"],
                        result["matched_terms"][0]
                        if result["matched_terms"]
                        else "",
                    )
                    if pdf_url:
                        st.link_button(
                            f"Open PDF at page {result['page']}",
                            pdf_url,
                        )
                    else:
                        st.error(f"PDF not found: {document['path']}")
                    if page_idx < page_count - 1:
                        st.divider()
