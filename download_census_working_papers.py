import re
from pathlib import Path

import requests

BASE_URL = 'https://www.census.gov'
LIST_URL = 'https://www.census.gov/topics/research/behavior-science-methods/working-papers.html'
OUT_DIR = Path(r'C:\Users\zbtay\census-working-papers')
OUT_DIR.mkdir(parents=True, exist_ok=True)

headers = {'User-Agent': 'Mozilla/5.0'}


def fetch_text(url):
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def extract_paper_links(page_html):
    href_pattern = re.compile(r'href=["\']([^"\']*rsm\d{4}-\d{2}\.html[^"\']*)["\']', re.IGNORECASE)
    links = []
    for match in href_pattern.findall(page_html):
        href = match.strip()
        if href.startswith('http'):
            links.append(href)
        elif href.startswith('/'):
            links.append(BASE_URL + href)
    unique = []
    seen = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def extract_pdf_link(detail_html):
    pdf_matches = re.findall(r'https?://[^"\s>]+\.pdf', detail_html, flags=re.IGNORECASE)
    for match in pdf_matches:
        if 'working-papers' in match.lower() or 'library' in match.lower():
            return match
    return None


list_html = fetch_text(LIST_URL)
paper_links = extract_paper_links(list_html)
print(f'Found {len(paper_links)} paper detail URLs')

for idx, paper_url in enumerate(paper_links, start=1):
    try:
        detail_html = fetch_text(paper_url)
        pdf_url = extract_pdf_link(detail_html)
        if not pdf_url:
            print(f'[{idx}] No PDF found for {paper_url}')
            continue
        filename = pdf_url.split('/')[-1]
        target = OUT_DIR / filename
        response = requests.get(pdf_url, headers=headers, timeout=60)
        response.raise_for_status()
        target.write_bytes(response.content)
        print(f'[{idx}] Downloaded {filename} ({len(response.content)} bytes)')
    except Exception as exc:
        print(f'[{idx}] FAILED {paper_url}: {exc}')

print(f'Finished. Files in {OUT_DIR}:')
for f in sorted(OUT_DIR.iterdir()):
    print(f.name)
