"""Unit checks for the cloud OCR publication quality gate."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.tools.sync_cloud import QualityError, validate  # noqa: E402


def rows(count: int, *, marathi: bool = True, serials: bool = True) -> list[dict]:
    return [
        {
            "name": f"मतदार नाव {i}" if marathi else f"Voter Name {i}",
            "name_normalized": f"मतदार नाव {i}" if marathi else f"voter name {i}",
            "relation_name_normalized": f"नातेवाईक {i}",
            "serial": str(i + 1) if serials else "",
            "epic": f"ZCG{i:07d}",
            "page": i // 20 + 1,
        }
        for i in range(count)
    ]


good = validate(rows(100), pages=5, ocr_pages=5)
assert good["status"] == "passed"
assert good["records"] == 100

for bad_rows, pages, reason in [
    (rows(5), 20, "too few records"),
    (rows(100, marathi=False), 5, "non-Marathi output"),
    (rows(100, serials=False), 5, "missing serials"),
]:
    try:
        validate(bad_rows, pages=pages, ocr_pages=pages)
    except QualityError:
        pass
    else:
        raise AssertionError(f"Quality gate accepted {reason}")

print("PASS: cloud OCR quality gate")
