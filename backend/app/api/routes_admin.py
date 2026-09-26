"""Admin dashboard endpoints – village + PDF management and index control."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from ..pdf_manager.pdf_store import PdfStoreError

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RenameBody(BaseModel):
    id: str
    new_name: str


class MoveBody(BaseModel):
    id: str
    village: str


class VillageBody(BaseModel):
    name: str


class VillageRenameBody(BaseModel):
    old_name: str
    new_name: str


def _store(request: Request):
    return request.app.state.store


def _indexer(request: Request):
    return request.app.state.indexer


def _wrap(fn):
    try:
        return fn()
    except PdfStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ------------------------------------------------------------------ villages
@router.get("/villages")
def list_villages(request: Request):
    store, indexer = _store(request), _indexer(request)
    counts = indexer.index.village_counts()
    pdf_counts: dict[str, int] = {}
    for pid in store.names():
        v = pid.split("/", 1)[0] if "/" in pid else ""
        pdf_counts[v] = pdf_counts.get(v, 0) + 1
    return {
        "villages": [
            {"name": v, "pdfs": pdf_counts.get(v, 0), "records": counts.get(v, 0)} for v in store.villages()
        ],
        "unassigned_pdfs": pdf_counts.get("", 0),
    }


@router.post("/villages")
def add_village(body: VillageBody, request: Request):
    name = _wrap(lambda: _store(request).add_village(body.name))
    return {"name": name}


@router.post("/villages/rename")
def rename_village(body: VillageRenameBody, request: Request):
    old, new = _wrap(lambda: _store(request).rename_village(body.old_name, body.new_name))
    _indexer(request).on_village_renamed(old, new)
    return {"old_name": old, "new_name": new}


@router.delete("/villages/{name}")
def delete_village(name: str, request: Request):
    removed = _wrap(lambda: _store(request).delete_village(name))
    _indexer(request).on_pdfs_deleted(removed)
    return {"deleted": name, "removed_pdfs": removed}


# ---------------------------------------------------------------------- pdfs
@router.get("/pdfs")
def list_pdfs(request: Request, q: str = Query("", max_length=200), village: str | None = Query(None)):
    store, indexer = _store(request), _indexer(request)
    meta = indexer.status()
    indexed = indexer._meta["pdfs"]  # noqa: SLF001 – read-only view
    items = []
    for info in store.list(q, village=village):
        d = info.to_dict()
        entry = indexed.get(info.id)
        d["indexed"] = entry is not None and entry.get("fingerprint") == info.fingerprint
        d["records"] = entry.get("records", 0) if entry else 0
        d["ocr_pages"] = entry.get("ocr_pages", 0) if entry else 0
        items.append(d)
    return {"pdfs": items, "index": meta}


@router.post("/pdfs/upload")
async def upload_pdfs(
    request: Request,
    files: list[UploadFile] = File(...),
    village: str = Form(""),
    replace: bool = Query(False),
):
    store, indexer = _store(request), _indexer(request)
    saved, errors = [], []
    for f in files:
        try:
            info = store.save_upload(f.filename or "upload.pdf", f.file, village=village, replace=replace)
            saved.append(info.to_dict())
            indexer.on_pdf_uploaded(info.id)
        except PdfStoreError as exc:
            errors.append({"file": f.filename, "error": str(exc)})
        finally:
            await f.close()
    if not saved and errors:
        raise HTTPException(status_code=400, detail=errors)
    return {"saved": saved, "errors": errors}


@router.post("/pdfs/replace")
async def replace_pdf(request: Request, id: str = Form(...), file: UploadFile = File(...)):
    store, indexer = _store(request), _indexer(request)
    if not store.exists(id):
        raise HTTPException(status_code=404, detail=f"PDF not found: {id}")
    try:
        info = store.info(id)
        info = store.save_upload(info.name, file.file, village=info.village, replace=True)
    except PdfStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()
    indexer.on_pdf_uploaded(info.id)
    return info.to_dict()


@router.delete("/pdfs")
def delete_pdf(request: Request, id: str = Query(...)):
    store, indexer = _store(request), _indexer(request)
    try:
        removed = store.delete(id)
    except PdfStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    indexer.on_pdf_deleted(removed)
    return {"deleted": removed}


@router.post("/pdfs/rename")
def rename_pdf(body: RenameBody, request: Request):
    old, new = _wrap(lambda: _store(request).rename(body.id, body.new_name))
    _indexer(request).on_pdf_renamed(old, new)
    return {"old_id": old, "new_id": new}


@router.post("/pdfs/move")
def move_pdf(body: MoveBody, request: Request):
    old, new = _wrap(lambda: _store(request).move(body.id, body.village))
    _indexer(request).on_pdf_renamed(old, new)
    return {"old_id": old, "new_id": new}


# --------------------------------------------------------------------- index
@router.get("/index/status")
def index_status(request: Request):
    return _indexer(request).status()


@router.post("/index/rebuild")
def rebuild_index(request: Request, full: bool = Query(True)):
    _indexer(request).schedule(full=full)
    return _indexer(request).status()
