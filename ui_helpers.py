import html

from document_search import compile_search_terms_pattern


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


