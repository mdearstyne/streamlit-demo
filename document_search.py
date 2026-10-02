import json
import re
from pathlib import Path

import fitz

from data_config import DEFAULT_INDEX_PATH, DEFAULT_PDF_DIR

INDEX_VERSION = 2
_CONTENTS_HEADINGS = {"contents", "table of contents"}
_REFERENCE_HEADING = re.compile(
    r"^(?:(?:[a-z]-?)?\d+(?:\.\d+)*\s+)?"
    r"(?:references|bibliography|works cited)$",
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


def _evaluate_query(expression: tuple, text: str) -> tuple[bool, list[str]]:
    kind = expression[0]
    if kind == "TERM":
        term = expression[1]
        return term.casefold() in text.casefold(), [term]
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
        or bool(re.search(r"(?:\.{2,}|…{2,})\s*(?:[ivxlcdm]+|\d+)$", line, re.I))
        for line in lines
    )
    return contents_entries >= 3


def _find_excluded_pages(pdf_doc) -> set[int]:
    page_texts = [page.get_text("text") for page in pdf_doc]
    contents_pages = set()
    in_contents = False

    for page_number, text in enumerate(page_texts, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
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

    reference_start = None
    for page_number, text in enumerate(page_texts, start=1):
        if page_number in contents_pages:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if any(_REFERENCE_HEADING.fullmatch(line) for line in lines[:20]):
            reference_start = page_number
            break

    if reference_start is None:
        return contents_pages
    return contents_pages | set(
        range(reference_start, len(page_texts) + 1)
    )


def _extract_title(pdf_doc, fallback: str) -> str:
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

    lines = page.get_text("text").splitlines()
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


def _build_snippet(text: str, keywords: list[str], pad: int = 140) -> str:
    lowered = text.casefold()
    occurrences = [
        (lowered.find(keyword.casefold()), keyword)
        for keyword in keywords
        if keyword
    ]
    occurrences = [(start, keyword) for start, keyword in occurrences if start >= 0]
    if not occurrences:
        return _clean_text(text[:pad * 2])

    start, keyword = min(occurrences, key=lambda occurrence: occurrence[0])
    snippet_start = max(0, start - pad)
    snippet_end = min(len(text), start + len(keyword) + pad)
    snippet = text[snippet_start:snippet_end]
    return _clean_text(snippet)


def build_index(pdf_dir: str | Path = DEFAULT_PDF_DIR, output_path: str | Path = DEFAULT_INDEX_PATH):
    pdf_dir = Path(pdf_dir).expanduser().resolve()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF directory does not exist: {pdf_dir}")

    records = []
    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        try:
            pdf_doc = fitz.open(str(pdf_path))
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"Skipping unreadable PDF: {pdf_path} ({exc})")
            continue

        title = _extract_title(pdf_doc, pdf_path.name)
        excluded_pages = _find_excluded_pages(pdf_doc)
        for page_number, page in enumerate(pdf_doc, start=1):
            if page_number in excluded_pages:
                continue
            page_text = _clean_text(page.get_text("text"))
            if not page_text:
                continue
            records.append(
                {
                    "document": pdf_path.name,
                    "title": title,
                    "file_path": str(pdf_path.relative_to(pdf_dir)),
                    "index_version": INDEX_VERSION,
                    "page": page_number,
                    "text": page_text,
                }
            )

        pdf_doc.close()

    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def load_index(
    index_path: str | Path = DEFAULT_INDEX_PATH,
    pdf_dir: str | Path = DEFAULT_PDF_DIR,
):
    index_path = Path(index_path)
    if not index_path.exists():
        build_index(pdf_dir, index_path)

    with index_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if payload and any(
        record.get("index_version") != INDEX_VERSION for record in payload
    ):
        payload = build_index(pdf_dir, index_path)
    return payload


def find_keyword(
    query: str,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    limit: int = 20,
    pdf_dir: str | Path = DEFAULT_PDF_DIR,
):
    if not query.strip():
        return []
    expression = _parse_query(query)

    matches = []
    title_cache = {}
    for record in load_index(index_path, pdf_dir):
        page_text = record["text"]
        matched, matched_terms = _evaluate_query(expression, page_text)
        if not matched:
            continue

        matched_terms = list(dict.fromkeys(matched_terms))
        record_path = Path(record["file_path"])
        pdf_path = (
            record_path
            if record_path.is_absolute()
            else Path(pdf_dir) / record_path
        )
        pdf_path = pdf_path.resolve()
        title = record.get("title")
        if not title:
            file_path = str(pdf_path)
            if file_path not in title_cache:
                if pdf_path.exists():
                    with fitz.open(str(pdf_path)) as pdf_doc:
                        title_cache[file_path] = _extract_title(
                            pdf_doc, record["document"]
                        )
                else:
                    title_cache[file_path] = record["document"]
            title = title_cache[file_path]

        match_count = sum(
            page_text.casefold().count(term.casefold()) for term in matched_terms
        )
        snippet = _build_snippet(page_text, matched_terms)
        matches.append(
            {
                "document": record["document"],
                "title": title,
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
    return matches[:limit]
