# Document repository search

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

The app creates or rebuilds the search index from the selected PDF folder.
Local PDFs, `.env`, and the generated index are ignored by Git; do not commit
large datasets or machine-specific paths.

## Server deployment

Set `DOCUMENTS_DIR` and optionally `INDEX_PATH` in the server environment to
locations available to the app process. Mount or download the PDFs into
`DOCUMENTS_DIR`, then build the index there or let the app create it. The
current PDF-opening behavior is designed for local use and should be adapted
to server-accessible PDF URLs before deploying the app publicly.
