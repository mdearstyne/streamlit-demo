# Pretested Question Resource

## Local setup

Install the Python dependencies and configure the paths to your PDF collection
and generated search index:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `DOCUMENTS_DIR=static/pdfs` (the default). Store your PDFs
in that folder. You can select another folder inside `static`; relative paths
are resolved from the project root. `INDEX_PATH` is optional and defaults
to `.local-data/document_index.json`.

If you do not already have PDFs, download the Census working papers into the
configured documents folder:

```powershell
python download_census_working_papers.py
```

To use another destination for one download:

```powershell
python download_census_working_papers.py --output-dir "static/other-papers"
```

Run the app from the project root:

```powershell
streamlit run app.py
```

The checked-in Streamlit configuration enables reruns when Python source files
are saved, so edits to the app and its imported modules appear automatically.

Only PDFs directly inside the selected folder are indexed; subfolders are not
searched. Scanned PDFs need OCR first because the app searches selectable text.

The **Search** tab contains the search interface. **Available documents** is a
catalogue of the selected collection, with title, author, year, filename,
searchable page count, and a link to open each PDF. Titles are sorted
alphabetically. Metadata comes from the existing index; when a PDF has no indexed
pages, its filename is shown as the title and missing metadata is labelled
"Not available". These PDFs remain visible in the catalogue but cannot match
searches. No additional PDF extraction is performed for the catalogue.

Search supports explicit `AND`, `OR`, and `NOT` operators, parentheses, and
quoted phrases. Individual terms match whole words rather than substrings in
longer words, while punctuation acts as a word boundary. For example:

```text
survey AND (response OR "data collection") AND NOT phone
```

Queries are evaluated separately for each page. `survey AND response` requires
both words on the same page; `NOT phone` excludes pages containing `phone`, not
entire documents. A phrase must occur together on one page.

`NOT` is evaluated before `AND`, and `AND` before `OR`. Use double quotes when
searching for a phrase.

Search results include author and publication year when they can be identified.
Authors are taken first from a suggested citation, then PDF metadata, and
finally from plausible author lines following the title or a "Prepared by"
credit when PDF metadata only names the Census Bureau. Publication year is
taken from a report-issued date, a month/year on the cover, or the report
number. Use the sort control to order results by matching pages, title, author,
or publication year.

The app checks the selected PDF folder whenever Streamlit reruns (for example,
after a search or sort change). It automatically rebuilds the index when the
folder changes, a PDF is added/deleted, a file's size or modification time changes,
or the index is missing, damaged, or uses an older format. File changes alone do
not refresh an idle browser; interact with the app or use **Rebuild index**.
The manual button also handles edits that preserve both file size and timestamp.
It is available only when `ENABLE_ADMIN_CONTROLS=true`.

Recognized title pages and tables of contents are omitted. A standalone
References/Bibliography/Works Cited heading starts an excluded section;
indexing resumes at a recognized Appendix/Appendices heading near the top of a
later page. Appendix questionnaires and interview materials remain searchable.
These rules are heuristics; unusual headings may require adjusting the rules.
Exclusion is by whole page, so text sharing a references page is also excluded.

The JSON index stores its format version, source folder, PDF file manifest, and
page records. Rebuilding writes a temporary file next to the index and replaces
the old file only when the new index is complete. If a PDF cannot be read or
changes during indexing, the app shows an error and preserves the old index;
it does not serve stale results while that error remains unresolved.

Local PDFs, `.env`, and the generated index are ignored by Git; do not commit
large datasets or machine-specific paths.

## PDF viewing

Click **Open PDF at page ?** to open the PDF in a new browser tab at the matching
physical page (which may differ from its printed page label). The app creates a
normal PDF link with `#page=...` and a search hint for the first positive matching
term. Page navigation and automatic search highlighting depend on your browser's
PDF viewer. If the search hint is ignored, use the viewer's Find control; search
snippets in the app are always highlighted. If your browser downloads PDFs instead
of displaying them, enable its built-in PDF viewer to use page navigation.

Searching and viewing use the same files in `static/pdfs`. Streamlit's built-in
static file server exposes them at `app/static/pdfs/<filename>`. No external
Census links, embedded viewer package, or separate server port are needed.
Local use works without an internet connection after dependencies and PDFs are
installed. A deployed app needs a connection to its server, but viewing does
not depend on Census or another third-party website.

Everything inside `static` is accessible to visitors through a URL. Keep only
files intended for app users there; keep `.env`, indexes, and other private
files outside it. Streamlit currently limits each served file to 200 MB.

## Local and server deployment

Use the same layout in each environment:

```text
streamlit-demo/
  app.py
  static/
    pdfs/                    # The single PDF collection
  .local-data/
    document_index.json      # Generated index; not served to browsers
```

`DOCUMENTS_DIR=static/pdfs` selects the collection. `INDEX_PATH` defaults to
`.local-data/document_index.json` and must be writable. The sidebar can select
another collection under `static` when `ENABLE_ADMIN_CONTROLS=true`. Restart the app after changing `.env` or
Streamlit configuration. The checked-in `.streamlit/config.toml` enables static
file serving; start Streamlit from the project root so it reads that setting.

### Public deployment controls

`ENABLE_ADMIN_CONTROLS` defaults to `false`. The local `.env.example` enables
it for development, exposing the folder setting and manual rebuild button.
On a public deployment, leave it unset or set it to the string `"false"`.
Visitors then use the configured collection and cannot request manual rebuilds
or change the folder. Index freshness checks and automatic rebuilds still run.

For Community Cloud, use root-level Secrets entries such as:

```toml
DOCUMENTS_DIR = "static/pdfs"
ENABLE_ADMIN_CONTROLS = "false"
```

This setting controls the UI for the entire app; it does not authenticate an
administrator. Enable it only in an environment where all visitors are trusted.
Private collections require access controls that also protect the static PDF
URLs. Search exclusions and Git ignore rules do not restrict PDF access.

An empty folder shows a setup message before indexing or searching. A collection
with PDFs but no searchable pages shows a separate text-extraction message in
the Search tab; its catalogue remains available.

For a conventional server, copy the collection into `static/pdfs`, or mount a
persistent data volume there. For example, a server collection stored at
`/srv/census-pdfs` can be mounted at `<app-directory>/static/pdfs`. This stores
one copy of each PDF and keeps the app's filesystem layout and browser URLs
consistent. No Python changes are needed. A directory link is also possible:
link the entire `static` directory to a dedicated collection directory, then
set `DOCUMENTS_DIR=static`. Links to directories outside an existing `static`
root may be rejected by Streamlit's path checks; use a mount for `static/pdfs`.

For Streamlit Community Cloud, the PDFs must actually exist in the deployed
app's `static/pdfs` directory. Changing a path cannot give Cloud access to your
Windows disk. Choose one provisioning method:

- Include PDFs in the deployment repository if publishing them is appropriate.
  Remove `/static/pdfs/` from `.gitignore` deliberately for that deployment.
- Provision the collection into `static/pdfs` before using the app. Runtime
  files can disappear across restarts, so this provisioning must be repeatable.
  The current downloader is a manual command-line tool, not an automatic
  Cloud startup step.

The local collection and generated index are ignored by Git. Community Cloud
is therefore not ready to use this collection until you provision it. Its
runtime filesystem is not a substitute for permanent document storage. A server
with a mounted persistent collection is the straightforward option when keeping
files available without an external document service is required.

See [Streamlit static file serving](https://docs.streamlit.io/develop/concepts/configuration/serving-static-files).

To check browser viewing, search for a known term and open a matching page.
Repeat against the deployed app from another device. Check the page number and
Find behavior. You can disconnect your local machine from the internet and
repeat against the locally running app. Browser support for PDF page/search
fragments varies; visual page navigation needs a browser check.

## Code and checks

- `app.py`: Streamlit UI inside `main()` and cached search results.
- `document_search.py`: query parsing, PDF extraction, index validation, and search.
- `ui_helpers.py`: snippet highlighting and document sorting without UI execution.
- `pdf_viewer.py`: browser PDF links and page/search parameters.
- `data_config.py`: environment settings and project-relative paths.
- `download_census_working_papers.py`: optional Census PDF downloader.

Importing these modules does not render the UI or build an index. Page text is
extracted once per PDF and reused for metadata, exclusions, and index records.
Index JSON is cached by path, modification time, and size. Search results are
cached by query, selected folder, and indexed records, so changing the sort order
reuses the search and rebuilding with changed text invalidates it.

Run the checks from the project root:

```powershell
python -m pytest -q
```
