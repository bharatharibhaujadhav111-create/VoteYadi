"""Voter Finder backend – FastAPI application factory.

Serves:
  /api/...         search + admin JSON API
  /pdf/...         PDF view / download
  /                compiled Flutter web app (user dashboard: "/", admin: "/super-admin")
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import routes_admin, routes_files, routes_search
from .pdf_manager.pdf_store import PdfStore
from .search_engine.engine import SearchEngine
from .search_index.index_manager import IndexManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voterfinder")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = PdfStore(config.PDF_DIR)
    indexer = IndexManager(store, config.INDEX_DIR)
    engine = SearchEngine(lambda: indexer.index)
    app.state.store = store
    app.state.indexer = indexer
    app.state.engine = engine
    indexer.startup()
    log.info("PDF dir: %s | index dir: %s | web dir: %s", config.PDF_DIR, config.INDEX_DIR, config.WEB_DIR)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Voter Finder API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _frame_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "ALLOWALL"
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
        return response

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # pragma: no cover
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(routes_search.router)
    app.include_router(routes_admin.router)
    app.include_router(routes_files.router)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    web_dir = Path(config.WEB_DIR)
    if web_dir.is_dir():
        index_html = web_dir / "index.html"

        # Static assets first, then SPA fallback so "/admin" deep links work.
        @app.get("/", include_in_schema=False)
        @app.get("/super-admin", include_in_schema=False)
        @app.get("/admin", include_in_schema=False)
        def spa_root():
            return FileResponse(index_html, headers={"Cache-Control": "no-cache"})

        app.mount("/", _SpaStaticFiles(directory=str(web_dir), html=True), name="web")
    else:
        log.warning("Web build not found at %s – run `flutter build web --release`", web_dir)

    return app


class _SpaStaticFiles(StaticFiles):
    """Static file server that falls back to index.html for unknown paths."""

    async def get_response(self, path, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except Exception:
            if "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


app = create_app()
