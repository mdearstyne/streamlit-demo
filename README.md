# Pretested Question Resource

Explore PDF reports about questionnaire testing, find relevant passages, and ask
questions about findings across the available collection. The app currently uses
Census working papers, but it can search other PDFs containing selectable text.

## What you can do

| Tab | Use it to |
|---|---|
| **Search** | Find exact words or phrases and combine search conditions. |
| **Available documents** | See which reports are in the selected collection and open them. |
| **Ask the reports** | Ask a natural-language question and receive an AI-generated answer with supporting page links. Requires setup and internet access. |

The online demo may contain fewer reports than the full local collection. Check
**Available documents** to understand what the app can search and summarize.

## Search for words and phrases

Enter a search in **Search** and press Enter. Results are grouped by report.
Expand a report to see matching pages, highlighted excerpts, and a count of
matching terms. Select **Open PDF at page ...** to read the original context.

Search is case-insensitive and matches whole words: `SNAP` matches `SNAP`, but
not `SNAPCHAT`. For a phrase, use double quotes. To combine terms, use `AND`,
`OR`, and `NOT` explicitly:

| Example | Finds pages that contain |
|---|---|
| `SNAP` | The word SNAP. |
| `"food assistance"` | The phrase food assistance. |
| `SNAP AND benefits` | Both words on the same page. |
| `SNAP OR "food assistance"` | Either the word or the phrase. |
| `SNAP AND NOT phone` | SNAP, without phone on that page. |
| `survey AND (response OR "data collection")` | Survey and either of the two grouped alternatives. |

Conditions apply to individual pages. A report with one word on page 3 and
another on page 10 will not match an `AND` search requiring both. `NOT` excludes
matching pages, rather than entire reports. `NOT` takes priority over `AND`,
which takes priority over `OR`; parentheses make your intended grouping clear.

Results can be sorted by matching page count, title, author, or publication year
(newest or oldest first). Titles, authors, and dates are identified automatically
from the reports and may be missing or imperfect.

### What is included in a search?

Only PDFs directly inside the selected collection folder are searched;
subfolders are not included. The app searches selectable text. A scanned image
of a page needs text recognition (OCR) before it can be searched.

Recognized title pages, tables of contents, and reference sections are excluded.
Searching resumes when an appendix heading is recognized, so appendix
questionnaires and interview materials can be found. These rules use page
headings and are not perfect. Exclusion applies to whole pages, including any
other text sharing an excluded page. The same exclusions apply to AI questions.

## Browse the available documents

**Available documents** lists each PDF's title, author, year, filename, number of
searchable pages, and an **Open PDF** link. The list starts in alphabetical title
order. "Searchable pages" counts pages retained for search, not the PDF's total
length.

A PDF with no searchable pages is still listed and can be opened, but cannot
appear in search results or contribute evidence to AI answers. When there is no
indexed metadata, the filename serves as the title and other details show
"Not available".

## Open and read PDFs

PDFs open in a new browser tab using your browser's PDF viewer. Search-result
and AI citation links request a particular physical PDF page. Physical page
numbers can differ from the page labels printed inside the report.

Automatic page navigation and search highlighting depend on the viewer. Some
mobile viewers open at the beginning, and some viewers ignore the search hint.
Navigate to the displayed page number manually if needed, and use the viewer's
Find control (often **Ctrl+F**) to highlight terms. Search excerpts inside the
app are highlighted regardless of browser support. If PDFs download instead of
opening, check your browser's PDF-viewing settings.

Searching and viewing use the same stored files, without contacting Census for
PDF viewing. Once installed with its PDFs, the local app supports ordinary search
and PDF viewing without internet access. A deployed app still needs a connection
to its server. Downloading reports and asking AI questions require internet access.

## Ask questions about the reports

In **Ask the reports**, enter a question such as:

> What has previous testing found related to SNAP benefits?

Choose a mode and click **Ask the reports**:

| Mode | What happens | Spending limit per question |
|---|---|---|
| **Quick answer** | Finds a small set of relevant passages and produces one answer. | USD 0.10 |
| **Thorough review** | Searches related formulations, gathers evidence across reports, and combines findings into a broader answer. Takes longer. | USD 0.50 |

The answer includes links to supporting report pages, an explanation of its
limitations, the recorded API cost, and the number of reports represented in the
retrieved evidence. Expand **Source passages considered** to read the excerpts
supplied to the model. Answers remain visible during ordinary interactions in the
same session; changing the collection hides the previous answer.

### Understand the answer's limits

The model uses selected passages from the available collection, without external
web search. Neither mode guarantees that every relevant finding or every report
has been examined. Thorough review is broader retrieval, not an exhaustive
literature review. The displayed coverage describes passages retrieved, not proof
that every page in those reports was reviewed.

The app checks that citation identifiers refer to passages it supplied and
creates the PDF links itself. This does not prove that the passage supports the
model's interpretation. AI can make mistakes: read the evidence before using a
finding. An answer with missing or unrecognized citations is not displayed.
When evidence is insufficient, the model is instructed to say so.

Questions and selected report text are sent to OpenAI. Preparing the collection
also sends indexed report text to OpenAI. Use only collections approved for that
purpose. A separately billed OpenAI API key is needed; a ChatGPT subscription
does not cover the app's API usage. Without a key or prepared collection, the tab
shows setup guidance and ordinary search remains available.

### How preparation works

Before answering questions, the app creates **embeddings**: numerical
representations that help it find passages with similar meaning, even when their
wording differs. These are stored locally and reused. New or changed passages
need preparation; unchanged passages do not need to be processed again. Deleted
passages are no longer used for answers.

With administrator controls enabled, open **Ask the reports**, review the cost
estimate, and click **Prepare report questions**. Opening a tab or refreshing the
app does not initiate paid requests. Preparation has a separate cumulative
USD 1 limit, including later updates. The answer allowance is USD 2 per UTC day
across users sharing the same spending database.

## Manage a collection

The app checks the folder when it loads and when an interaction reruns it, such
as submitting a search or changing the sort. Added, removed, renamed, or edited
PDFs trigger a full rebuild of the saved search text, called the **index**.
Edits are detected by file size and modification time. Missing, damaged, or
outdated indexes are also rebuilt automatically.

There is no timed background check. After changing files, refresh or interact
with the app. **Rebuild index** forces a rebuild, including when an edit preserves
both size and modification time. If a PDF cannot be read or changes during a
rebuild, the app reports an error and preserves the previous index rather than
publishing incomplete results. AI preparation is separate from this rebuild.

An empty collection shows a setup message. A collection with PDFs but no
searchable text still has a catalogue, with guidance about OCR in the Search tab.

### Administrator controls

Set `ENABLE_ADMIN_CONTROLS=true` locally to show the sidebar's **PDF folder** and
**Rebuild index** controls, embedding preparation, and daily AI spending display.
The folder must be under the project's `static` directory for browser viewing.

These controls are an instance-wide setting, not an administrator login. Everyone
accessing that instance can use them. Leave the setting unset or `false` on a
public deployment. Automatic index updates continue when controls are hidden.
Restart the app after changing configuration.

## Install and run locally

The following Windows instructions use VS Code's terminal in the project folder.
You need Python installed. If the project already has a `.venv`, skip its creation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For a new setup, copy the example configuration. **Do not overwrite an existing
`.env`**, which may contain your settings and API key:

```powershell
Copy-Item .env.example .env
```

Keep `DOCUMENTS_DIR=static/pdfs` to use the full local collection. Put your PDFs
in that folder, or download Census working papers with:

```powershell
.\.venv\Scripts\python.exe download_census_working_papers.py
```

The downloader can use another destination with `--output-dir "static/other-papers"`.
It is a manual utility; the app does not automatically download missing reports.

Start the app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Ctrl+click the **Local URL** in the terminal. Keep the terminal running. Press
**Ctrl+C** to stop, then run the command again to restart. Saved Python edits
normally trigger automatic reruns; `.env` and Streamlit configuration changes
require a restart. If an old import error persists, restart and use the new
terminal's URL.

To enable AI questions, add your key as `OPENAI_API_KEY` in `.env`, restart, and
prepare the collection. Never share the value in screenshots, selected IDE
context, logs, or Git. `.gitignore` prevents Git tracking; it does not prevent an
IDE from sharing selected text in a conversation.

### Configuration reference

Relative paths are resolved from the project folder.

| Setting | Default or purpose |
|---|---|
| `DOCUMENTS_DIR` | `static/pdfs`: the selected PDF collection. |
| `INDEX_PATH` | `.local-data/document_index.json`: saved searchable page text; must be writable. |
| `ENABLE_ADMIN_CONTROLS` | Defaults to `false`; the example local configuration sets `true`. |
| `OPENAI_API_KEY` | Optional secret used for AI preparation and questions. |
| `AI_EMBEDDINGS_PATH` | `.local-data/embeddings.sqlite3`: saved passage embeddings. |
| `AI_SPENDING_PATH` | `.local-data/usage.sqlite3`: spending history; must be writable. |

## Deploy a demo or move to a server

### Community Cloud demo

The demo uses PDFs committed in `static/demo-pdfs` and prepared embeddings in
`demo-data/embeddings.sqlite3`. Your full collection in `static/pdfs`, local
`.env`, indexes, and spending history stay outside Git. The `.gitkeep` placeholder
keeps the full-collection folder present without committing its PDFs.

To export demo embeddings from your local prepared collection:

```powershell
.\.venv\Scripts\python.exe export_demo_embeddings.py
```

The utility copies only embeddings matching the demo PDFs, with no spending
records or paid API calls. It uses a separate demo search index and leaves your
local collection setting unchanged. If embeddings are missing, prepare the demo
passages first; no incomplete export is published. Regenerate the export when
the demo PDFs or passage-preparation rules change, then commit it with the PDFs.

In Community Cloud **Secrets**, enter these root-level settings using TOML syntax:

```toml
DOCUMENTS_DIR = "static/demo-pdfs"
AI_EMBEDDINGS_PATH = "demo-data/embeddings.sqlite3"
AI_SPENDING_PATH = ".local-data/usage.sqlite3"
ENABLE_ADMIN_CONTROLS = "false"
# Add OPENAI_API_KEY securely here if enabling AI questions.
```

Cloud reads the demo embeddings without modifying them during normal answering.
Secrets supplies deployment settings much like `.env` supplies local settings.
A path setting cannot give Cloud access to PDFs on your computer: files must be
included in the deployment or supplied separately.

**AI spending on Cloud needs care:** runtime files can disappear on restarts,
including the spending database. That resets the app's spending history. Keep
AI access restricted until persistent budget storage is arranged; the current
local ledger is not a durable deployment-wide billing cap.

### A conventional server

Copy the PDF collection into `static/pdfs`, or mount permanent server storage at
that path. A mount makes an external collection visible at the expected location
without storing a second copy. Keep `DOCUMENTS_DIR=static/pdfs`; no viewer-code
change is needed. Use persistent storage for both embeddings and spending history.
Independent app replicas need shared spending controls to enforce a common limit.

Everything under `static` can be accessed through file URLs. Keep API keys,
indexes, and databases outside that directory. Private documents need access
controls protecting PDF URLs as well as the app interface. Search exclusions
and Git ignore rules do not restrict document access. Committed demo embeddings
are derived from document content; publish them only for a public collection.

## Troubleshooting

| Message or behavior | What to do |
|---|---|
| No PDFs available | Supply PDFs in the configured collection folder. A placeholder alone is not a document collection. |
| No searchable text | Check for selectable text; scans may need OCR. Some pages are intentionally excluded. |
| AI collection needs preparation | An administrator should prepare new passages or supply the matching demo embedding database. |
| OpenAI rejects a request | Check the key, API billing, model access, and rate limits. Requests are not automatically retried. |
| Spending limit reached | Daily answer allowance resets on the next UTC day. The cumulative preparation allowance does not reset daily. |
| PDF opens at the beginning or without highlights | Use the page number and viewer's Find control; browser support varies. |
| Admin sidebar is missing | Enable the setting, restart, and check whether the sidebar is collapsed. |

Failed or interrupted API calls keep their reserved cost because their billing
status may be uncertain. Recorded spending therefore can exceed the eventual
provider charge. The app's cost controls use configured prices and conservative
request estimates; they are not provider-enforced guarantees.

<details>
<summary>Maintenance notes for developers</summary>

Answers use `gpt-4.1-mini-2025-04-14`; embeddings use `text-embedding-3-small`
with 256 dimensions. Indexed text is split into overlapping 1,500-character
passages, which may start or end mid-sentence. Quick answer retrieves up to ten
passages. Thorough review generates up to three alternate queries and selects
up to two passages per report, capped at 64 passages, before evidence extraction
and synthesis. No additional PDF extraction is performed for the catalogue or AI.

Spending reservations use SQLite transactions shared by sessions/processes using
the same ledger. Pricing constants and model choices are in `report_answers.py`;
review rates when changing models or when provider prices change. Embedding reads
use read-only connections; preparation needs a writable embedding database.

For an older combined AI database, stop the app and run:

```powershell
.\.venv\Scripts\python.exe migrate_ai_storage.py
```

This preserves embeddings, spending IDs, and pending reservations in separate
files while retaining the original database as a backup. Existing destinations
are not overwritten. `--source` or the retired `AI_DATA_PATH` setting selects a
legacy source. Restart before further paid requests. An existing legacy database
with no new ledger blocks paid requests until migration.

Main files:

- `app.py`: tabs, search interface, and document catalogue.
- `document_search.py`: query parsing, PDF text extraction, and index updates.
- `ui_helpers.py`: snippet highlighting and result sorting.
- `pdf_viewer.py`: browser PDF links and page/search hints.
- `answer_ui.py`: question interface and supporting evidence display.
- `report_answers.py`: retrieval, API requests, embedding storage, and spending.
- `data_config.py`: environment settings and path resolution.
- `download_census_working_papers.py`: optional report downloader.
- `export_demo_embeddings.py`: demo-only embedding export.
- `migrate_ai_storage.py`: legacy database migration.

Existing automated checks can be run with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

References: [Streamlit static file serving](https://docs.streamlit.io/develop/concepts/configuration/serving-static-files),
[OpenAI answer model](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
[embedding model](https://developers.openai.com/api/docs/models/text-embedding-3-small),
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

</details>
