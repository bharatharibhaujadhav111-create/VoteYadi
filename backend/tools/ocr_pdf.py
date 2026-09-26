"""Read one PDF the way the indexer does, and print what it sees.

    # true Marathi OCR of a scanned page (no text layer)
    python backend/tools/ocr_pdf.py pdfs/Marathi/roll.pdf --pages 1

    # whatever text layer / OCR the pipeline produces, plus the chosen language
    python backend/tools/ocr_pdf.py pdfs/Marathi/roll.pdf --auto

Useful for tuning: OCR language, DPI, and whether a page needs OCR at all.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from app import config  # noqa: E402
from app.core import marathi as mar  # noqa: E402
from app.pdf_manager import pdf_parser as pp  # noqa: E402


def parse_pages(spec: str, count: int) -> list[int]:
    if not spec:
        return list(range(min(count, 3)))
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a) - 1, int(b)))
        elif part:
            out.append(int(part) - 1)
    return [p for p in out if 0 <= p < count]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", default="", help="e.g. 1 or 2-4 (default: first 3)")
    ap.add_argument("--lang", default="", help="force an OCR language, e.g. mar or mar+eng")
    ap.add_argument("--dpi", type=int, default=0, help="override render DPI")
    ap.add_argument("--auto", action="store_true", help="print the pipeline output + detected script")
    ap.add_argument("--records", action="store_true", help="print parsed voter records")
    args = ap.parse_args()

    if args.dpi:
        config.OCR_DPI = args.dpi
    path = Path(args.pdf)
    if not path.exists():
        print(f"not found: {path}")
        return 1

    with pymupdf.open(path) as doc:
        pages = parse_pages(args.pages, doc.page_count)
        print(f"{path}  pages={doc.page_count}  reading {[p + 1 for p in pages]}")
        for i in pages:
            page = doc[i]
            lines = pp._page_lines(page)
            text = "\n".join(l[2] for l in lines)
            prof = mar.page_profile(text)
            print(f"\n================ page {i + 1} ================")
            print(f"text layer : {len(text.strip())} chars  script={prof['script']} "
                  f"(devanagari {prof['devanagari_ratio']:.0%})")
            needs_ocr = len(text.strip()) < config.OCR_MIN_TEXT_CHARS
            lang = args.lang or pp.ocr_language_for(text)
            print(f"ocr needed : {needs_ocr}   chosen language: {lang}")
            if needs_ocr or not args.auto:
                ocr_lines = pp._ocr_lines(page, lang=lang)
                otext = "\n".join(l[2] for l in ocr_lines)
                print(f"core OCR   : {len(otext.strip())} chars  "
                      f"script={mar.page_profile(otext)['script']}")
                print("--- OCR text ---")
                print(otext[:2500])
                lines = ocr_lines
            if args.auto:
                print("--- pipeline text ---")
                print(text[:2500])
            if args.records:
                result = pp.parse_page_text(pp.order_by_columns(lines), i + 1, "")
                print(f"--- {len(result.records)} records (part={result.part or '?'}) ---")
                for r in result.records:
                    print(f"  {r.serial or '-':>4} {r.name:<28} | {r.relation_type or '?':<7} "
                          f"{r.relation_name:<24} | part {r.part or '?':<3} | {r.epic}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
