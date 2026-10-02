import json
import re
from pathlib import Path

import fitz

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_PDF_DIR = Path(r"C:\Users\zbtay\census-working-papers")
DEFAULT_INDEX_PATH = ROOT_DIR / "document_index.json"


def normalize_query(query: str) -> str:
    return " ".join(str(query or "").strip().split()).lower()


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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


def _build_snippet(text: str, keyword: str, pad: int = 140) -> str:
    lowered = text.lower()
    kw = keyword.lower()
    start = lowered.find(kw)
    if start == -1:
        return _clean_text(text[:pad * 2])

    snippet_start = max(0, start - pad)
    snippet_end = min(len(text), start + len(keyword) + pad)
    snippet = text[snippet_start:snippet_end]
    return _clean_text(snippet)


def build_index(pdf_dir: str | Path = DEFAULT_PDF_DIR, output_path: str | Path = DEFAULT_INDEX_PATH):
    pdf_dir = Path(pdf_dir)
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
        for page_number, page in enumerate(pdf_doc, start=1):
            page_text = _clean_text(page.get_text("text"))
            if not page_text:
                continue
            records.append(
                {
                    "document": pdf_path.name,
                    "title": title,
                    "file_path": str(pdf_path),
                    "page": page_number,
                    "text": page_text,
                }
            )

        pdf_doc.close()

    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def load_index(index_path: str | Path = DEFAULT_INDEX_PATH):
    index_path = Path(index_path)
    if not index_path.exists():
        build_index(DEFAULT_PDF_DIR, index_path)

    with index_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload


def find_keyword(query: str, index_path: str | Path = DEFAULT_INDEX_PATH, limit: int = 20):
    keyword = normalize_query(query)
    if not keyword:
        return []

    matches = []
    title_cache = {}
    for record in load_index(index_path):
        page_text = record["text"]
        lowered_text = page_text.lower()
        if keyword not in lowered_text:
            continue

        title = record.get("title")
        if not title:
            file_path = record["file_path"]
            if file_path not in title_cache:
                pdf_path = Path(file_path)
                if pdf_path.exists():
                    with fitz.open(str(pdf_path)) as pdf_doc:
                        title_cache[file_path] = _extract_title(
                            pdf_doc, record["document"]
                        )
                else:
                    title_cache[file_path] = record["document"]
            title = title_cache[file_path]

        match_count = lowered_text.count(keyword)
        snippet = _build_snippet(page_text, keyword)
        matches.append(
            {
                "document": record["document"],
                "title": title,
                "page": record["page"],
                "match_count": match_count,
                "snippet": snippet,
                "path": record["file_path"],
            }
        )

    matches.sort(key=lambda item: (-item["match_count"], item["document"], item["page"]))
    return matches[:limit]
