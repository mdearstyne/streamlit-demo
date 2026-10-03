# Pretested Question Resource

## Local setup

Install the Python dependencies and configure the paths to your PDF collection
and generated search index:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

The demo PDFs are bundled in `static/pdfs/` and are used by default.
`DOCUMENTS_DIR` can optionally point to another PDF folder; relative paths are
resolved from the project root. `INDEX_PATH` is optional and defaults to
`.local-data/document_index.json`. `PDF_ACCESS_MODE=local` serves PDFs from the
machine running the app for browser viewing during local development. This
works when opening Streamlit from that same machine.

For hosted deployment, set `PDF_ACCESS_MODE=public` in Streamlit Community
Cloud's app secrets. With the bundled PDFs, the app automatically uses its
`/app/static/pdfs/` URL. To use PDFs hosted elsewhere, also set `PDF_BASE_URL`
to their public HTTP(S) base URL. That host must allow cross-origin requests
from users' browsers so PDF.js can load the files.

To download the full Census working-paper collection into a custom documents
folder:

```powershell
python download_census_working_papers.py
```

To use another destination for one download:

```powershell
python download_census_working_papers.py --output-dir "C:\data\working-papers"
```

Run the app from the project root:

```powershell
streamlit run app.py
```

The checked-in Streamlit configuration enables reruns when Python source files
are saved, so edits to the app and its imported modules appear automatically.

Search supports explicit `AND`, `OR`, and `NOT` operators, parentheses, and
quoted phrases. Individual search terms match whole words, not substrings
inside longer words. For example:

```text
survey AND (response OR "data collection") AND NOT phone
```

`NOT` is evaluated before `AND`, and `AND` before `OR`. Use double quotes when
searching for a phrase.

Search results prefer author names from a suggested citation, then use PDF
metadata or first-page author lines as fallbacks. Publication year is taken
from a first-page issue date or report number. Use the document sort control to
order results by matching page count (the default), title, author, or
publication year. All matching pages are displayed together.

The app creates or rebuilds the search index from the selected PDF folder.
Identified title pages, pages headed Abstract or Contents (including detected
contents continuations), and pages from a standalone References/Bibliography/
Works Cited heading through the end of that document are omitted from search.
The index is rebuilt automatically when its format or exclusion rules change.
Local PDFs, `.env`, and the generated index are ignored by Git; do not commit
large datasets or machine-specific paths.

## Server deployment

Community Cloud serves bundled PDFs from `static/pdfs/` because static serving
is enabled in `.streamlit/config.toml`. Set `PDF_ACCESS_MODE=public` in the
app's secrets; bundled PDF links then use the deployed app's own URL. If using
an alternate document folder, ensure the files are also reachable at the
configured `PDF_BASE_URL`. Do not use local mode for a hosted deployment: its
PDF links point to the server's loopback interface.
