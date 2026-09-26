"""PDF viewing / downloading endpoints (PDF Viewer module backend)."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..pdf_manager.pdf_store import PdfStoreError

router = APIRouter(prefix="/pdf", tags=["files"])


def _resolve(request: Request, name: str):
    store = request.app.state.store
    try:
        path = store.path_for(name)
    except PdfStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"PDF not found: {name}")
    return path


@router.get("/view/{name:path}")
def view_pdf(name: str, request: Request):
    """Inline display – browsers honour ``#page=N`` in the URL fragment."""
    path = _resolve(request, name)
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(path.name)}",
            "Cache-Control": "public, max-age=3600",
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/download/{name:path}")
def download_pdf(name: str, request: Request):
    path = _resolve(request, name)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )
