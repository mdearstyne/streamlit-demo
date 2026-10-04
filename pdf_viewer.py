from pathlib import Path
from urllib.parse import quote, urlencode

from data_config import STATIC_DIR


def build_browser_pdf_url(
    pdf_path: str | Path,
    page_number: int,
    search_terms: list[str],
) -> str:
    """Open the indexed file through Streamlit's built-in static file server."""
    if page_number < 1:
        raise ValueError("PDF page numbers start at 1.")
    relative_path = Path(pdf_path).resolve().relative_to(STATIC_DIR.resolve())
    options = {"page": str(page_number)}
    if search_terms:
        options["search"] = search_terms[0]
    return "app/static/" + quote(relative_path.as_posix(), safe="/") + "#" + urlencode(
        options, quote_via=quote
    )
