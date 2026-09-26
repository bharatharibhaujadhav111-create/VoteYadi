"""Search Index Manager.

Responsibilities
----------------
* Keep ``meta.json`` (status, version, timestamps, per-PDF fingerprints).
* Run indexing jobs in the background with progress reporting.
* Incremental updates: only PDFs whose fingerprint changed are re-parsed;
  deleted PDFs have their shard removed; renamed PDFs have their shard renamed
  (no re-parse needed).
* Atomically swap the in-memory :class:`SearchIndex` so searches keep working
  while a rebuild is running.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from ..pdf_manager.pdf_parser import parse_pdf, pdf_page_count
from ..pdf_manager.pdf_store import PdfStore, fingerprint_for
from .index_store import SearchIndex, delete_shard, read_shard, rename_shard, write_shard

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IndexManager:
    def __init__(self, store: PdfStore, index_dir: Path | None = None) -> None:
        self.store = store
        self.index_dir = Path(index_dir or config.INDEX_DIR)
        self.shards_dir = self.index_dir / "shards"
        self.meta_path = self.index_dir / "meta.json"
        self.pickle_path = self.index_dir / "index.pkl"
        self.shards_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._job_lock = threading.Lock()
        self._index: SearchIndex = SearchIndex()
        self._meta = self._load_meta()
        self._progress = {"current": 0, "total": 0, "file": "", "started_at": None}
        self._pending_full = False
        self._pending_dirty: set[str] = set()
        self._memory_dirty = False  # shards changed without re-parsing (rename / delete)
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ meta
    def _load_meta(self) -> dict:
        default = {
            "version": 0,
            "status": "empty",  # empty | ready | indexing | error
            "last_indexed_at": None,
            "last_duration_sec": None,
            "error": None,
            "pdfs": {},  # name -> {fingerprint, records, pages, ocr_pages}
        }
        if self.meta_path.exists():
            try:
                default.update(json.loads(self.meta_path.read_text()))
            except Exception as exc:
                log.warning("meta.json unreadable (%s) – starting fresh", exc)
        if default["status"] == "indexing":  # crashed mid-run
            default["status"] = "ready" if default["pdfs"] else "empty"
        return default

    def _save_meta(self) -> None:
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._meta, indent=2))
        tmp.replace(self.meta_path)

    # ---------------------------------------------------------------- public
    @property
    def index(self) -> SearchIndex:
        return self._index

    def status(self) -> dict:
        with self._lock:
            total_records = len(self._index)
            prog = dict(self._progress)
            total = prog["total"] or 0
            pct = (prog["current"] / total * 100.0) if total else (100.0 if self._meta["status"] == "ready" else 0.0)
            return {
                "status": self._meta["status"],
                "version": self._meta["version"],
                "last_indexed_at": self._meta["last_indexed_at"],
                "last_duration_sec": self._meta["last_duration_sec"],
                "error": self._meta["error"],
                "total_pdfs": len(self.store.names()),
                "indexed_pdfs": len(self._meta["pdfs"]),
                "total_records": total_records,
                "total_villages": len(self.store.villages()),
                "village_counts": self._index.village_counts(),
                "ocr_available": _ocr_available(),
                "progress": {
                    "current": prog["current"],
                    "total": total,
                    "percent": round(pct, 1),
                    "file": prog["file"],
                    "files_done": prog.get("files_done", 0),
                    "files_total": prog.get("files_total", 0),
                    "started_at": prog["started_at"],
                },
            }

    def startup(self) -> None:
        """Load cached index, then reconcile with the PDF folder in the background."""
        cached = SearchIndex.load(self.pickle_path) if self.pickle_path.exists() else None
        if cached is not None:
            with self._lock:
                self._index = cached
            log.info("Loaded cached index: %d records", len(cached))
        else:
            self._rebuild_memory_index()
        self.schedule(full=False)

    def index_now(self, *, full: bool = False, timeout: float | None = None) -> None:
        """Run one indexing pass and *wait* for it (CLI tools and tests).

        The HTTP server always indexes in the background; a command-line run has
        nothing to do afterwards, so it needs a blocking entry point.
        """
        self.schedule(full=full)
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def schedule(self, *, full: bool = False, dirty: set[str] | None = None) -> None:
        """Request an indexing pass; coalesces with a running job."""
        with self._lock:
            if full:
                self._pending_full = True
            if dirty:
                self._pending_dirty.update(dirty)
            if self._thread and self._thread.is_alive():
                return  # running job will pick up pending work at the end
            self._thread = threading.Thread(target=self._run_loop, name="indexer", daemon=True)
            self._thread.start()

    def on_pdf_deleted(self, name: str) -> None:
        with self._lock:
            delete_shard(self.shards_dir, name)
            self._meta["pdfs"].pop(name, None)
            self._memory_dirty = True
        self.schedule(full=False)

    def on_pdf_renamed(self, old: str, new: str) -> None:
        with self._lock:
            if rename_shard(self.shards_dir, old, new):
                entry = self._meta["pdfs"].pop(old, None)
                if entry:
                    try:
                        entry["fingerprint"] = fingerprint_for(self.store.path_for(new))
                    except Exception:
                        pass
                    self._meta["pdfs"][new] = entry
                self._memory_dirty = True
        self.schedule(full=False)

    def on_pdf_uploaded(self, name: str) -> None:
        self.schedule(full=False, dirty={name})

    def on_village_renamed(self, old: str, new: str) -> None:
        """All PDFs under a village moved: rename shards, no re-parse needed."""
        with self._lock:
            for pdf_id in [p for p in self._meta["pdfs"] if p.startswith(old + "/")]:
                self.on_pdf_renamed(pdf_id, new + pdf_id[len(old):])
        self.schedule(full=False)

    def on_pdfs_deleted(self, names: list[str]) -> None:
        with self._lock:
            for n in names:
                delete_shard(self.shards_dir, n)
                self._meta["pdfs"].pop(n, None)
            self._memory_dirty = True
        self.schedule(full=False)

    # ----------------------------------------------------------- background
    def _run_loop(self) -> None:
        while True:
            with self._lock:
                full = self._pending_full
                self._pending_full = False
                self._pending_dirty.clear()
            try:
                self._run_job(full=full)
            except Exception as exc:  # pragma: no cover
                log.exception("Indexing failed")
                with self._lock:
                    self._meta["status"] = "error"
                    self._meta["error"] = str(exc)
                    self._save_meta()
            with self._lock:
                if not self._pending_full and not self._pending_dirty:
                    return

    def _plan(self, full: bool) -> tuple[list[str], list[str]]:
        """Return (to_parse, to_remove)."""
        current = {}
        for name in self.store.names():
            try:
                current[name] = fingerprint_for(self.store.path_for(name))
            except Exception:
                continue
        indexed = self._meta["pdfs"]
        to_remove = [n for n in indexed if n not in current]
        if full:
            to_parse = list(current)
        else:
            to_parse = [
                n for n, fp in current.items()
                if n not in indexed or indexed[n].get("fingerprint") != fp or read_shard(self.shards_dir, n) is None
            ]
        return to_parse, to_remove

    def _run_job(self, *, full: bool) -> None:
        with self._job_lock:
            started = time.time()
            to_parse, to_remove = self._plan(full)
            with self._lock:
                for n in to_remove:
                    delete_shard(self.shards_dir, n)
                    self._meta["pdfs"].pop(n, None)
                memory_dirty = self._memory_dirty or bool(to_remove)
                self._memory_dirty = False
            if not to_parse:
                if memory_dirty or (len(self._index) == 0 and self._meta["pdfs"]):
                    # shards changed (rename / move / delete) – recompose without re-parsing
                    self._rebuild_memory_index()
                    with self._lock:
                        self._meta["status"] = "ready" if self._meta["pdfs"] else "empty"
                        self._meta["version"] += 1
                        self._meta["last_indexed_at"] = _now_iso()
                        self._meta["last_duration_sec"] = round(time.time() - started, 2)
                        self._save_meta()
                    log.info("Index v%d recomposed: %d records", self._meta["version"], len(self._index))
                elif self._meta["status"] == "empty" and not self._meta["pdfs"]:
                    self._rebuild_memory_index()
                return

            with self._lock:
                self._meta["status"] = "indexing"
                self._meta["error"] = None
                self._progress = {"current": 0, "total": len(to_parse), "file": "", "started_at": _now_iso()}
                self._save_meta()

            log.info("Indexing %d PDFs (full=%s), removing %d", len(to_parse), full, len(to_remove))
            if to_parse:
                self._parse_many(to_parse)

            self._rebuild_memory_index()
            with self._lock:
                self._meta["status"] = "ready"
                self._meta["version"] += 1
                self._meta["last_indexed_at"] = _now_iso()
                self._meta["last_duration_sec"] = round(time.time() - started, 2)
                self._progress["file"] = ""
                self._save_meta()
            log.info("Index v%d ready: %d records in %.1fs", self._meta["version"], len(self._index), time.time() - started)

    def _parse_many(self, names: list[str]) -> None:
        """Parse PDFs one after another; pages inside each PDF are processed in
        parallel worker processes (OCR is CPU bound).  Progress is reported per
        page so the admin progress bar moves smoothly even for one huge PDF."""
        paths = {n: str(self.store.path_for(n)) for n in names}
        total_pages = 0
        for n in names:
            try:
                total_pages += pdf_page_count(paths[n])
            except Exception:
                pass
        with self._lock:
            self._progress["total"] = max(total_pages, 1)
            self._progress["current"] = 0
            self._progress["files_total"] = len(names)
            self._progress["files_done"] = 0

        done_before = 0
        failures: list[str] = []
        for name in names:
            with self._lock:
                self._progress["file"] = name
            base = done_before

            def _on_page(done: int, _total: int, base=base) -> None:
                with self._lock:
                    self._progress["current"] = base + done

            try:
                payload = parse_pdf(paths[name], workers=config.INDEX_WORKERS, progress=_on_page).to_dict()
                payload["pdf"] = name
                write_shard(self.shards_dir, name, payload)
                with self._lock:
                    self._meta["pdfs"][name] = {
                        "fingerprint": fingerprint_for(Path(payload["path"])),
                        "records": len(payload["records"]),
                        "pages": payload["pages"],
                        "ocr_pages": payload["ocr_pages"],
                        "indexed_at": _now_iso(),
                    }
                    self._save_meta()
                done_before += payload["pages"]
                log.info("Indexed %s: %d records (%d/%d pages OCR)", name, len(payload["records"]), payload["ocr_pages"], payload["pages"])
            except Exception as exc:
                log.warning("Failed to parse %s: %s", name, exc)
                failures.append(f"{name}: {exc}")
                try:
                    done_before += pdf_page_count(paths[name])
                except Exception:
                    pass
            with self._lock:
                self._progress["current"] = done_before
                self._progress["files_done"] = self._progress.get("files_done", 0) + 1
            # make freshly parsed PDFs searchable immediately, before the whole batch finishes
            self._rebuild_memory_index()
        if failures:
            raise RuntimeError("Indexing failed for " + "; ".join(failures))

    def _rebuild_memory_index(self) -> None:
        """Compose all shards into a fresh SearchIndex and swap it in."""
        names = [n for n in self.store.names() if n in self._meta["pdfs"]]

        def _iter():
            for n in names:
                payload = read_shard(self.shards_dir, n)
                if payload:
                    yield n, payload.get("records", [])

        new_index = SearchIndex.build(_iter())
        with self._lock:
            self._index = new_index
        try:
            new_index.save(self.pickle_path)
        except Exception as exc:  # pragma: no cover
            log.warning("Could not persist index cache: %s", exc)


def _ocr_available() -> bool:
    if not config.OCR_ENABLED:
        return False
    try:
        import pytesseract  # noqa

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
