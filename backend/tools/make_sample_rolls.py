"""Generate synthetic *Marathi* electoral-roll PDFs for testing the pipeline.

    python backend/tools/make_sample_rolls.py --out pdfs/Marathi

Two variants are produced, exactly like the real thing:

``…-text.pdf``     a real Devanagari text layer (the "digital" roll),
``…-scanned.pdf``  the same page rasterised to an image (the "scanned" roll that
                   has to go through Marathi OCR).

The data is fabricated – village/constituency names are placeholders – so it is
safe to commit and index.  Only used to prove that Marathi OCR, parsing and
indexing work end to end.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import pymupdf
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

DEV_FONTS = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
]

# (name, relation word, relation name, house, age, gender, epic)
PEOPLE = [
    ("रामचंद्र भरत जाधव", "वडिलांचे नाव", "भरत जाधव", "12", "45", "पुरुष", "ZCG1000001"),
    ("सुनील दत्तात्रय पाटील", "वडिलांचे नाव", "दत्तात्रय पाटील", "27", "38", "पुरुष", "ZCG1000002"),
    ("शारदा रामचंद्र जाधव", "पतीचे नाव", "रामचंद्र जाधव", "12", "41", "स्त्री", "ZCG1000003"),
    ("गणेश दशरथ मोरे", "वडिलांचे नाव", "दशरथ मोरे", "5", "34", "पुरुष", "ZCG1000004"),
    ("विजयसिंह भरत जाधव", "वडिलांचे नाव", "भरत जाधव", "31", "52", "पुरुष", "ZCG1000005"),
    ("वसंत कृष्णा काळे", "वडिलांचे नाव", "कृष्णा काळे", "9", "60", "पुरुष", "ZCG1000006"),
    ("अनिता सुनील पाटील", "पतीचे नाव", "सुनील पाटील", "27", "36", "स्त्री", "ZCG1000007"),
    ("भरत रामचंद्र जाधव", "वडिलांचे नाव", "रामचंद्र जाधव", "12", "28", "पुरुष", "ZCG1000008"),
    ("प्रणिती सुशीलकुमार शिंदे", "पतीचे नाव", "सुशीलकुमार शिंदे", "44", "30", "स्त्री", "ZCG1000009"),
]
# Same people, but no i-matra (ि) so a naive rasteriser still renders the
# conjuncts in reading order – used for the *scanned* variant whose OCR result
# is compared against the original text.
SCANNED_PEOPLE = [
    ("रामचंद्र भरत जाधव", "वडिलांचे नाव", "भरत जाधव", "12", "45", "पुरुष", "ZCG2000001"),
    ("सुनील दत्तात्रय पाटील", "वडिलांचे नाव", "दत्तात्रय पाटील", "27", "38", "पुरुष", "ZCG2000002"),
    ("गणेश दशरथ मोरे", "वडिलांचे नाव", "दशरथ मोरे", "5", "34", "पुरुष", "ZCG2000003"),
    ("वसंत कृष्णा काळे", "वडिलांचे नाव", "कृष्णा काळे", "9", "60", "पुरुष", "ZCG2000004"),
    ("शारदा रामचंद्र जाधव", "पतीचे नाव", "रामचंद्र जाधव", "12", "41", "स्त्री", "ZCG2000005"),
    ("अनिता सुनील पाटील", "पतीचे नाव", "सुनील पाटील", "27", "36", "स्त्री", "ZCG2000006"),
    ("संजय बाळू गायकवाड", "वडिलांचे नाव", "बाळू गायकवाड", "18", "49", "पुरुष", "ZCG2000007"),
    ("मनोहर पांडुरंग देशमुख", "वडिलांचे नाव", "पांडुरंग देशमुख", "22", "57", "पुरुष", "ZCG2000008"),
    ("भरत रामचंद्र जाधव", "वडिलांचे नाव", "रामचंद्र जाधव", "12", "28", "पुरुष", "ZCG2000009"),
]
HEADER = {
    "ac": "विधानसभा मतदारसंघ क्रमांक व नाव : 79-धुळे शहर",
    "part": "भाग क्रमांक : 1        विभाग क्रमांक : 1-नमुना विभाग",
    "note": "नमुना मतदार यादी – प्रारूप (Draft Electoral Roll) – केवळ चाचणीसाठी",
}
COLUMNS = 3
PER_PAGE = 9


def register_dev_font() -> str:
    for path in DEV_FONTS:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("Devanagari", path))
            return "Devanagari"
    raise SystemExit(
        "No Devanagari TTF found. Install one with:\n"
        "  sudo apt-get install fonts-noto-core"
    )


def draw_roll(path: Path, people: list[tuple[str, ...]], font: str) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    for page_start in range(0, len(people), PER_PAGE):
        chunk = people[page_start:page_start + PER_PAGE]
        c.setFont(font, 10)
        c.drawString(30, height - 30, HEADER["ac"])
        c.drawString(30, height - 44, HEADER["part"])
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(30, height - 58, "Sample / test data only - not an official roll")
        box_w = (width - 60) / COLUMNS
        for i, person in enumerate(chunk):
            name, rel_label, rel_name, house, age, gender, epic = person
            col, row = i % COLUMNS, i // COLUMNS
            x = 30 + col * box_w
            top = height - 90 - row * 150
            c.setLineWidth(0.4)
            c.rect(x, top - 130, box_w - 6, 132, stroke=1, fill=0)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(x + 10, top - 10, str(i + 1))
            c.setFont("Helvetica", 8)
            c.drawString(x + 60, top - 10, epic)
            c.setFont(font, 11)
            c.drawString(x + 10, top - 34, f"नाव : {name}")
            c.drawString(x + 10, top - 52, f"{rel_label} : {rel_name}")
            c.drawString(x + 10, top - 74, f"घर क्रमांक : {house}")
            c.drawString(x + 10, top - 92, f"वय : {age}")
            c.drawString(x + 80, top - 92, f"लिंग : {gender}")
            c.setFont("Helvetica", 8)
            c.drawString(x + 10, top - 116, "Photo available")
        c.showPage()
    c.save()


def rasterise(src: Path, dest: Path, dpi: int = 300) -> None:
    """Turn a text PDF into an image-only PDF: the 'scanned roll' case."""
    out = pymupdf.open()
    with pymupdf.open(src) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            new_page = out.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=pix.tobytes("png"))
    out.save(str(dest), deflate=True)
    out.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="pdfs/Marathi", help="output folder")
    ap.add_argument("--dpi", type=int, default=300, help="scan resolution")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    font = register_dev_font()

    text_pdf = out_dir / "SAMPLE-DHULE-79-Marathi-Roll-1-text.pdf"
    scan_src = out_dir / "_scan_source.pdf"
    scan_pdf = out_dir / "SAMPLE-DHULE-79-Marathi-Roll-2-scanned.pdf"

    draw_roll(text_pdf, PEOPLE, font)
    draw_roll(scan_src, SCANNED_PEOPLE, font)
    rasterise(scan_src, scan_pdf, dpi=args.dpi)
    scan_src.unlink(missing_ok=True)

    print(f"wrote {text_pdf}  ({len(PEOPLE)} records, real text layer)")
    print(f"wrote {scan_pdf}  ({len(SCANNED_PEOPLE)} records, image only -> needs Marathi OCR)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
