import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

LOCAL_DATA_DIR = ROOT_DIR / ".local-data"


def _configured_path(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    path = Path(value).expanduser() if value else default
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


DEFAULT_PDF_DIR = _configured_path(
    "DOCUMENTS_DIR", LOCAL_DATA_DIR / "pdfs"
)
DEFAULT_INDEX_PATH = _configured_path(
    "INDEX_PATH", LOCAL_DATA_DIR / "document_index.json"
)
