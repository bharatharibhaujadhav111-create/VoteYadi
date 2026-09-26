"""Public (user dashboard) endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..ai_parser.marathi_parser import parse_query
from ..core import devanagari as dev

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(
    request: Request,
    q: str = Query("", max_length=300),
    village: str = Query("", max_length=120, description="Restrict search to one village's PDFs"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ai: bool = Query(True, description="Allow the AI parser for conversational queries"),
):
    engine = request.app.state.engine
    parsed = parse_query(q, allow_llm=ai)
    parsed.village = village.strip()
    result = engine.search(parsed, page=page, page_size=page_size).to_dict()
    # Echo how the sentence was understood – the user dashboard shows this so a
    # Marathi query ("वडिलांचे नाव …") is visibly split into name + relative.
    result["parsed"] = {
        "name": parsed.name,
        "name_dev": dev.to_roman_text(parsed.name) if dev.has_devanagari(parsed.name) else "",
        "relation_name": parsed.relation_name,
        "relation_type": parsed.relation_type,
        "part": parsed.part,
        "any_text": parsed.any_text,
        "source": parsed.source,
        "notes": list(parsed.notes),
        "is_marathi": parsed.name != "" and dev.has_devanagari(parsed.name + parsed.relation_name),
    }
    return result


@router.get("/suggest")
def suggest(
    request: Request,
    q: str = Query("", max_length=120),
    village: str = Query("", max_length=120),
    limit: int = Query(8, ge=1, le=20),
):
    engine = request.app.state.engine
    items = engine.suggest(q, limit=limit, village=village.strip())
    return {"suggestions": [i["text"] for i in items], "items": items}


@router.get("/parse")
def parse(q: str = Query("", max_length=300), ai: bool = True):
    """Debug helper: show how a query is interpreted (no search performed)."""
    return parse_query(q, allow_llm=ai).to_dict()


@router.get("/villages")
def villages(request: Request):
    """Village list for the user dashboard dropdown (with record counts)."""
    store = request.app.state.store
    counts = request.app.state.indexer.index.village_counts()
    return {"villages": [{"name": v, "records": counts.get(v, 0)} for v in store.villages()]}


@router.get("/stats")
def stats(request: Request):
    s = request.app.state.indexer.status()
    return {
        "total_pdfs": s["total_pdfs"],
        "total_records": s["total_records"],
        "total_villages": s["total_villages"],
        "index_status": s["status"],
        "index_version": s["version"],
        "last_indexed_at": s["last_indexed_at"],
    }


@router.get("/ocr-status")
def ocr_status(request: Request):
    """Marathi OCR / cross-script index health (shown on the admin dashboard)."""
    from .. import config
    from ..pdf_manager.pdf_parser import _ocr_tesseract_version  # noqa: SLF001
    from ..pdf_manager import pdf_parser as pp

    indexer = request.app.state.indexer
    idx = indexer.index
    try:
        version = _ocr_tesseract_version()
    except Exception:
        version = ""
    dev_records = 0
    if getattr(idx, "rec_name_script", None):
        dev_records = sum(1 for s in idx.rec_name_script if s == "devanagari")
    return {
        "ocr_enabled": config.OCR_ENABLED,
        "ocr_lang": config.OCR_LANG,
        "ocr_lang_dev": config.OCR_LANG_DEV,
        "ocr_lang_auto": config.OCR_LANG_AUTO,
        "ocr_lang_blend": config.OCR_LANG_BLEND,
        "tessdata_dir": str(config.TESSDATA_DIR),
        "tesseract": version,
        "index_format": __import__("app.search_index.index_store", fromlist=["INDEX_FORMAT"]).INDEX_FORMAT,
        "records": len(idx),
        "devanagari_records": dev_records,
        "alias_tokens": len(getattr(idx, "alias_tokens", {}) or {}),
        "sample_languages": {
            "marathi_page": pp.ocr_language_for("नाव : रामचंद्र जाधव ओळखपत्र ZCG1234567"),
            "english_page": pp.ocr_language_for("Name : Vinayshree Bharat Jadhav"),
        },
    }
