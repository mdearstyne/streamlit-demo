import functools
import html
import http.server
import socketserver
import threading
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from document_search import (
    DEFAULT_INDEX_PATH,
    DEFAULT_PDF_DIR,
    QuerySyntaxError,
    build_index,
    compile_search_terms_pattern,
    find_keyword,
)
from data_config import BUNDLED_PDF_DIR, PDF_ACCESS_MODE, PDF_BASE_URL


def _deployment_setting(name: str, default: str) -> str:
    try:
        value = st.secrets.get(name, default)
    except StreamlitSecretNotFoundError:
        return default
    return str(value).strip()


PDF_ACCESS_MODE = _deployment_setting(
    "PDF_ACCESS_MODE", PDF_ACCESS_MODE
).casefold()
PDF_BASE_URL = _deployment_setting("PDF_BASE_URL", PDF_BASE_URL).rstrip("/")


class QuietDirectoryHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        del _format, _args
        return


class QuietTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


@st.cache_resource
def _get_or_create_pdf_server(pdf_dir: str) -> socketserver.TCPServer:
    handler = functools.partial(
        QuietDirectoryHandler, directory=pdf_dir
    )
    server = QuietTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def build_local_pdf_url(
    pdf_path: str | Path, page_number: int, pdf_dir: str | Path
) -> str | None:
    resolved_path = Path(pdf_path).resolve()
    resolved_dir = Path(pdf_dir).resolve()
    try:
        relative_path = resolved_path.relative_to(resolved_dir)
    except ValueError:
        raise ValueError("PDF path must be inside the configured PDF directory.")
    if not resolved_path.is_file():
        return None
    server = _get_or_create_pdf_server(str(resolved_dir))
    server_url = f"http://127.0.0.1:{server.server_address[1]}"
    return (
        f"{server_url}/{quote(relative_path.as_posix(), safe='/')}"
        f"#page={page_number}"
    )


def build_public_pdf_url(
    pdf_path: str | Path,
    page_number: int,
    pdf_base_url: str,
    pdf_dir: str | Path,
) -> str:
    parsed_base_url = urlsplit(pdf_base_url)
    if (
        parsed_base_url.scheme not in {"http", "https"}
        or not parsed_base_url.netloc
        or parsed_base_url.query
        or parsed_base_url.fragment
    ):
        raise ValueError(
            "PDF_BASE_URL must be an HTTP(S) URL without a query or fragment."
        )

    relative_path = Path(pdf_path).resolve().relative_to(
        Path(pdf_dir).resolve()
    )
    encoded_pdf_url = (
        f"{pdf_base_url.rstrip('/')}/"
        f"{quote(relative_path.as_posix(), safe='/')}"
    )
    return f"{encoded_pdf_url}#page={page_number}"


def _append_path_to_app_url(app_url: str, path: str) -> str:
    parsed_app_url = urlsplit(app_url)
    if parsed_app_url.scheme not in {"http", "https"} or not parsed_app_url.netloc:
        raise ValueError("Streamlit app URL must be an HTTP(S) URL.")
    app_path = f"{parsed_app_url.path.rstrip('/')}{path}"
    return urlunsplit(
        (parsed_app_url.scheme, parsed_app_url.netloc, app_path, "", "")
    )


def build_cloud_static_pdf_url(
    pdf_path: str | Path,
    page_number: int,
    app_url: str,
    pdf_dir: str | Path,
) -> str:
    if Path(pdf_dir).resolve() != BUNDLED_PDF_DIR.resolve():
        raise ValueError(
            "Cloud static PDF links require the bundled static PDF directory."
        )
    pdf_base_url = _append_path_to_app_url(
        app_url, "/~/+/app/static/pdfs"
    )
    return build_public_pdf_url(
        pdf_path, page_number, pdf_base_url, pdf_dir
    )


def build_local_static_pdf_url(
    pdf_path: str | Path,
    page_number: int,
    app_url: str,
    pdf_dir: str | Path,
) -> str:
    if Path(pdf_dir).resolve() != BUNDLED_PDF_DIR.resolve():
        raise ValueError(
            "Streamlit static PDF links require the bundled static PDF directory."
        )
    pdf_base_url = _append_path_to_app_url(
        app_url, "/app/static/pdfs"
    )
    return build_public_pdf_url(
        pdf_path, page_number, pdf_base_url, pdf_dir
    )


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


st.set_page_config(
    page_title="Pretested Question Resource", page_icon="📚", layout="wide"
)

st.title("Pretested Question Resource")
st.caption("Search PDF working papers for keywords and phrases.")

if PDF_ACCESS_MODE not in {"local", "public"}:
    st.error("PDF_ACCESS_MODE must be either 'local' or 'public'.")
    st.stop()

with st.sidebar:
    st.header("Settings")
    pdf_dir = st.text_input("PDF folder", value=str(DEFAULT_PDF_DIR))
    rebuild_index = st.button("Rebuild index")
    if PDF_ACCESS_MODE == "local":
        st.caption(
            "PDFs open from this computer's local PDF folder in the browser."
        )
    else:
        st.caption(
            "PDFs open from this app's public static files."
            if not PDF_BASE_URL
            else f"PDFs open from the configured public host: {PDF_BASE_URL}"
        )

pdf_dir_path = Path(pdf_dir).expanduser().resolve()
index_path = DEFAULT_INDEX_PATH

if not pdf_dir_path.exists():
    st.error(f"The PDF folder does not exist: {pdf_dir_path}")
    st.stop()

if (
    PDF_ACCESS_MODE == "public"
    and not PDF_BASE_URL
    and pdf_dir_path != BUNDLED_PDF_DIR.resolve()
):
    st.error(
        "Set PDF_BASE_URL when using public access with a PDF folder other "
        "than the bundled static PDFs."
    )
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
    "Search report text with whole-word keywords or quoted exact phrases. Use AND to "
    "require terms, OR to match alternatives, NOT to exclude terms, and "
    "parentheses to group conditions. Example: survey AND (response OR "
    '"data collection") AND NOT phone'
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

        document_count = len(documents)
        document_label = "document" if document_count == 1 else "documents"
        st.write(f"Found {document_count} {document_label}.")
        sorted_documents = _sort_documents(list(documents.values()), sort_by)
        for document in sorted_documents:
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
                    if (
                        PDF_ACCESS_MODE == "local"
                        and pdf_dir_path == BUNDLED_PDF_DIR.resolve()
                    ):
                        pdf_url = build_local_static_pdf_url(
                            document["path"],
                            result["page"],
                            st.context.url,
                            pdf_dir_path,
                        )
                    elif PDF_ACCESS_MODE == "local":
                        pdf_url = build_local_pdf_url(
                            document["path"], result["page"], pdf_dir_path
                        )
                    elif PDF_BASE_URL:
                        pdf_url = build_public_pdf_url(
                            document["path"],
                            result["page"],
                            PDF_BASE_URL,
                            pdf_dir_path,
                        )
                    else:
                        pdf_url = build_cloud_static_pdf_url(
                            document["path"],
                            result["page"],
                            st.context.url,
                            pdf_dir_path,
                        )
                    if pdf_url:
                        st.link_button(
                            f"Open PDF in browser at page {result['page']}",
                            pdf_url,
                        )

                    if page_idx < page_count - 1:
                        st.divider()
