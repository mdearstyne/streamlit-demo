# Pretested Question Resource

## Local setup

Install the Python dependencies and configure the paths to your PDF collection
and generated search index:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `DOCUMENTS_DIR` to the folder containing your PDFs. Relative
paths are resolved from the project root. `INDEX_PATH` is optional and defaults
to `.local-data/document_index.json`.

If you do not already have PDFs, download the Census working papers into the
configured documents folder:

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
quoted phrases. For example:

```text
survey AND (response OR "data collection") AND NOT phone
```

`NOT` is evaluated before `AND`, and `AND` before `OR`. Use double quotes when
searching for a phrase.

Search results include author and publication year when they can be identified.
Authors are taken first from a suggested citation, then PDF metadata, and
finally from plausible author lines following the title. Publication year is
taken from a report-issued date or, when that is unavailable, the report number.
Use the sort control to order results by matching pages, title, author, or
publication year.

The app creates or rebuilds the search index from the selected PDF folder.
Recognized title pages and tables of contents are omitted, as are pages from a
standalone References/Bibliography/Works Cited heading through the end of that
document. The index is rebuilt automatically when its format or exclusion rules
change.
Local PDFs, `.env`, and the generated index are ignored by Git; do not commit
large datasets or machine-specific paths.

## Server deployment

Set `DOCUMENTS_DIR` and optionally `INDEX_PATH` in the server environment to
locations available to the app process. Mount or download the PDFs into
`DOCUMENTS_DIR`, then build the index there or let the app create it. The
current PDF-opening behavior is designed for local use and should be adapted
to server-accessible PDF URLs before deploying the app publicly.
