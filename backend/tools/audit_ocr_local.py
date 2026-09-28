"""Read-only local OCR audit: page counts and serial anomalies, without voter names."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pdf_manager.pdf_parser import parse_pdf  # noqa: E402
from tools.sync_cloud import QualityError, validate, voter_rows  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--raw", action="store_true", help="Skip serial recovery and report first-pass OCR values")
    args = parser.parse_args()
    result = parse_pdf(args.pdf, workers=args.workers, recover_serials=not args.raw,
                       progress=lambda done, total: print(f"pages {done}/{total}", flush=True))
    by_page = defaultdict(list)
    for record in result.records:
        by_page[record.page].append(record.serial)
    seen = Counter()
    next_serial = 1
    for page, serials in sorted(by_page.items()):
        expected = set(range(next_serial, next_serial + len(serials)))
        try:
            actual = {int(value) for value in serials}
        except (ValueError, TypeError):
            actual = set()
        if actual != expected:
            print(f"page={page} count={len(serials)} expected={min(expected)}-{max(expected)} "
                  f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}", flush=True)
        seen.update(serials)
        next_serial += len(serials)
    print(f"RESULT pages={result.pages} records={len(result.records)} "
          f"duplicates={sum(count - 1 for count in seen.values() if count > 1)} "
          f"missing_serials={seen['']}", flush=True)
    try:
        report = validate(voter_rows({"village_id": "local-audit"}, result), result.pages, result.ocr_pages)
        print(f"QUALITY passed warnings={report['warnings']}", flush=True)
    except QualityError as exc:
        print(f"QUALITY needs_review: {exc}", flush=True)


if __name__ == "__main__":
    main()
