from pathlib import Path

import streamlit as st

from data_config import (
    DEFAULT_INDEX_PATH, DEFAULT_PDF_DIR, ENABLE_ADMIN_CONTROLS, ROOT_DIR, STATIC_DIR,
)
from document_search import QuerySyntaxError, build_index, load_index, search_records
from pdf_viewer import build_browser_pdf_url
from ui_helpers import _highlight_snippet_html, _sort_documents


@st.cache_data(show_spinner=False, max_entries=32)
def cached_search(query: str, records: list[dict], pdf_dir: str) -> list[dict]:
    return search_records(query, records, pdf_dir)


def main():
    st.set_page_config(
        page_title="Pretested Question Resource", page_icon="📚", layout="wide"
    )

    st.title("Pretested Question Resource")
    st.caption("Search PDF working papers and open matching pages in your browser.")

    pdf_dir = str(DEFAULT_PDF_DIR)
    rebuild_index = False
    if ENABLE_ADMIN_CONTROLS:
        with st.sidebar:
            st.header("Settings")
            pdf_dir = st.text_input("PDF folder", value=pdf_dir)
            rebuild_index = st.button("Rebuild index")

    pdf_dir_path = Path(pdf_dir).expanduser()
    if not pdf_dir_path.is_absolute():
        pdf_dir_path = ROOT_DIR / pdf_dir_path
    pdf_dir_path = pdf_dir_path.resolve()
    index_path = DEFAULT_INDEX_PATH

    if not pdf_dir_path.is_dir():
        if ENABLE_ADMIN_CONTROLS:
            st.error(f"The PDF folder does not exist or is not a directory: {pdf_dir_path}")
        else:
            st.error("The document collection is unavailable. Please contact the app administrator.")
        st.stop()

    if not pdf_dir_path.is_relative_to(STATIC_DIR.resolve()):
        st.error("The PDF folder must be inside the project static directory. "
                 "Use static/pdfs, or mount your server collection there.")
        st.stop()

    try:
        if not any(path.is_file() for path in pdf_dir_path.glob("*.pdf")):
            st.info("No PDFs available in this collection.")
            if ENABLE_ADMIN_CONTROLS:
                st.caption("Add PDFs directly to the configured folder, then refresh the app. "
                           "Files in subfolders are not searched.")
            else:
                st.caption("The app administrator needs to supply the document collection.")
            st.stop()
        with st.spinner("Checking and updating the PDF index..."):
            if rebuild_index:
                build_index(pdf_dir_path, index_path)
            records = load_index(index_path, pdf_dir_path)
    except (OSError, ValueError) as exc:
        if ENABLE_ADMIN_CONTROLS:
            st.error(f"Could not load the PDF collection: {exc}")
        else:
            st.error("Could not load the document collection. Please contact the app administrator.")
        st.stop()
    if rebuild_index:
        st.success(f"Indexed documents from {pdf_dir_path}")
    if not records:
        st.info("No searchable text was found. Check that the folder contains PDFs with selectable text.")
        st.stop()

    query = st.text_input(
        "Search keyword or phrase",
        value="",
        placeholder="Enter a search term or phrase to begin",
    )
    st.caption(
        'Searches apply to each page: AND terms must occur on the same page. '
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
            results = cached_search(query, records, str(pdf_dir_path))
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
            st.caption("PDF links request the matching page where supported; some mobile viewers "
                       "open at the beginning. Use Find in your PDF viewer to highlight terms. "
                       "Page numbers refer to PDF pages, not printed page labels.")
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
                    st.caption(f"File: {Path(document['path']).name}")
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
                            document["path"], result["page"], result["matched_terms"]
                        )
                        st.link_button(f"Open PDF at page {result['page']}", pdf_url)
                        if page_idx < page_count - 1:
                            st.divider()


if __name__ == "__main__":
    main()
