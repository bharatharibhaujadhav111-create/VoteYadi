"""Generate realistic sample Electoral Roll PDFs for testing / demo.

Usage:
    python backend/tools/generate_sample_rolls.py [--out pdfs] [--count 3] [--pages 6] [--scanned]

Each PDF mimics the ECI layout: a header with Part number, then a grid of
voter boxes (serial, EPIC, Name, Father's/Husband's Name, House, Age, Gender).
With ``--scanned`` the last page of the first PDF is rasterised (image only) so
the OCR path is exercised.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import pymupdf

FIRST_M = ["Vijay", "Bharat", "Pratapsinh", "Ramesh", "Suresh", "Ganesh", "Mahesh", "Sanjay", "Ajay", "Rahul",
           "Anil", "Sunil", "Prakash", "Deepak", "Rajesh", "Santosh", "Nitin", "Sachin", "Amol", "Kiran",
           "Dattatray", "Shivaji", "Balasaheb", "Vishal", "Rohit", "Sagar", "Yogesh", "Manoj", "Dinesh", "Vikram"]
FIRST_F = ["Vinayshree", "Sunita", "Anita", "Kavita", "Savita", "Sangita", "Manisha", "Priya", "Pooja", "Sneha",
           "Archana", "Vaishali", "Swati", "Rupali", "Meena", "Rekha", "Lata", "Asha", "Usha", "Nanda",
           "Shobha", "Jyoti", "Sarika", "Madhuri", "Aarti", "Sheetal", "Pallavi", "Kalpana", "Vandana", "Shital"]
SURNAMES = ["Jadhav", "Patil", "Pawar", "Shinde", "More", "Kadam", "Gaikwad", "Deshmukh", "Kulkarni", "Chavan",
            "Bhosale", "Sawant", "Salunkhe", "Mane", "Thorat", "Yadav", "Kale", "Suryawanshi", "Ghorpade", "Nikam"]
STATES = ["MH", "KA", "GJ", "RJ", "UP"]


def make_epic(rng: random.Random, used: set[str]) -> str:
    while True:
        e = f"{rng.choice(['ABC', 'MHT', 'KLM', 'XYZ', 'PQR', 'DEF'])}{rng.randint(1000000, 9999999)}"
        if e not in used:
            used.add(e)
            return e


def make_voters(rng: random.Random, n: int, used: set[str], surname_pool: list[str]) -> list[dict]:
    voters = []
    for i in range(1, n + 1):
        gender = rng.choice(["Male", "Female", "Female", "Male"])
        surname = rng.choice(surname_pool)
        father = rng.choice(FIRST_M)
        if gender == "Male":
            name = f"{rng.choice(FIRST_M)} {father} {surname}"
            rel_type, rel = "Father", f"{father} {surname}"
        else:
            if rng.random() < 0.5:
                name = f"{rng.choice(FIRST_F)} {father} {surname}"
                rel_type, rel = "Father", f"{father} {surname}"
            else:
                husband = rng.choice(FIRST_M)
                name = f"{rng.choice(FIRST_F)} {husband} {surname}"
                rel_type, rel = "Husband", f"{husband} {surname}"
        voters.append({
            "serial": i, "epic": make_epic(rng, used), "name": name, "rel_type": rel_type, "rel": rel,
            "house": str(rng.randint(1, 400)), "age": rng.randint(18, 90), "gender": gender,
        })
    return voters


def draw_page(doc: pymupdf.Document, part: int, page_no: int, total_pages: int, voters: list[dict], constituency: str, section: int) -> pymupdf.Page:
    page = doc.new_page(width=595, height=842)  # A4
    y = 36
    page.insert_text((40, y), f"Electoral Roll 2024 - {constituency} Assembly Constituency", fontsize=12, fontname="helv")
    y += 18
    page.insert_text((40, y), f"Part No : {part}      Section No : {section}      Page {page_no} of {total_pages}", fontsize=10, fontname="helv")
    y += 10
    page.draw_line((40, y), (555, y))
    cols, box_w, box_h = 3, 168, 84
    x0, y0 = 40, y + 12
    for i, v in enumerate(voters):
        r, c = divmod(i, cols)
        x = x0 + c * (box_w + 6)
        yy = y0 + r * (box_h + 6)
        if yy + box_h > 800:
            break
        page.draw_rect(pymupdf.Rect(x, yy, x + box_w, yy + box_h), width=0.6)
        lines = [
            f"{v['serial']}    {v['epic']}",
            f"Name : {v['name']}",
            f"{v['rel_type']}'s Name : {v['rel']}",
            f"House Number : {v['house']}",
            f"Age : {v['age']}    Gender : {v['gender']}",
        ]
        ty = yy + 13
        for ln in lines:
            page.insert_text((x + 5, ty), ln, fontsize=7.5, fontname="helv")
            ty += 13
    return page


def build_pdf(out: Path, part: int, pages: int, rng: random.Random, used: set[str], constituency: str, scanned_last: bool, force_names: list[dict] | None = None) -> int:
    doc = pymupdf.open()
    total = 0
    surname_pool = rng.sample(SURNAMES, 6)
    for p in range(1, pages + 1):
        voters = make_voters(rng, 27, used, surname_pool)
        if p == 1 and force_names:
            for i, fv in enumerate(force_names):
                voters[i].update(fv)
        for v in voters:
            v["serial"] = total + voters.index(v) + 1
        draw_page(doc, part, p, pages, voters, constituency, section=(p - 1) // 2 + 1)
        total += len(voters)
    if scanned_last:
        # rasterise the last page so it contains no text layer (forces OCR)
        last = doc[-1]
        pix = last.get_pixmap(dpi=200)
        img_page = doc.new_page(width=last.rect.width, height=last.rect.height)
        img_page.insert_image(img_page.rect, pixmap=pix)
        doc.delete_page(len(doc) - 2)
    doc.set_metadata({"title": f"Electoral Roll Part {part}", "author": "Sample Generator"})
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="pdfs")
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--pages", type=int, default=6)
    ap.add_argument("--scanned", action="store_true", help="make the last page of the first PDF image-only (OCR test)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    used: set[str] = set()
    demo = [
        {"name": "Vinayshree Bharat Jadhav", "rel_type": "Father", "rel": "Bharat Jadhav", "gender": "Female", "age": 29},
        {"name": "Vijay Bharat Jadhav", "rel_type": "Father", "rel": "Bharat Jadhav", "gender": "Male", "age": 34},
        {"name": "Pratapsinh Bharat Jadhav", "rel_type": "Father", "rel": "Bharat Jadhav", "gender": "Male", "age": 41},
    ]
    constituencies = ["Karad", "Satara", "Patan", "Koregaon", "Wai", "Phaltan", "Man", "Khatav"]
    grand = 0
    for i in range(args.count):
        part = 101 + i
        name = f"Part_{part}_{constituencies[i % len(constituencies)]}.pdf"
        n = build_pdf(out_dir / name, part, args.pages, rng, used, constituencies[i % len(constituencies)],
                      scanned_last=(args.scanned and i == 0), force_names=demo if i == 0 else None)
        grand += n
        print(f"wrote {out_dir / name}: {n} voters")
    print(f"total voters: {grand}")


if __name__ == "__main__":
    main()
