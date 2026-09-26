"""Copy Marathi (+English) Tesseract models into the app-local tessdata folder.

Run once after cloning:  python tools/install_tessdata.py
Without it the backend uses the system tesseract models when available.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "tessdata"
TARGET.mkdir(parents=True, exist_ok=True)

SOURCES = [
    Path("/usr/share/tesseract-ocr/5/tessdata"),
    Path("/usr/share/tesseract-ocr/4.00/tessdata"),
    Path("/usr/share/tessdata"),
    Path("/usr/local/share/tessdata"),
]
WANTED = ["mar.traineddata", "eng.traineddata", "osd.traineddata"]


def main() -> int:
    copied = 0
    for name in WANTED:
        dest = TARGET / name
        if dest.exists():
            print(f"ok      {dest} (already present)")
            copied += 1
            continue
        for src_dir in SOURCES:
            src = src_dir / name
            if src.exists():
                shutil.copy2(src, dest)
                print(f"copied  {src} -> {dest}")
                copied += 1
                break
        else:
            print(f"MISSING {name} – install it with:  sudo apt-get install tesseract-ocr-mar")
    print(f"\\n{copied}/{len(WANTED)} models in {TARGET}")
    return 0 if (TARGET / "mar.traineddata").exists() else 1


if __name__ == "__main__":
    sys.exit(main())
