import json
import os
import tempfile
from functools import lru_cache
import re
from pathlib import Path

import fitz

from data_config import DEFAULT_INDEX_PATH, DEFAULT_PDF_DIR

INDEX_VERSION = 8
_CONTENTS_HEADINGS = {"contents", "table of contents"}
_MONTH_YEAR = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\.?\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_TITLE_PAGE_MARKER = re.compile(
    r"^\s*(?:RESEARCH REPORT SERIES\b|Prepared for\s*:|Prepared by\s*:|"
    r"Title Page\s*$)",
    re.IGNORECASE,
)
_REFERENCE_HEADING = re.compile(
    r"^(?:(?:[a-z]-?)?\d+(?:\.\d+)*\s+)?"
    r"(?:references|bibliography|works cited)$",
    re.IGNORECASE,
)
_APPENDIX_HEADING = re.compile(r"appendi(?:x|ces)(?:\s.*|[:.].*)?", re.IGNORECASE)
_AUTHOR_LINE = re.compile(
    r"^[^\W\d_][\w.'’\-]*(?:\s+(?:[^\W\d_][\w.'’\-]*|de|van|von|del|la)){1,5}\s*\d*$",
    re.UNICODE,
)
_AUTHOR_AFFILIATION = re.compile(
    r"^(?:\d+\s*)?(?:RTI International|U\.?S\.? Census Bureau|"
    r"Center for\b|Research and Methodology Directorate\b|"
    r"Project Team\b|IOE\b|Report issued\b|Washington, D\.?C\.?)",
    re.IGNORECASE,
)
_CONTENTS_ENTRY = re.compile(
    r"^\d+(?:\.\d+)*\.?\s+\S.+\s+"
    r"(?:[ivxlcdm]+|\d+(?:-\d+)?|\d+)$",
    re.IGNORECASE,
)


class QuerySyntaxError(ValueError):
    pass


def _tokenize_query(query: str) -> list[tuple[str, str]]:
    token_pattern = re.compile(r'"((?:\\.|[^"\\])*)"|(\()|(\))|([^\s()"]+)')
    tokens = []
    cursor = 0
    for match in token_pattern.finditer(query):
        if query[cursor : match.start()].strip():
            raise QuerySyntaxError("Use double quotes to search for an exact phrase.")
        cursor = match.end()

        phrase, left_paren, right_paren, word = match.groups()
        if phrase is not None:
            phrase = re.sub(r'\\(["\\])', r"\1", phrase)
            if not phrase.strip():
                raise QuerySyntaxError("Quoted phrases cannot be empty.")
            tokens.append(("TERM", phrase))
        elif left_paren:
            tokens.append(("LPAREN", left_paren))
        elif right_paren:
            tokens.append(("RPAREN", right_paren))
        else:
            operator = word.upper()
            if operator in {"AND", "OR", "NOT"}:
                tokens.append((operator, operator))
            else:
                tokens.append(("TERM", word))

    if query[cursor:].strip():
        raise QuerySyntaxError("Unclosed quote or invalid search syntax.")
    return tokens


def _parse_query(query: str) -> tuple:
    tokens = _tokenize_query(query)
    if not tokens:
        raise QuerySyntaxError("Enter a search term.")
    position = 0

    def parse_primary() -> tuple:
        nonlocal position
        if position >= len(tokens):
            raise QuerySyntaxError("Expected a search term.")
        token_type, value = tokens[position]
        if token_type == "TERM":
            position += 1
            return ("TERM", value)
        if token_type == "LPAREN":
            position += 1
            expression = parse_or()
            if position >= len(tokens) or tokens[position][0] != "RPAREN":
                raise QuerySyntaxError("Missing closing parenthesis.")
            position += 1
            return expression
        if token_type == "RPAREN":
            raise QuerySyntaxError("Unexpected closing parenthesis.")
        raise QuerySyntaxError(f"Expected a search term before {value}.")

    def parse_not() -> tuple:
        nonlocal position
        if position < len(tokens) and tokens[position][0] == "NOT":
            position += 1
            return ("NOT", parse_not())
        return parse_primary()

    def parse_and() -> tuple:
        nonlocal position
        expression = parse_not()
        while position < len(tokens) and tokens[position][0] == "AND":
            position += 1
            expression = ("AND", expression, parse_not())
        return expression

    def parse_or() -> tuple:
        nonlocal position
        expression = parse_and()
        while position < len(tokens) and tokens[position][0] == "OR":
            position += 1
            expression = ("OR", expression, parse_and())
        return expression

    parsed = parse_or()
    if position < len(tokens):
        token_type, value = tokens[position]
        if token_type == "RPAREN":
            raise QuerySyntaxError("Unexpected closing parenthesis.")
        if token_type in {"AND", "OR", "NOT"}:
            raise QuerySyntaxError(f"Expected a search term after {value}.")
        raise QuerySyntaxError("Use AND, OR, or NOT between search terms.")
    return parsed


def compile_search_terms_pattern(terms: list[str]) -> re.Pattern[str]:
    alternatives = "|".join(
        re.escape(term) for term in sorted(set(terms), key=len, reverse=True) if term
    )
    if not alternatives:
        return re.compile(r"(?!)")
    return re.compile(
        rf"(?<!\w)(?:{alternatives})(?!\w)",
        re.IGNORECASE,
    )


def _evaluate_query(expression: tuple, text: str) -> tuple[bool, list[str]]:
    kind = expression[0]
    if kind == "TERM":
        term = expression[1]
        return compile_search_terms_pattern([term]).search(text) is not None, [term]
    if kind == "NOT":
        matched, _ = _evaluate_query(expression[1], text)
        return not matched, []

    left_match, left_terms = _evaluate_query(expression[1], text)
    right_match, right_terms = _evaluate_query(expression[2], text)
    if kind == "AND":
        if left_match and right_match:
            return True, left_terms + right_terms
        return False, []
    if left_match or right_match:
        return True, (left_terms if left_match else []) + (
            right_terms if right_match else []
        )
    return False, []


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_contents_heading(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip(" .:-").casefold()
    return normalized in _CONTENTS_HEADINGS


def _looks_like_contents_continuation(page_text: str) -> bool:
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    contents_entries = sum(
        bool(_CONTENTS_ENTRY.match(line))
        or bool(
            re.search(
                r"(?:\.{2,}|…{2,})\s*(?:[ivxlcdm]+|\d+(?:-\d+)?)$",
                line,
                re.I,
            )
        )
        for line in lines
    )
    has_roman_page_label = bool(lines and re.fullmatch(r"[ivxlcdm]+", lines[0], re.I))
    return contents_entries >= 3 or (
        has_roman_page_label and contents_entries >= 2
    )


def _find_excluded_pages(page_texts: list[str]) -> set[int]:
    contents_pages = set()
    title_pages = set()
    in_contents = False

    for page_number, text in enumerate(page_texts, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if page_number <= 5 and any(
            _TITLE_PAGE_MARKER.match(line) for line in lines[:20]
        ):
            title_pages.add(page_number)
        has_contents_heading = any(
            _is_contents_heading(line) for line in lines[:15]
        )
        if has_contents_heading:
            contents_pages.add(page_number)
            in_contents = True
        elif in_contents and _looks_like_contents_continuation(text):
            contents_pages.add(page_number)
        else:
            in_contents = False

    excluded_pages = contents_pages | title_pages
    in_references = False
    for page_number, text in enumerate(page_texts, start=1):
        if page_number in excluded_pages:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        # Recognize headings near the top, not mentions buried in body text.
        if any(_APPENDIX_HEADING.fullmatch(line) for line in lines[:5]):
            in_references = False
        elif any(_REFERENCE_HEADING.fullmatch(line) for line in lines[:20]):
            in_references = True
        if in_references:
            excluded_pages.add(page_number)
    return excluded_pages


def _extract_title(pdf_doc, fallback: str, page_texts: list[str]) -> str:
    metadata_title = _clean_text(pdf_doc.metadata.get("title") or "")
    if metadata_title:
        return metadata_title

    if len(pdf_doc) == 0:
        return fallback

    page = pdf_doc[0]
    formatted_lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            text = _clean_text(" ".join(span["text"] for span in spans))
            if text:
                formatted_lines.append(
                    (text, any("bold" in span["font"].lower() for span in spans))
                )

    series_index = next(
        (
            index
            for index, (line, _) in enumerate(formatted_lines)
            if line.upper().startswith("RESEARCH REPORT SERIES")
        ),
        None,
    )
    if series_index is not None:
        title_lines = []
        for line, is_bold in formatted_lines[series_index + 1 :]:
            if line.startswith("(Survey Methodology"):
                continue
            if is_bold:
                title_lines.append(line)
            elif title_lines:
                break
        if title_lines:
            return _clean_text(" ".join(title_lines))

    lines = page_texts[0].splitlines()
    series_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().upper().startswith("RESEARCH REPORT SERIES")
        ),
        None,
    )
    if series_index is not None:
        title_lines = []
        for line in lines[series_index + 1 :]:
            line = line.strip()
            if not line:
                if title_lines:
                    break
                continue
            if line.startswith("(Survey Methodology"):
                continue
            title_lines.append(line)
        if title_lines:
            return _clean_text(" ".join(title_lines))

    return fallback


def _extract_author(pdf_doc, title: str, page_texts: list[str]) -> str:
    if len(pdf_doc) == 0:
        return ""

    citation_author = _extract_citation_author(page_texts)
    if citation_author:
        return citation_author

    metadata_author = _clean_text(pdf_doc.metadata.get("author") or "")
    normalized_metadata_author = metadata_author.casefold()
    generic_metadata_authors = {
        "",
        "unknown",
        "none",
        "n/a",
        "u.s. census bureau",
        "us census bureau",
        "united states census bureau",
        "census bureau",
    }
    if normalized_metadata_author not in generic_metadata_authors:
        return metadata_author

    lines = page_texts[0].splitlines()
    page_text = " ".join(line.strip() for line in lines if line.strip())
    title_start = page_text.casefold().find(title.casefold())
    if title_start >= 0:
        title_end = title_start + len(title)
        line_offsets = []
        cursor = 0
        for line in lines:
            cleaned_line = line.strip()
            if not cleaned_line:
                continue
            line_offsets.append((cursor, cursor + len(cleaned_line), cleaned_line))
            cursor += len(cleaned_line) + 1

        author_lines = []
        for start, end, line in line_offsets:
            if end <= title_end or start < title_end:
                continue
            if _AUTHOR_AFFILIATION.match(line):
                break
            if not _AUTHOR_LINE.fullmatch(line):
                break
            author_lines.append(re.sub(r"\s+\d+$", "", line))
        if author_lines:
            return "; ".join(author_lines)

    prepared_by = _extract_prepared_by(page_texts)
    if prepared_by:
        return prepared_by
    return metadata_author


def _extract_prepared_by(page_texts: list[str]) -> str:
    for text in page_texts:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            match = re.match(r"^\s*Prepared\s+by\s*:?\s*(.*)$", line, re.I)
            if not match:
                continue
            value = match.group(1).strip(" \t:;,.")
            if value:
                return value
            for following_line in lines[index + 1 :]:
                value = following_line.strip(" \t:;,.")
                if value:
                    return value
    return ""


def _extract_citation_author(page_texts: list[str]) -> str:
    for text in page_texts:
        citation_start = re.search(
            r"\bSuggested Citation\s*:\s*", text, re.IGNORECASE
        )
        if not citation_start:
            continue

        citation = text[citation_start.end() :]
        publication_date = re.search(r"\(\s*(?:19|20)\d{2}\s*\)", citation)
        if not publication_date:
            continue

        authors = _clean_text(citation[: publication_date.start()])
        affiliation = re.search(
            r"(?<=[^\W\d_]{2})\.\s+(?=[^\W\d_])", authors, re.UNICODE
        )
        if affiliation:
            authors = authors[: affiliation.start()]
        authors = authors.strip(" \t\r\n,;.")
        if authors:
            return authors
    return ""


def _extract_publication_year(page_texts: list[str]) -> int | None:
    if not page_texts:
        return None

    first_page = page_texts[0]
    issued_year = re.search(
        r"\bReport issued\s*:\s*.*?\b((?:19|20)\d{2})\b",
        first_page,
        re.IGNORECASE | re.DOTALL,
    )
    if issued_year:
        return int(issued_year.group(1))

    cover_year = _MONTH_YEAR.search(first_page)
    if cover_year:
        return int(cover_year.group(1))

    series_year = re.search(
        r"\bSurvey Methodology\s*#\s*((?:19|20)\d{2})-\d+\b",
        first_page,
        re.IGNORECASE,
    )
    if series_year:
        return int(series_year.group(1))
    return None


def _build_snippet(text: str, keywords: list[str], pad: int = 140) -> str:
    occurrence = compile_search_terms_pattern(keywords).search(text)
    if occurrence is None:
        return _clean_text(text[:pad * 2])

    start, end = occurrence.span()
    snippet_start = max(0, start - pad)
    snippet_end = min(len(text), end + pad)
    snippet = text[snippet_start:snippet_end]
    return _clean_text(snippet)


def _pdf_manifest(pdf_dir: Path) -> list[dict]:
    """A cheap snapshot to detect added, edited, and deleted PDFs."""
    if not pdf_dir.is_dir():
        raise NotADirectoryError(f"PDF folder does not exist or is not a directory: {pdf_dir}")
    files = []
    for path in sorted(pdf_dir.glob("*.pdf")):
        if path.is_file():
            stat = path.stat()
            files.append({
                "name": path.name,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            })
    return files


def _write_index(output_path: Path, payload: dict) -> None:
    """Replace the index only after the complete JSON has been written."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent,
            prefix=output_path.name + ".", suffix=".tmp", delete=False,
        ) as fh:
            temporary_path = Path(fh.name)
            json.dump(payload, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    _read_index.cache_clear()


def build_index(
    pdf_dir: str | Path = DEFAULT_PDF_DIR,
    output_path: str | Path = DEFAULT_INDEX_PATH,
) -> list[dict]:
    pdf_dir = Path(pdf_dir).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    files = _pdf_manifest(pdf_dir)
    records = []
    for file in files:
        pdf_path = pdf_dir / file["name"]
        # A failed extraction must not publish a partial index as up to date.
        try:
            with fitz.open(str(pdf_path)) as pdf_doc:
                page_texts = [page.get_text("text") for page in pdf_doc]
                title = _extract_title(pdf_doc, pdf_path.name, page_texts)
                author = _extract_author(pdf_doc, title, page_texts)
                year = _extract_publication_year(page_texts)
                excluded_pages = _find_excluded_pages(page_texts)
                for page_number, text in enumerate(page_texts, start=1):
                    page_text = _clean_text(text)
                    if page_number in excluded_pages or not page_text:
                        continue
                    records.append({
                        "document": pdf_path.name,
                        "title": title,
                        "author": author,
                        "year": year,
                        "file_path": pdf_path.name,
                        "page": page_number,
                        "text": page_text,
                    })
        except Exception as exc:
            raise ValueError(f"Could not index {pdf_path.name}: {exc}") from exc
    if files != _pdf_manifest(pdf_dir):
        raise ValueError("PDF files changed during indexing. Please try again.")
    _write_index(output_path, {
        "index_version": INDEX_VERSION,
        "pdf_dir": str(pdf_dir),
        "files": files,
        "records": records,
    })
    return records


@lru_cache(maxsize=2)
def _read_index(index_path: str, mtime_ns: int, size: int) -> dict:
    # File metadata is part of the cache key; rebuilding invalidates old data.
    with Path(index_path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _valid_records(records) -> bool:
    if not isinstance(records, list):
        return False
    for record in records:
        if not isinstance(record, dict):
            return False
        if any(
            not isinstance(record.get(key), str)
            for key in ("document", "title", "author", "file_path", "text")
        ):
            return False
        path = Path(record["file_path"])
        if path.name != record["file_path"] or path.is_absolute():
            return False
        if type(record.get("page")) is not int or record["page"] < 1:
            return False
        if record.get("year") is not None and type(record["year"]) is not int:
            return False
    return True


def load_index(
    index_path: str | Path = DEFAULT_INDEX_PATH,
    pdf_dir: str | Path = DEFAULT_PDF_DIR,
) -> list[dict]:
    index_path = Path(index_path).expanduser().resolve()
    pdf_dir = Path(pdf_dir).expanduser().resolve()
    files = _pdf_manifest(pdf_dir)
    try:
        stat = index_path.stat()
        payload = _read_index(str(index_path), stat.st_mtime_ns, stat.st_size)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    if (
        not isinstance(payload, dict)
        or payload.get("index_version") != INDEX_VERSION
        or payload.get("pdf_dir") != str(pdf_dir)
        or payload.get("files") != files
        or not _valid_records(payload.get("records"))
    ):
        # Old list indexes and damaged indexes use the same rebuild path.
        return build_index(pdf_dir, index_path)
    return payload["records"]


def find_keyword(
    query: str,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    pdf_dir: str | Path = DEFAULT_PDF_DIR,
):
    if not query.strip():
        return []
    return search_records(query, load_index(index_path, pdf_dir), pdf_dir)


def search_records(query: str, records: list[dict], pdf_dir: str | Path) -> list[dict]:
    if not query.strip():
        return []
    expression = _parse_query(query)
    matches = []
    for record in records:
        page_text = record["text"]
        matched, matched_terms = _evaluate_query(expression, page_text)
        if not matched:
            continue

        matched_terms = list(dict.fromkeys(matched_terms))
        pdf_path = (Path(pdf_dir) / record["file_path"]).resolve()
        match_count = sum(
            sum(
                1
                for _ in compile_search_terms_pattern([term]).finditer(page_text)
            )
            for term in matched_terms
        )
        snippet = _build_snippet(page_text, matched_terms)
        matches.append(
            {
                "document": record["document"],
                "title": record["title"],
                "author": record.get("author") or "",
                "year": record.get("year"),
                "page": record["page"],
                "match_count": match_count,
                "matched_terms": matched_terms,
                "snippet": snippet,
                "path": str(pdf_path),
            }
        )

    matches.sort(
        key=lambda item: (item["document"].casefold(), item["page"])
    )
    return matches
