# Pretested Question Resource

## Local setup

Install the Python dependencies and configure the paths to your PDF collection
and generated search index:

```powershell
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

The six demo PDFs are bundled in `static/pdfs/` and used by default.
`DOCUMENTS_DIR` can optionally point to another PDF folder; relative paths are
resolved from the project root. `INDEX_PATH` is optional and defaults to
`.local-data/document_index.json`. `PDF_ACCESS_MODE=local` serves PDFs from a
loopback HTTP server for custom PDF folders. Bundled PDFs use Streamlit's
documented static route. Use local mode when the browser can access the machine
running the app.

To download the full Census working-paper collection, the default output is
`.local-data/pdfs/`, keeping downloaded files separate from the small,
publicly served demo corpus:

```powershell
python download_census_working_papers.py
# Or choose another destination:
python download_census_working_papers.py --output-dir "C:\data\working-papers"
```

To search that downloaded collection, either set
`DOCUMENTS_DIR=.local-data/pdfs` in `.env` and restart the app, or enter that
folder in the app's sidebar.

Run the app from the project root:

```powershell
streamlit run app.py
```

The checked-in Streamlit configuration enables Streamlit static-file serving
and reruns the app when source files are saved during development.

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

## Community Cloud demo

Community Cloud serves checked-in files from `static/` because
`enableStaticServing` is enabled in `.streamlit/config.toml`. Set
`PDF_ACCESS_MODE=public` in the app's secrets. For the bundled PDFs, the app
builds links using the Cloud route verified for this deployment:
`/~/+/app/static/pdfs/<filename>`. Streamlit's documented static URL form is
`/app/static/<filename>`; the additional prefix is specific to the Cloud route
we observed and should be retested if the deployment setup changes.

Do not use `PDF_ACCESS_MODE=local` for a hosted deployment: those links point
to loopback on the server, not to the user's computer.

## Future server deployment

For a standalone server with PDFs hosted separately, set
`PDF_ACCESS_MODE=public` and `PDF_BASE_URL` to the public HTTPS base URL where
the corresponding files are available. The app appends each PDF's path within
`DOCUMENTS_DIR` to that base URL. The PDFs must still be available in a local
folder to build the search index; `PDF_BASE_URL` only controls where the
browser opens the PDF. A CDN in front of an S3 bucket is a suitable future
option. The bucket or CDN must serve the PDFs to app users; private objects and
expiring signed URLs are not supported yet. Configure that access model when
the server deployment is planned rather than adding AWS-specific code to the
current local/Community Cloud demo.

When `PDF_ACCESS_MODE=public` and `PDF_BASE_URL` is unset, the Cloud static
route is only valid for the bundled `static/pdfs/` directory. The app reports
an error rather than generating misleading links if another PDF folder is
selected.
