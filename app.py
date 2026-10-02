import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from document_search import DEFAULT_PDF_DIR, DEFAULT_INDEX_PATH, build_index, find_keyword

_PDF_SERVERS = {}


class QuietDirectoryHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Origin, X-Requested-With, Content-Type, Accept")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


class QuietTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def _get_or_create_pdf_server(pdf_dir: str | Path):
    pdf_dir = Path(pdf_dir).resolve()
    key = str(pdf_dir)
    server = _PDF_SERVERS.get(key)
    if server is not None:
        return f"http://127.0.0.1:{server.server_address[1]}", pdf_dir

    handler = functools.partial(QuietDirectoryHandler, directory=str(pdf_dir))
    server = QuietTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _PDF_SERVERS[key] = server
    return f"http://127.0.0.1:{server.server_address[1]}", pdf_dir


def build_browser_pdf_url(pdf_path: str | Path, page_number: int):
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        return None

    server_url, pdf_dir = _get_or_create_pdf_server(pdf_dir=pdf_path.parent)
    relative_path = pdf_path.relative_to(pdf_dir).as_posix()
    encoded_file = quote(server_url + "/" + relative_path, safe="")
    return f"https://mozilla.github.io/pdf.js/web/viewer.html?file={encoded_file}#page={page_number}"


def detect_pdf_viewer():
    local_app_data = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\zbtay\AppData\Local"))
    candidates = [
        ("SumatraPDF", [
            shutil.which("sumatrapdf.exe"),
            str(Path(r"C:\Program Files\SumatraPDF\SumatraPDF.exe")),
            str(Path(r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe")),
            str(local_app_data / "SumatraPDF" / "SumatraPDF.exe"),
        ]),
        ("Adobe Acrobat", [shutil.which("Acrobat.exe") or str(Path(r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe"))]),
        ("Adobe Reader", [shutil.which("AcroRd32.exe") or str(Path(r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe"))]),
        ("Foxit Reader", [shutil.which("FoxitPDFReader.exe") or str(Path(r"C:\Program Files\Foxit Software\Foxit PDF Reader\FoxitPDFReader.exe"))]),
    ]

    for name, probable_paths in candidates:
        for candidate in probable_paths:
            if candidate and os.path.exists(candidate):
                return name, candidate
    return "None detected", None


def open_pdf_at_page(pdf_path: str, page_number: int):
    pdf_path = str(pdf_path)
    if not os.path.exists(pdf_path):
        return False

    browser_url = build_browser_pdf_url(pdf_path, page_number)
    if browser_url:
        try:
            return bool(webbrowser.open_new_tab(browser_url))
        except Exception:
            pass

    viewer_name, viewer_path = detect_pdf_viewer()
    if viewer_path:
        viewer_commands = {
            "SumatraPDF": [
                viewer_path,
                "-new-window",
                "-page",
                str(page_number),
                pdf_path,
            ],
            "Adobe Acrobat": [viewer_path, "/A", f"page={page_number}", pdf_path],
            "Adobe Reader": [viewer_path, "/A", f"page={page_number}", pdf_path],
            "Foxit Reader": [viewer_path, "/A", f"page={page_number}", pdf_path],
        }
        command = viewer_commands.get(viewer_name)
        if command:
            try:
                subprocess.Popen(command, shell=False)
                return True
            except Exception:
                pass

    # Fallback for viewers that are available on PATH but not yet detected by the app.
    candidates = [
        ("Acrobat", "Acrobat.exe", ["/A", f"page={page_number}", pdf_path]),
        ("Acrobat Reader", "AcroRd32.exe", ["/A", f"page={page_number}", pdf_path]),
        (
            "SumatraPDF",
            "sumatrapdf.exe",
            [
                "-new-window",
                "-page",
                str(page_number),
                pdf_path,
            ],
        ),
        ("Foxit", "FoxitPDFReader.exe", ["/A", f"page={page_number}", pdf_path]),
    ]

    for _, exe_name, args in candidates:
        exe_path = shutil.which(exe_name)
        if exe_path:
            try:
                subprocess.Popen([exe_path] + args, shell=False)
                return True
            except Exception:
                continue

    try:
        os.startfile(pdf_path)
        return True
    except Exception:
        return False


st.set_page_config(page_title="Document Search", page_icon="📚", layout="wide")

st.title("Document repository search")
st.caption("Search local PDF working papers for keywords and open the matching file directly from the app.")

with st.sidebar:
    st.header("Settings")
    pdf_dir = st.text_input("PDF folder", value=str(DEFAULT_PDF_DIR))
    rebuild_index = st.button("Rebuild index")
    viewer_name, viewer_path = detect_pdf_viewer()
    if viewer_path:
        st.success(f"Browser PDF viewing enabled. Local viewer detected: {viewer_name}.")
    else:
        st.success("Browser PDF viewing enabled. Local app will open PDFs in a browser tab.")

pdf_dir_path = Path(pdf_dir)
index_path = DEFAULT_INDEX_PATH

if not pdf_dir_path.exists():
    st.error(f"The PDF folder does not exist: {pdf_dir_path}")
    st.stop()

if rebuild_index or not index_path.exists():
    with st.spinner("Indexing PDF files..."):
        build_index(pdf_dir_path, index_path)
    st.success(f"Indexed documents from {pdf_dir_path}")

query = st.text_input("Search keyword or phrase", value="survey response")
if query:
    results = find_keyword(query, index_path)
    if not results:
        st.info(f"No matches found for '{query}'.")
    else:
        st.write(f"Found {len(results)} matching results.")
        for idx, result in enumerate(results):
            st.markdown(f"### {result['document']} — Page {result['page']}")
            st.markdown(f"Match count: **{result['match_count']}**")
            st.write(result["snippet"])
            st.caption(f"File path: {result['path']}")

            if st.button(f"Open PDF at page {result['page']}", key=f"open_{idx}"):
                opened = open_pdf_at_page(result["path"], result["page"])
                if not opened:
                    st.error(f"Could not open the file automatically: {result['path']}")
            st.divider()
else:
    st.info("Enter a search term to begin.")
