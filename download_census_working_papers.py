import argparse
import re
from pathlib import Path

import requests

from data_config import DEFAULT_PDF_DIR

BASE_URL = "https://www.census.gov"
LIST_URL = (
    "https://www.census.gov/topics/research/behavior-science-methods/"
    "working-papers.html"
)
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def extract_paper_links(page_html: str) -> list[str]:
    href_pattern = re.compile(
        r'href=["\']([^"\']*rsm\d{4}-\d{2}\.html[^"\']*)["\']',
        re.IGNORECASE,
    )
    links = []
    for href in href_pattern.findall(page_html):
        href = href.strip()
        if href.startswith("http"):
            links.append(href)
        elif href.startswith("/"):
            links.append(BASE_URL + href)
    return list(dict.fromkeys(links))


def extract_pdf_link(detail_html: str) -> str | None:
    pdf_matches = re.findall(
        r'https?://[^"\s>]+\.pdf', detail_html, flags=re.IGNORECASE
    )
    for match in pdf_matches:
        if "working-papers" in match.lower() or "library" in match.lower():
            return match
    return None


def download_papers(output_dir: str | Path = DEFAULT_PDF_DIR) -> None:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    paper_links = extract_paper_links(fetch_text(LIST_URL))
    print(f"Found {len(paper_links)} paper detail URLs")

    for idx, paper_url in enumerate(paper_links, start=1):
        try:
            detail_html = fetch_text(paper_url)
            pdf_url = extract_pdf_link(detail_html)
            if not pdf_url:
                print(f"[{idx}] No PDF found for {paper_url}")
                continue
            filename = pdf_url.split("/")[-1]
            response = requests.get(pdf_url, headers=HEADERS, timeout=60)
            response.raise_for_status()
            target = output_dir / filename
            target.write_bytes(response.content)
            print(f"[{idx}] Downloaded {filename} ({len(response.content)} bytes)")
        except requests.RequestException as exc:
            print(f"[{idx}] FAILED {paper_url}: {exc}")

    print(f"Finished. Files in {output_dir}:")
    for pdf_path in sorted(output_dir.glob("*.pdf")):
        print(pdf_path.name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Census working paper PDFs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_PDF_DIR,
        help="Folder to save PDFs (defaults to DOCUMENTS_DIR or local data).",
    )
    args = parser.parse_args()
    download_papers(args.output_dir)


if __name__ == "__main__":
    main()
