"""Application configuration.

All paths are resolved relative to the project root unless overridden with
environment variables.  PDFs are the *only* source of truth; the index folder
holds derived, searchable metadata that can be rebuilt at any time.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("VF_PROJECT_ROOT", Path(__file__).resolve().parents[2]))

# Folder that the admin dashboard manages.  Requirement: "/pdfs"
PDF_DIR = Path(os.environ.get("VF_PDF_DIR", PROJECT_ROOT / "pdfs"))

# Derived search index (safe to delete – it is rebuilt from PDFs)
INDEX_DIR = Path(os.environ.get("VF_INDEX_DIR", PROJECT_ROOT / "index"))

# Compiled Flutter web app that the backend serves at "/"
WEB_DIR = Path(os.environ.get("VF_WEB_DIR", PROJECT_ROOT / "build" / "web"))

HOST = os.environ.get("VF_HOST", "0.0.0.0")
PORT = int(os.environ.get("VF_PORT", "8000"))

# Indexing
INDEX_WORKERS = int(os.environ.get("VF_INDEX_WORKERS", str(max(1, min(4, (os.cpu_count() or 2))))))
OCR_ENABLED = os.environ.get("VF_OCR_ENABLED", "1") == "1"
OCR_MIN_TEXT_CHARS = int(os.environ.get("VF_OCR_MIN_TEXT_CHARS", "40"))  # below this, page is treated as scanned
OCR_DPI = int(os.environ.get("VF_OCR_DPI", "220"))  # upper bound
OCR_TARGET_WIDTH_PX = int(os.environ.get("VF_OCR_TARGET_WIDTH_PX", "2600"))  # rasterise pages to ~this width
OCR_PSM = int(os.environ.get("VF_OCR_PSM", "3"))  # tesseract page segmentation mode
OCR_LANG = os.environ.get("VF_OCR_LANG", "eng")          # language for Latin/English pages
OCR_LANG_DEV = os.environ.get("VF_OCR_LANG_DEV", "mar")   # language for Devanagari/Marathi pages
OCR_LANG_AUTO = os.environ.get("VF_OCR_LANG_AUTO", "1") == "1"  # pick per page from the script
OCR_LANG_BLEND = os.environ.get("VF_OCR_LANG_BLEND", "1") == "1"  # Marathi pages: "mar+eng"
TESSDATA_DIR = Path(os.environ.get("VF_TESSDATA_DIR", str(PROJECT_ROOT / "backend" / "tessdata")))
TESSERACT_CMD = os.environ.get("VF_TESSERACT_CMD", "")
TRANSLIT_DB = Path(os.environ.get("VF_TRANSLIT_DB", str(PROJECT_ROOT / "data" / "translit.sqlite")))

# Search
MAX_RESULTS = int(os.environ.get("VF_MAX_RESULTS", "500"))
FUZZY_VOCAB_LIMIT = int(os.environ.get("VF_FUZZY_VOCAB_LIMIT", "12"))  # candidate tokens per query token
FUZZY_SCORE_CUTOFF = int(os.environ.get("VF_FUZZY_SCORE_CUTOFF", "72"))

# AI query parser (OpenAI-compatible endpoint).  Optional – rule based fallback always exists.
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("VF_LLM_MODEL", "gpt-5.4-mini")
LLM_TIMEOUT = float(os.environ.get("VF_LLM_TIMEOUT", "6"))
LLM_ENABLED = os.environ.get("VF_LLM_ENABLED", "1") == "1"


def _load_llm_config_from_yaml() -> None:
    """Sandbox convenience: read ~/.genspark_llm.yaml if env vars are absent."""
    global LLM_API_KEY, LLM_BASE_URL
    if LLM_API_KEY:
        return
    cfg = Path.home() / ".genspark_llm.yaml"
    if not cfg.exists():
        return
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(cfg.read_text()) or {}
        openai_cfg = data.get("openai", {})
        LLM_API_KEY = openai_cfg.get("api_key", "") or LLM_API_KEY
        LLM_BASE_URL = openai_cfg.get("base_url", "") or LLM_BASE_URL
    except Exception:  # pragma: no cover - best effort only
        pass


_load_llm_config_from_yaml()

for _d in (PDF_DIR, INDEX_DIR):
    _d.mkdir(parents=True, exist_ok=True)
