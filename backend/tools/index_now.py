"""Build/refresh the search index from the command line (no server needed).

    python backend/tools/index_now.py            # incremental
    python backend/tools/index_now.py --full     # re-parse every PDF
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.pdf_manager.pdf_store import PdfStore  # noqa: E402
from app.search_index.index_manager import IndexManager  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--workers", type=int, default=0)
    args = ap.parse_args()
    if args.no_ocr:
        config.OCR_ENABLED = False
    if args.workers:
        config.INDEX_WORKERS = args.workers

    store = PdfStore()
    indexer = IndexManager(store)
    print(f"pdfs={config.PDF_DIR}  index={config.INDEX_DIR}")
    print(f"ocr={config.OCR_ENABLED}  ocr_lang={config.OCR_LANG}  "
          f"ocr_lang_dev={config.OCR_LANG_DEV}  auto={config.OCR_LANG_AUTO}")
    started = time.time()
    indexer.index_now(full=args.full)
    status = indexer.status()
    print(f"status={status['status']} v{status['version']} "
          f"pdfs={status['indexed_pdfs']}/{status['total_pdfs']} "
          f"records={status['total_records']} in {time.time() - started:.1f}s")
    for name, entry in sorted(indexer._meta["pdfs"].items()):  # noqa: SLF001 – CLI report
        print(f"  {name}: {entry.get('records', 0)} records, {entry.get('pages', 0)} pages, "
              f"{entry.get('ocr_pages', 0)} OCR'd")
    return 0 if status["status"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
