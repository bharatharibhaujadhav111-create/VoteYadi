"""PDF storage manager – the admin dashboard operates on the /pdfs folder only.

Layout::

    pdfs/
      villages.json              ordered list of villages shown in dropdowns
      <Village>/<file>.pdf       one sub-folder per village
      <file>.pdf                 (optional) PDFs not assigned to any village

A PDF is identified by its *relative path* ("Tirhe/Part_101.pdf").  Every
mutation returns the affected ids so the caller can trigger an incremental
index update.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from .. import config
from .pdf_parser import pdf_page_count

# Allow unicode letters (Devanagari village / file names), digits and a few symbols.
_SAFE_NAME = re.compile(r"[^\w \-.()\[\]&]+", re.UNICODE)
VILLAGES_FILE = "villages.json"
UNASSIGNED = ""  # village id for PDFs kept in the root folder


class PdfStoreError(Exception):
    """Raised for invalid operations (bad name, missing file, …)."""


@dataclass
class PdfInfo:
    id: str            # relative path, e.g. "Tirhe/Part_101.pdf"
    name: str          # file name only
    village: str       # "" when unassigned
    size: int
    pages: int
    uploaded_at: str   # ISO 8601
    modified_ts: float
    fingerprint: str   # size:mtime – cheap change detection used by the index

    def to_dict(self) -> dict:
        return asdict(self)


def sanitize_name(name: str) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    name = _SAFE_NAME.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        raise PdfStoreError("Invalid file name")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def sanitize_village(village: str) -> str:
    village = (village or "").replace("\\", "/").replace("/", " ").strip()
    village = _SAFE_NAME.sub("", village)
    village = re.sub(r"\s+", " ", village).strip(" .")
    if village.lower().endswith(".pdf") or village == VILLAGES_FILE:
        raise PdfStoreError("Invalid village name")
    return village


def fingerprint_for(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


def split_id(pdf_id: str) -> tuple[str, str]:
    pdf_id = (pdf_id or "").replace("\\", "/").strip("/")
    if "/" in pdf_id:
        village, name = pdf_id.split("/", 1)
        return sanitize_village(village), sanitize_name(name)
    return UNASSIGNED, sanitize_name(pdf_id)


def make_id(village: str, name: str) -> str:
    return f"{village}/{name}" if village else name


class PdfStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or config.PDF_DIR)
        self.root.mkdir(parents=True, exist_ok=True)
        self._page_cache: dict[str, tuple[str, int]] = {}

    # ----- villages --------------------------------------------------------
    def _villages_path(self) -> Path:
        return self.root / VILLAGES_FILE

    def villages(self) -> list[str]:
        """Ordered village list = villages.json ∪ existing sub-folders."""
        listed: list[str] = []
        p = self._villages_path()
        if p.exists():
            try:
                listed = [str(v) for v in json.loads(p.read_text(encoding="utf-8")) if str(v).strip()]
            except Exception:
                listed = []
        folders = sorted(d.name for d in self.root.iterdir() if d.is_dir() and not d.name.startswith("."))
        out: list[str] = []
        for v in listed + folders:
            if v not in out:
                out.append(v)
        return out

    def _save_villages(self, villages: list[str]) -> None:
        tmp = self._villages_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(villages, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._villages_path())

    def add_village(self, village: str) -> str:
        v = sanitize_village(village)
        if not v:
            raise PdfStoreError("Village name is required")
        villages = self.villages()
        if v not in villages:
            villages.append(v)
            self._save_villages(villages)
        (self.root / v).mkdir(parents=True, exist_ok=True)
        return v

    def rename_village(self, old: str, new: str) -> tuple[str, str]:
        old_v, new_v = sanitize_village(old), sanitize_village(new)
        if not old_v or not new_v:
            raise PdfStoreError("Village name is required")
        if old_v == new_v:
            return old_v, new_v
        if (self.root / new_v).exists():
            raise PdfStoreError(f"Village '{new_v}' already exists")
        if (self.root / old_v).exists():
            shutil.move(str(self.root / old_v), str(self.root / new_v))
        villages = [new_v if v == old_v else v for v in self.villages()]
        self._save_villages(villages)
        self._page_cache.clear()
        return old_v, new_v

    def delete_village(self, village: str) -> list[str]:
        """Delete a village and all its PDFs.  Returns removed pdf ids."""
        v = sanitize_village(village)
        if not v:
            raise PdfStoreError("Village name is required")
        removed = [i.id for i in self.list(village=v)]
        folder = self.root / v
        if folder.exists():
            shutil.rmtree(folder)
        self._save_villages([x for x in self.villages() if x != v])
        for r in removed:
            self._page_cache.pop(r, None)
        return removed

    # ----- helpers ---------------------------------------------------------
    def path_for(self, pdf_id: str) -> Path:
        village, name = split_id(pdf_id)
        path = (self.root / village / name).resolve() if village else (self.root / name).resolve()
        if self.root.resolve() not in path.parents:
            raise PdfStoreError("Invalid path")
        return path

    def id_for(self, path: Path) -> str:
        rel = path.resolve().relative_to(self.root.resolve())
        return rel.as_posix()

    def exists(self, pdf_id: str) -> bool:
        try:
            return self.path_for(pdf_id).is_file()
        except PdfStoreError:
            return False

    def _pages(self, pdf_id: str, path: Path) -> int:
        fp = fingerprint_for(path)
        cached = self._page_cache.get(pdf_id)
        if cached and cached[0] == fp:
            return cached[1]
        pages = pdf_page_count(path)
        self._page_cache[pdf_id] = (fp, pages)
        return pages

    def info(self, pdf_id: str) -> PdfInfo:
        path = self.path_for(pdf_id)
        if not path.is_file():
            raise PdfStoreError(f"PDF not found: {pdf_id}")
        st = path.stat()
        village, name = split_id(self.id_for(path))
        pid = make_id(village, name)
        return PdfInfo(
            id=pid,
            name=name,
            village=village,
            size=st.st_size,
            pages=self._pages(pid, path),
            uploaded_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            modified_ts=st.st_mtime,
            fingerprint=fingerprint_for(path),
        )

    # ----- queries ---------------------------------------------------------
    def _iter_paths(self, village: str | None = None):
        if village is None:
            yield from sorted(self.root.glob("*.pdf"), key=lambda x: x.name.lower())
            for d in sorted(self.root.iterdir(), key=lambda x: x.name.lower()):
                if d.is_dir() and not d.name.startswith("."):
                    yield from sorted(d.glob("*.pdf"), key=lambda x: x.name.lower())
        elif village == UNASSIGNED:
            yield from sorted(self.root.glob("*.pdf"), key=lambda x: x.name.lower())
        else:
            folder = self.root / sanitize_village(village)
            if folder.is_dir():
                yield from sorted(folder.glob("*.pdf"), key=lambda x: x.name.lower())

    def list(self, query: str = "", village: str | None = None) -> list[PdfInfo]:
        q = (query or "").lower().strip()
        items: list[PdfInfo] = []
        for p in self._iter_paths(village):
            if not p.is_file():
                continue
            pid = self.id_for(p)
            if q and q not in pid.lower():
                continue
            try:
                items.append(self.info(pid))
            except PdfStoreError:
                continue
        return items

    def names(self) -> list[str]:
        """All pdf ids (relative paths)."""
        return [self.id_for(p) for p in self._iter_paths() if p.is_file()]

    # ----- mutations -------------------------------------------------------
    def save_upload(self, filename: str, stream: BinaryIO, *, village: str = UNASSIGNED, replace: bool = False) -> PdfInfo:
        village = sanitize_village(village)
        if village:
            self.add_village(village)
        name = sanitize_name(filename)
        path = self.path_for(make_id(village, name))
        if path.exists() and not replace:
            stem, i = path.stem, 2
            while path.exists():
                path = path.with_name(f"{stem} ({i}).pdf")
                i += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".pdf.part")
        with open(tmp, "wb") as fh:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
        with open(tmp, "rb") as fh:
            head = fh.read(5)
        if head != b"%PDF-":
            tmp.unlink(missing_ok=True)
            raise PdfStoreError(f"{filename} is not a valid PDF file")
        os.replace(tmp, path)
        pid = self.id_for(path)
        self._page_cache.pop(pid, None)
        return self.info(pid)

    def delete(self, pdf_id: str) -> str:
        path = self.path_for(pdf_id)
        if not path.is_file():
            raise PdfStoreError(f"PDF not found: {pdf_id}")
        pid = self.id_for(path)
        path.unlink()
        self._page_cache.pop(pid, None)
        return pid

    def rename(self, pdf_id: str, new_name: str) -> tuple[str, str]:
        src = self.path_for(pdf_id)
        if not src.is_file():
            raise PdfStoreError(f"PDF not found: {pdf_id}")
        village, _ = split_id(self.id_for(src))
        dst = self.path_for(make_id(village, new_name))
        if dst.exists():
            raise PdfStoreError(f"A PDF named {dst.name} already exists in this village")
        shutil.move(str(src), str(dst))
        old_id, new_id = self.id_for(src), self.id_for(dst)
        self._page_cache.pop(old_id, None)
        return old_id, new_id

    def move(self, pdf_id: str, village: str) -> tuple[str, str]:
        """Move a PDF to another village folder."""
        src = self.path_for(pdf_id)
        if not src.is_file():
            raise PdfStoreError(f"PDF not found: {pdf_id}")
        village = sanitize_village(village)
        if village:
            self.add_village(village)
        dst = self.path_for(make_id(village, src.name))
        if dst.exists():
            raise PdfStoreError(f"A PDF named {src.name} already exists in that village")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        old_id, new_id = self.id_for(src), self.id_for(dst)
        self._page_cache.pop(old_id, None)
        return old_id, new_id
