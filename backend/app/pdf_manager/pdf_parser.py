"""PDF -> voter records extraction.

Understands the layout used by Indian Electoral Rolls (ECI format):

    12   ABC1234567
    Name          : Vinayshree Bharat Jadhav
    Father's Name : Bharat Jadhav
    House Number  : 45     Age : 34    Gender : Female

Text is extracted with PyMuPDF.  When a page has (almost) no extractable text it
is treated as a scanned image and OCR (Tesseract) is used instead.

The parser is deliberately defensive – electoral rolls come from many sources
and the exact wording differs ("Father's Name", "Husband Name", "Fathers
Name", "Mother's Name", "Other's Name" …).
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterable

import pymupdf

from .. import config
from ..core import devanagari as dev
from ..core import marathi as mar
from ..core.text_utils import EPIC_RE, normalize

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^\s*(?:elector'?s?\s*)?name\s*[:：\-]\s*(.+?)\s*$", re.I)
RELATION_RE = re.compile(
    r"^\s*((?:father|husband|mother|other|wife|guardian)(?:'?s)?)\s*(?:name)?\s*[:：\-]\s*(.+?)\s*$",
    re.I,
)
# A line that is *only* a serial number and/or EPIC ("12 ABC1234567", "ABC1234567", "12")
SERIAL_EPIC_RE = re.compile(r"^\s*(?:(\d{1,5})\b\s*)?([A-Z]{2,3}/?\d{2}/?\d{3}/?\d{6,7}|[A-Z]{3}\s?\d{7})?\s*$")
PART_RE = re.compile(r"part\s*(?:no|number)?\.?\s*[:：\-]?\s*(\d{1,4})", re.I)
SECTION_RE = re.compile(r"section\s*(?:no|number)?\.?\s*[:：\-]?\s*(\d{1,4})", re.I)
HOUSE_RE = re.compile(r"house\s*(?:no|number)?\.?\s*[:：\-]?\s*([^\s].*?)(?=\s+age\b|\s+gender\b|$)", re.I)
AGE_RE = re.compile(r"\bage\s*[:：\-]?\s*(\d{1,3})", re.I)
GENDER_RE = re.compile(r"\b(?:gender|sex)\s*[:：\-]?\s*(male|female|third gender|other|m|f|t)\b", re.I)
NOISE_RE = re.compile(r"\b(photo|available|not available|deleted)\b", re.I)

# ---------------------------------------------------------------------------
# Marathi (Devanagari) roll patterns – same layout, different script
# ---------------------------------------------------------------------------
DEV_LABEL = r"[\u0900-\u097f]+"                       # label word(s), Marathi
DEV_NAME = r"[\u0900-\u097f][\u0900-\u097f\s.\-']*"
#  नाव : रामचंद्र जाधव     |     मतदाराचे नाव - ...   |  नाव   रामचंद्र जाधव
#  नाव : रामचंद्र जाधव  |  मतदाराचे नाव : …   (but never "वडिलांचे नाव : …", which is
#  the relative's name and belongs to the *previous* voter box)
DEV_NAME_RE = re.compile(
    rf"^\s*(?!वडिल|वडील|वडिलां|पित|पती|आई|माते|माता|पत्नी|पालक|इतर|अन्य|जनक|बाप|ांचे|चे)"
    rf"[\u0900-\u097f]*\s*(?:नाव|नाम)\s*[:：\-–]?\s*(.+?)\s*$"
)
#  वडिलांचे नाव : भारत जाधव / पतीचे नाव : … / आईचे नाव : …
DEV_RELATION_RE = re.compile(
    rf"^\s*(वडिलांचे|वडिलाचे|वडिल|वडील|पित्याचे|पिताचे|पिता|जनकाचे|बापाचे|पतीचे|पतीचा|पती|"
    rf"आईचे|आईचा|आई|मातेचे|माता|पत्नीचे|पत्नी|पालकाचे|पालक|इतराचे|इतर|अन्य|ांचे|चे)"
    rf"\s*(?:नाव|नाम)?\s*[:：\-–]?\s*(.+?)\s*$"
)
DEV_HOUSE_RE = re.compile(r"(?:घर|गृह)\s*(?:क्रमांक|नं|नंबर|नो)?\s*[:：\-–]?\s*([^\s].*?)(?=\s*(?:वय|लिंग|वर्ष)\b|$)")
DEV_AGE_RE = re.compile(r"\b(?:वय|वर्ष)\s*[:：\-–]?\s*([0-9०-९]{1,3})")
DEV_GENDER_RE = re.compile(
    r"\b(?:लिंग)\s*[:：\-–]?\s*(पुरुष|स्त्री|महिला|इतर|अन्य)", re.I
)
DEV_PART_RE = re.compile(r"(?:भाग|विभाग)\s*(?:क्रमांक|नं|नो)?\s*[:：\-–]?\s*([0-9०-९]{1,4})")
DEV_SECTION_RE = re.compile(r"(?:विभाग|सेक्शन)\s*(?:क्रमांक|नं)?\s*[:：\-–]?\s*([0-9०-९]{1,4})")
DEV_PART_LATIN_RE = re.compile(r"Part\s*(?:No|Number)?\.?\s*[:：\-]?\s*(\d{1,4})", re.I)
# a line made only of a Devanagari numeral – the serial number of the next box
DEV_SERIAL_RE = re.compile(r"^\s*[0-9०-९]{1,5}\s*$")
DEV_PUNCT = re.compile(r"[\u0964\u0965]+")


def to_ascii_digits(value: str) -> str:
    """Devanagari digits -> ASCII so "भाग ७" and "part 7" filter identically."""
    return value.translate(str.maketrans(dev.DEV_TO_ASCII_DIGIT)) if value else value


# words that only appear on an English-language roll (used to recognise one)
ENGLISH_ROLL_WORDS = (
    "name", "father", "husband", "mother", "house", "age", "gender", "part",
    "section", "elector", "roll", "assembly", "constituency",
)


def looks_english(text: str) -> bool:
    """True when text reads as a *clean English* roll, not OCR noise.

    The distinction matters: an English model run over Devanagari produces
    meaningless Latin look-alikes ("Aled : WAX" for "नाव : रामचंद्र"), which
    would be indexed as a person's name.  A Latin model is therefore only used
    when the text really carries English roll vocabulary.
    """
    if not text:
        return False
    low = text.lower()
    prof = mar.page_profile(text)
    if prof["devanagari_letters"]:
        return False
    return prof["latin_letters"] >= 40 and sum(1 for w in ENGLISH_ROLL_WORDS if w in low) >= 2


def ocr_language_for(text: str, *, scanned: bool = False) -> str:
    """Language pack for a page, chosen from the script it is written in.

    * Text layer available: the script of that text decides – pure Latin with
      English roll words → ``eng`` (~2x faster), anything Devanagari → ``mar``
      or ``mar+eng``.
    * Scanned page (no text layer): the model choice has to be made from a small
      probe, and a wrong guess destroys the page.  The Marathi model *also* reads
      Latin script, so it is the safe default; plain ``eng`` is used only when
      the probe clearly reads as an English roll.
    """
    if not config.OCR_LANG_AUTO:
        return config.OCR_LANG
    if scanned:
        if looks_english(text):
            return config.OCR_LANG or "eng"
        # On Marathi voter cards the English model can turn Devanagari names
        # into plausible-looking Latin fragments ("AGA", "agar", "Goats").
        # The Marathi model usually reads the numeric headers too. Suspect
        # serials are verified with a second bilingual pass after parsing.
        return config.OCR_LANG_DEV
    prof = mar.page_profile(text)
    if prof["script"] == "latin" and looks_english(text):
        return config.OCR_LANG or "eng"
    if prof["script"] == "latin":
        # Latin-ish but no English roll vocabulary: unknown origin, keep both.
        return f'{config.OCR_LANG_DEV}+{config.OCR_LANG or "eng"}'
    if config.OCR_LANG_BLEND and prof["latin_letters"] > 40:
        return f'{config.OCR_LANG_DEV}+{config.OCR_LANG or "eng"}'
    return config.OCR_LANG_DEV



@dataclass
class VoterRecord:
    name: str
    relation_name: str = ""
    relation_type: str = ""
    epic: str = ""
    serial: str = ""
    house: str = ""
    age: str = ""
    gender: str = ""
    part: str = ""
    section: str = ""
    page: int = 1  # 1-based page number

    def to_row(self) -> dict:
        return asdict(self)


@dataclass
class PageParseResult:
    page: int
    records: list[VoterRecord] = field(default_factory=list)
    used_ocr: bool = False
    part: str = ""


@dataclass
class PdfParseResult:
    path: str
    pages: int
    records: list[VoterRecord]
    ocr_pages: int
    part: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "pages": self.pages,
            "ocr_pages": self.ocr_pages,
            "part": self.part,
            "records": [r.to_row() for r in self.records],
        }


# ----------------------------------------------------------------------------
# Text extraction (column aware)
# ----------------------------------------------------------------------------
Line = tuple[float, float, str]  # (x0, y0, text) in PDF points

# OCR can indent a damaged Marathi label by 40-60 points inside its voter card.
# Real columns in the ECI three-column layout are hundreds of points apart, so
# a wider clustering tolerance prevents a stray label from inventing a fourth
# column without merging genuine columns.
COLUMN_GAP_PT = 90.0


def _page_lines(page: pymupdf.Page) -> list[Line]:
    """Return positioned text lines from the PDF text layer."""
    lines: list[Line] = []
    data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    for block in data.get("blocks", []):
        for ln in block.get("lines", []):
            txt = "".join(sp.get("text", "") for sp in ln.get("spans", []))
            if txt.strip():
                x0, y0 = ln["bbox"][0], ln["bbox"][1]
                lines.append((x0, y0, txt))
    return lines


def _ocr_tesseract_version() -> str:
    """Tesseract version string, or "" when OCR is unavailable."""
    try:
        import pytesseract

        _configure_tesseract(pytesseract)
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return ""


def _configure_tesseract(pytesseract_module) -> None:
    """Configure bundled language data and discover common Windows installs."""
    if config.TESSDATA_DIR.exists():
        os.environ.setdefault("TESSDATA_PREFIX", str(config.TESSDATA_DIR))
    if config.TESSERACT_CMD:
        pytesseract_module.pytesseract.tesseract_cmd = config.TESSERACT_CMD
        return
    if os.name == "nt":
        candidates = (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        )
        for candidate in candidates:
            if candidate.is_file():
                pytesseract_module.pytesseract.tesseract_cmd = str(candidate)
                break


def _probe_page_text(page: pymupdf.Page) -> str:
    """Cheap script probe for a page with no text layer.

    Rasterises a small strip (top sixth, 90 dpi) and reads it with *both* models
    so the amount of Devanagari that comes out decides the language for the full
    page.  Costs well under a second even on a 8263x11692 pt scanned roll.
    """
    if not config.OCR_ENABLED:
        return ""
    try:
        import pytesseract  # noqa: WPS433
        from PIL import Image

        _configure_tesseract(pytesseract)
        os.environ.setdefault("OMP_THREAD_LIMIT", "1")
        clip = pymupdf.Rect(0, 0, page.rect.width, max(page.rect.height / 6, 1))
        pix = page.get_pixmap(dpi=90, clip=clip, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        return pytesseract.image_to_string(
            img, lang=f'{config.OCR_LANG_DEV}+{config.OCR_LANG or "eng"}'
        )
    except Exception as exc:  # pragma: no cover - probe is best effort
        log.debug("script probe failed: %s", exc)
        return ""


def _ocr_lines(page: pymupdf.Page, lang: str | None = None, *, psm: int | None = None) -> list[Line]:
    """OCR the page and return positioned lines (converted to PDF points).

    ``lang`` defaults to the page's own script profile (see ``ocr_language_for``),
    so Marathi pages are read with the Devanagari model and English pages with
    the (faster) Latin one, in the same index run.
    """
    if not config.OCR_ENABLED:
        return []
    try:
        import pytesseract  # noqa: WPS433 (optional dependency)
        from pytesseract import Output
        from PIL import Image
    except Exception:  # pragma: no cover
        log.warning("OCR requested but pytesseract/Pillow not installed")
        return []
    # Tesseract spawns OpenMP threads per process; with several worker
    # processes this oversubscribes the CPU dramatically (minutes per page
    # instead of seconds).  One thread per process is fastest overall.
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    _configure_tesseract(pytesseract)
    try:
        # Adaptive resolution: scanned rolls are often stored as huge pages
        # (e.g. 1983x2806 pt).  Aim for a fixed pixel width so OCR time is
        # predictable regardless of the page's nominal size.
        target_px = config.OCR_TARGET_WIDTH_PX
        dpi = max(72, min(config.OCR_DPI, int(target_px / max(page.rect.width, 1) * 72)))
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        scale = 72.0 / dpi
        # psm 3 (auto) reads the boxed serial/EPIC header of each voter box that
        # psm 6 skips; both handle the 3-column grid once we split by gaps.
        use_lang = lang or config.OCR_LANG
        data = pytesseract.image_to_data(
            img, lang=use_lang, config=f"--psm {psm or config.OCR_PSM}", output_type=Output.DICT
        )
    except Exception as exc:  # pragma: no cover
        log.warning("OCR failed on page %s: %s", page.number, exc)
        return []

    grouped: dict[tuple[int, int, int], list[tuple[int, int, int, int, str]]] = {}
    heights: list[int] = []
    n = len(data.get("text", []))
    for i in range(n):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        try:
            if float(data["conf"][i]) < 0:
                continue
        except (TypeError, ValueError):
            pass
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        grouped.setdefault(key, []).append((data["left"][i], data["top"][i], data["width"][i], data["height"][i], word))
        heights.append(data["height"][i])
    heights.sort()
    med_h = heights[len(heights) // 2] if heights else 20
    # Tesseract tends to merge side-by-side voter boxes into one line; split a
    # line wherever the horizontal gap between words is unusually large.
    gap_px = max(int(med_h * 1.6), 12)
    lines: list[Line] = []
    for words in grouped.values():
        words.sort(key=lambda w: w[0])
        segment: list[tuple[int, int, int, int, str]] = []
        for w in words:
            if segment and w[0] - (segment[-1][0] + segment[-1][2]) > gap_px:
                lines.append((segment[0][0] * scale, min(s[1] for s in segment) * scale, " ".join(s[4] for s in segment)))
                segment = []
            segment.append(w)
        if segment:
            lines.append((segment[0][0] * scale, min(s[1] for s in segment) * scale, " ".join(s[4] for s in segment)))
    return _repair_ocr_epics(lines)


_OCR_DIGIT_FOR_LETTER = {
    "B": {"8"}, "C": {"0", "6"}, "G": {"0", "6"}, "I": {"1"},
    "O": {"0"}, "S": {"5"}, "Z": {"2"},
}


def _repair_ocr_epics(lines: list[Line]) -> list[Line]:
    """Repair digit-shaped OCR substitutions in EPIC prefixes.

    On this roll Tesseract regularly reads ``ZCG6902928`` as ``2066902928``.
    A repair is made only when the page already contains at least two valid
    EPICs with the same three-letter prefix, so arbitrary 10-digit values are
    never guessed without page-local evidence.
    """
    prefixes: Counter[str] = Counter()
    for _, _, text in lines:
        match = EPIC_RE.search(text.upper())
        if match:
            compact = normalize(match.group(1)).replace(" ", "").replace("/", "").upper()
            if re.fullmatch(r"[A-Z]{3}\d{7}", compact):
                prefixes[compact[:3]] += 1
    if not prefixes:
        return lines
    prefix, count = prefixes.most_common(1)[0]
    if count < 2:
        return lines

    repaired: list[Line] = []
    for x, y, text in lines:
        compact = re.sub(r"\s+", "", text)
        if re.fullmatch(r"\d{10}", compact) and all(
            compact[i] in _OCR_DIGIT_FOR_LETTER.get(letter, set())
            for i, letter in enumerate(prefix)
        ):
            text = prefix + compact[3:]
        repaired.append((x, y, text))
    return repaired


def order_by_columns(lines: list[Line]) -> list[str]:
    """Group lines into vertical columns (left-edge clustering) and read each
    column top-to-bottom.  Electoral rolls print voter boxes in a 3-column
    grid; naive top-to-bottom reading would interleave the boxes."""
    if not lines:
        return []

    # Anchor columns on the "Name :" lines – every voter box has one and they
    # share the same left edge within a column.  Other lines of a box (serial
    # number in a centred frame, right-aligned EPIC, age/gender) start further
    # right, so plain left-edge clustering would split a box across columns.
    name_anchors = [l for l in lines if NAME_RE.match(l[2]) or DEV_NAME_RE.match(l[2])]
    anchor_xs = sorted({round(l[0]) for l in name_anchors})
    if len(anchor_xs) < 2:
        anchor_xs = sorted({round(l[0]) for l in lines})
    clusters: list[list[float]] = [[anchor_xs[0]]]
    for x in anchor_xs[1:]:
        if x - clusters[-1][-1] > COLUMN_GAP_PT:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    starts = [min(c) for c in clusters]
    # A line belongs to the right-most column whose start is left of it.
    tol = COLUMN_GAP_PT

    def column_of(x: float) -> int:
        idx = 0
        for i, s in enumerate(starts):
            if x >= s - tol:
                idx = i
        return idx

    # Rejoin label values before inserting spatially inferred serial markers.
    # Otherwise a marker can sort between "नाव: श..." and the continuation
    # fragment Tesseract placed a few points to its right.
    consumed: set[int] = set()
    replacements: dict[int, Line] = {}
    for anchor_index, anchor in enumerate(lines):
        if not (NAME_RE.match(anchor[2]) or DEV_NAME_RE.match(anchor[2])
                or RELATION_RE.match(anchor[2]) or DEV_RELATION_RE.match(anchor[2])
                or HOUSE_RE.search(anchor[2]) or DEV_HOUSE_RE.search(anchor[2])):
            continue
        col = column_of(anchor[0])
        col_width = (starts[col + 1] - starts[col]) if col + 1 < len(starts) else (
            starts[col] - starts[col - 1] if col else 600
        )
        continuations: list[tuple[float, str, int]] = []
        for candidate_index, candidate in enumerate(lines):
            if candidate_index == anchor_index or candidate_index in consumed:
                continue
            if column_of(candidate[0]) != col or not (anchor[0] < candidate[0]):
                continue
            if candidate[0] - anchor[0] >= col_width * 0.55 or abs(candidate[1] - anchor[1]) > 8:
                continue
            text = candidate[2].strip()
            if (not text or DEV_SERIAL_RE.fullmatch(text) or SERIAL_EPIC_RE.fullmatch(text)
                    or EPIC_RE.search(text) or NAME_RE.match(text) or DEV_NAME_RE.match(text)
                    or RELATION_RE.match(text) or DEV_RELATION_RE.match(text)):
                continue
            continuations.append((candidate[0], text, candidate_index))
        if continuations:
            continuations.sort()
            replacements[anchor_index] = (
                anchor[0], anchor[1],
                " ".join([anchor[2], *(item[1] for item in continuations)]),
            )
            consumed.update(item[2] for item in continuations)
    if replacements:
        lines = [replacements.get(index, line) for index, line in enumerate(lines)
                 if index not in consumed]
        name_anchors = [line for line in lines if NAME_RE.match(line[2]) or DEV_NAME_RE.match(line[2])]

    # Serial numbers are printed at a stable position above each voter name.
    # If OCR misses a number, recover it from the card's row/column position,
    # calibrated by the serials that OCR did read on this same page.  Spatial
    # row ranks preserve gaps when a card/name itself was not recognised.
    if name_anchors and len(starts) >= 2:
        row_centres: list[float] = []
        for y in sorted(l[1] for l in name_anchors):
            if not row_centres or y - row_centres[-1] > 35:
                row_centres.append(y)
            else:
                row_centres[-1] = (row_centres[-1] + y) / 2

        def card_position(line: Line) -> tuple[int, int]:
            col = column_of(line[0])
            row = min(range(len(row_centres)), key=lambda i: abs(row_centres[i] - line[1]))
            return row * len(starts) + col, col

        observed: dict[int, int] = {}
        cards: list[tuple[Line, int, int]] = []
        for anchor in name_anchors:
            pos, col = card_position(anchor)
            cards.append((anchor, pos, col))
            col_width = (starts[col + 1] - starts[col]) if col + 1 < len(starts) else (
                starts[col] - starts[col - 1] if col else 600
            )
            candidates: list[tuple[float, int]] = []
            for x, y, text in lines:
                if column_of(x) != col or not DEV_SERIAL_RE.fullmatch(text.strip()):
                    continue
                # Serials sit in the left half of a card; numeric EPIC OCR
                # noise and photo labels occur much farther to the right.
                if not (0 <= x - starts[col] < col_width * 0.55):
                    continue
                dy = anchor[1] - y
                if 0 < dy < 90:
                    try:
                        candidates.append((dy, int(to_ascii_digits(text.strip()))))
                    except ValueError:
                        pass
            if candidates:
                observed[pos] = min(candidates)[1]

        bases = Counter(serial - pos for pos, serial in observed.items())
        if len(observed) >= 2 and bases:
            base, support = bases.most_common(1)[0]
            if base > 0 and support >= 2:
                # Once the page sequence is established, replace every nearby
                # OCR numeral (including truncations such as ``11`` -> ``1``
                # and photo-area noise) with the spatially derived value.
                def is_card_number(line: Line) -> bool:
                    x, y, text = line
                    if not DEV_SERIAL_RE.fullmatch(text.strip()):
                        return False
                    col = column_of(x)
                    return any(
                        card_col == col and 0 < anchor[1] - y < 90
                        for anchor, _, card_col in cards
                    )

                augmented = [line for line in lines if not is_card_number(line)]
                for anchor, pos, _ in cards:
                    # Keep enough vertical separation to survive the 2-point
                    # row rounding used by the column sorter below.
                    augmented.append((anchor[0], anchor[1] - 3.0, str(base + pos)))
                lines = augmented

    buckets: list[list[Line]] = [[] for _ in starts]
    for ln in lines:
        buckets[column_of(ln[0])].append(ln)
    ordered: list[str] = []
    for col in buckets:
        col.sort(key=lambda l: (round(l[1] / 2), l[0]))
        joined: list[Line] = []
        for line in col:
            if joined and abs(joined[-1][1] - line[1]) <= 3:
                prior = joined[-1][2]
                # OCR may split a label and its Marathi value at a large word
                # gap inside one card. Join labelled fields only; serial/EPIC
                # headers stay separate so a damaged EPIC cannot hide a good
                # serial number.
                if (NAME_RE.match(prior) or DEV_NAME_RE.match(prior)
                        or RELATION_RE.match(prior) or DEV_RELATION_RE.match(prior)
                        or HOUSE_RE.search(prior) or DEV_HOUSE_RE.search(prior)):
                    joined[-1] = (joined[-1][0], joined[-1][1], f"{prior} {line[2]}")
                    continue
            joined.append(line)
        ordered.extend(line[2] for line in joined)
    return ordered


# ----------------------------------------------------------------------------
# Record parsing (state machine over lines)
# ----------------------------------------------------------------------------
def _clean(value: str) -> str:
    value = DEV_PUNCT.sub(" ", value)
    value = NOISE_RE.sub("", value)
    # OCR artefacts: stray brackets / pipes / quotes inside names
    value = re.sub(r"[\[\]{}|<>*_\"`~^]+", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .:-|,;")
    return value


def _finish(current: VoterRecord | None, out: list[VoterRecord]) -> None:
    """Validate, clean and keep a record.

    Marathi names arrive with honourifics (श्री / श्रीमती), trailing danda and
    stray form labels; ``mar.clean_name`` removes those.  A record whose words
    are *all* labels ("नाव", "घर क्रमांक") is dropped instead of being indexed as
    a person.
    """
    if not current or not current.name:
        return
    current.name = mar.clean_name(current.name) or current.name
    if current.relation_name:
        current.relation_name = mar.clean_name(current.relation_name)
    if not current.name:
        return
    for tok in current.name.split():
        if not mar.is_label(tok) and len(tok) > 1:
            out.append(current)
            return


def parse_lines(lines: Iterable[str], page_no: int, part: str, section: str) -> list[VoterRecord]:
    records: list[VoterRecord] = []
    current: VoterRecord | None = None
    pending_serial = ""
    pending_epic = ""

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        m = DEV_NAME_RE.match(line)
        if m:
            _finish(current, records)
            current = VoterRecord(
                name=_clean(m.group(1)),
                epic=pending_epic,
                serial=pending_serial,
                part=part,
                section=section,
                page=page_no,
            )
            pending_epic = pending_serial = ""
            continue

        m = NAME_RE.match(line)
        if m:
            _finish(current, records)
            current = VoterRecord(
                name=_clean(m.group(1)),
                epic=pending_epic,
                serial=pending_serial,
                part=part,
                section=section,
                page=page_no,
            )
            pending_epic = pending_serial = ""
            continue

        m = DEV_RELATION_RE.match(line)
        if m:
            rel_type = mar.relation_type_of(m.group(1)) or m.group(1)
            value = _clean(m.group(2))
            if current is None or current.relation_name:
                target = next((r for r in reversed(records) if not r.relation_name), None)
                if target is not None and current is None:
                    target.relation_name, target.relation_type = value, rel_type
                    continue
                _finish(current, records)
                current = VoterRecord(name="", part=part, section=section, page=page_no)
            current.relation_name, current.relation_type = value, rel_type
            continue

        m = RELATION_RE.match(line)
        if m:
            rel_type = re.sub(r"'?s$", "", m.group(1).lower()).strip()
            value = _clean(m.group(2))
            if current is None or current.relation_name:
                # relation without a preceding name (odd column ordering) – attach to
                # the most recent record lacking a relation, else start a new one.
                target = next((r for r in reversed(records) if not r.relation_name), None)
                if target is not None and current is None:
                    target.relation_name, target.relation_type = value, rel_type
                    continue
                _finish(current, records)
                current = VoterRecord(name="", part=part, section=section, page=page_no)
            current.relation_name, current.relation_type = value, rel_type
            continue

        if DEV_SERIAL_RE.match(line) and current is None:
            pending_serial = to_ascii_digits(line.strip())
            continue

        m = SERIAL_EPIC_RE.match(line)
        if m and (m.group(1) or m.group(2)):
            # start of a new voter box – flush the previous one.  Serial and
            # EPIC may arrive on one line or on two consecutive lines (OCR).
            _finish(current, records)
            current = None
            if m.group(1):
                pending_serial = m.group(1)
                if not m.group(2):
                    pending_epic = ""
            if m.group(2):
                pending_epic = m.group(2).replace(" ", "").replace("/", "")
            continue

        epic_match = EPIC_RE.search(line)
        if epic_match and current is not None and not current.epic:
            current.epic = epic_match.group(1)
        elif epic_match and current is None:
            pending_epic = epic_match.group(1)

        if current is not None:
            hm = HOUSE_RE.search(line) or DEV_HOUSE_RE.search(line)
            if hm and not current.house:
                current.house = _clean(hm.group(1))
            am = AGE_RE.search(line) or DEV_AGE_RE.search(line)
            if am and not current.age:
                current.age = to_ascii_digits(am.group(1))
            gm = GENDER_RE.search(line) or DEV_GENDER_RE.search(line)
            if gm and not current.gender:
                g = gm.group(1).lower()
                current.gender = mar.GENDER_MAP.get(g, {"m": "Male", "f": "Female", "t": "Third Gender"}.get(g, g.title()))

    _finish(current, records)
    return [r for r in records if r.name]


def _drop_phantom_relations(records: list[VoterRecord]) -> list[VoterRecord]:
    """Remove records that are really the relative of the voter before them.

    Scanned Marathi rolls sometimes lose the label ("वडिलांचे" → "asferd"), so the
    relative's name is read as a voter of its own.  Such a phantom is recognisable:
    no EPIC, no relation of its own, and its name repeats the preceding record's
    relative name.  Dropping it keeps the roll count right without losing anyone
    (the real voter keeps its relation name).
    """
    out: list[VoterRecord] = []
    for rec in records:
        if (
            out
            and not rec.epic
            and not rec.relation_name
            and rec.name
            and normalize(rec.name) == normalize(out[-1].relation_name or "")
        ):
            continue
        out.append(rec)
    return out


def parse_page_text(lines: list[str], page_no: int, part_hint: str = "") -> PageParseResult:
    full_text = "\n".join(lines)
    part = part_hint
    pm = PART_RE.search(full_text) or DEV_PART_RE.search(full_text) or DEV_PART_LATIN_RE.search(full_text)
    if pm:
        part = to_ascii_digits(pm.group(1))
    section = ""
    sm = SECTION_RE.search(full_text) or DEV_SECTION_RE.search(full_text)
    if sm:
        section = to_ascii_digits(sm.group(1))
    records = _drop_phantom_relations(parse_lines(lines, page_no, part, section))
    return PageParseResult(page=page_no, records=records, part=part)


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------
def _parse_page_job(args: tuple[str, int]) -> tuple[int, str, bool, list[dict]]:
    """Parse one page (runs in a worker process).  Returns (page_no, part, used_ocr, records)."""
    path, page_index = args
    with pymupdf.open(path) as doc:
        page = doc[page_index]
        lines = _page_lines(page)
        probe = " ".join(l[2] for l in lines)
        text_len = len(probe.strip())
        used_ocr = False
        if text_len < config.OCR_MIN_TEXT_CHARS:
            # A short text layer may be only a stamp or watermark. Treat the
            # page as scanned and use Marathi OCR unless the probe clearly
            # identifies an English roll.
            if config.OCR_LANG_AUTO and not probe.strip():
                probe = _probe_page_text(page)
            lang = ocr_language_for(probe, scanned=True)
            ocr = _ocr_lines(page, lang=lang)
            if ocr:
                lines = ocr
                used_ocr = True
        result = parse_page_text(order_by_columns(lines), page_index + 1, "")
        return page_index + 1, result.part, used_ocr, [r.to_row() for r in result.records]


def _apply_verified_page_serials(rows: list[dict], other: list[VoterRecord], first_serial: int) -> bool:
    """Transfer only independently verified serials, never bilingual names."""
    expected = set(range(first_serial, first_serial + len(rows)))
    try:
        serials = [int(record.serial) for record in other]
    except (ValueError, TypeError):
        return False
    if len(set(serials)) != len(serials) or not set(serials) <= expected:
        return False

    # Fast path: both passes found every card in the same order. Do not move
    # an already-correct number to another card.
    if len(other) == len(rows) and set(serials) == expected:
        aligned = True
        for row, serial in zip(rows, serials):
            try:
                old = int(row["serial"])
            except (ValueError, TypeError):
                continue
            if old in expected and old != serial:
                aligned = False
                break
        if aligned:
            for row, serial in zip(rows, serials):
                row["serial"] = str(serial)
            return True

    # A bilingual pass can miss one Marathi name while reading all other
    # serials correctly. Match those cards by unique full name, then infer the
    # sole remaining number only when exactly one card and one number remain.
    if len(other) != len(rows) - 1 or len(set(serials)) != len(rows) - 1:
        return False
    original_names = [normalize(str(row.get("name") or "")) for row in rows]
    other_names = [normalize(record.name) for record in other]
    if (not all(original_names) or not all(other_names)
            or len(set(original_names)) != len(rows)
            or len(set(other_names)) != len(other)
            or not set(other_names) <= set(original_names)):
        return False
    by_name = dict(zip(other_names, serials))
    missing = expected - set(serials)
    if len(missing) != 1:
        return False
    inferred = missing.pop()
    for row, name in zip(rows, original_names):
        row["serial"] = str(by_name.get(name, inferred))
    return True


def _numeric_serials(rows: list[dict]) -> list[int]:
    return [int(value) for row in rows if (value := str(row.get("serial") or "").strip()).isdigit()]


def _merge_complete_page(rows: list[dict], other: list[VoterRecord], expected: set[int]) -> bool:
    """Merge a complete alternate parse while preserving primary-pass text."""
    try:
        serials = [int(record.serial) for record in other]
    except (ValueError, TypeError):
        return False
    if len(other) != len(expected) or len(serials) != len(set(serials)) or set(serials) != expected:
        return False

    indexed = list(enumerate(rows))
    by_epic = {
        str(row.get("epic") or "").replace(" ", "").upper(): (index, row)
        for index, row in indexed if str(row.get("epic") or "").strip()
    }
    by_serial = {
        str(row.get("serial") or "").strip(): (index, row)
        for index, row in indexed if str(row.get("serial") or "").strip()
    }
    by_name = {normalize(str(row.get("name") or "")): (index, row) for index, row in indexed}
    merged: list[dict] = []
    used: set[int] = set()
    alternate_only = 0
    for record in other:
        alternate = record.to_row()
        epic = record.epic.replace(" ", "").upper()
        match = by_epic.get(epic) if epic else None
        match = match or by_serial.get(record.serial)
        match = match or by_name.get(normalize(record.name))
        if match and match[0] not in used:
            index, original = match
            used.add(index)
            kept = dict(original)
            kept["serial"] = record.serial
            merged.append(kept)
        else:
            alternate_only += 1
            merged.append(alternate)
    expected_new = len(other) - len(rows)
    if len(used) != len(rows) or alternate_only != expected_new or expected_new not in (0, 1):
        return False
    rows[:] = merged
    return True


def _digit_candidates(page: pymupdf.Page, anchors: list[Line], expected: set[int]) -> set[int]:
    """Read only Latin digits, including tight crops around voter headers."""
    try:
        import pytesseract  # noqa: WPS433
        from PIL import Image
        from pytesseract import Output
    except Exception:  # pragma: no cover
        return set()
    _configure_tesseract(pytesseract)
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    dpi = max(300, config.OCR_DPI)
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    scale = dpi / 72.0
    found: set[int] = set()

    def collect(source, psm: int) -> None:
        try:
            data = pytesseract.image_to_data(
                source, lang=config.OCR_LANG or "eng",
                config=f"--psm {psm} -c tessedit_char_whitelist=0123456789",
                output_type=Output.DICT,
            )
        except Exception as exc:  # pragma: no cover
            log.debug("digit OCR failed on page %s: %s", page.number + 1, exc)
            return
        for value in data.get("text", []):
            text = str(value or "").strip()
            if text.isdigit() and int(text) in expected:
                found.add(int(text))

    collect(image, 12)
    if expected <= found:
        return found
    for x, y, text in anchors:
        if not (DEV_NAME_RE.match(text) or NAME_RE.match(text)):
            continue
        crop = image.crop((
            max(0, int(x * scale)), max(0, int((y - 115) * scale)),
            min(image.width, int((x + 220) * scale)),
            min(image.height, max(1, int((y - 15) * scale))),
        ))
        collect(crop, 6)
        if expected <= found:
            break
    return found


def _apply_digit_verified_serials(rows: list[dict], expected: set[int], confirmed: set[int]) -> bool:
    """Apply only corrections independently confirmed by digits-only OCR."""
    if len(rows) != len(expected):
        return False
    actual = _numeric_serials(rows)
    if len(actual) == len(rows) and len(set(actual)) == len(actual):
        offset = min(expected) - min(actual)
        shifted = {value + offset for value in actual}
        # A full page can lose one otherwise-clear number in the independent
        # verification pass.  The constant shift is safe only when neighbour
        # pages prove the exact interval and at least 95% of a substantial
        # page is separately confirmed. Sparse pages require every number.
        enough_confirmation = expected <= confirmed or (
            len(expected) >= 10
            and len(expected & confirmed) / len(expected) >= 0.95
        )
        if shifted == expected and offset and enough_confirmation:
            for row in rows:
                row["serial"] = str(int(row["serial"]) + offset)
            return True

    valid = {value for value in actual if value in expected}
    unknown = [row for row in rows if not str(row.get("serial") or "").isdigit()
               or int(row["serial"]) not in expected]
    missing = expected - valid
    if expected <= confirmed and len(unknown) == len(missing) == 1:
        unknown[0]["serial"] = str(next(iter(missing)))
        return True
    return False


def _card_record_from_text(
    text: str, *, serial: int, page_no: int, epic_prefix: str = ""
) -> VoterRecord | None:
    """Parse one high-resolution voter-card crop.

    This intentionally accepts only a small set of common Marathi OCR label
    substitutions. It is used solely after neighbouring pages prove that one
    card is absent from an otherwise complete page.
    """
    lines = [re.sub(r"^[|\[\] ]+", "", line).strip() for line in text.splitlines()]
    name = relation = relation_type = house = age = gender = epic = ""
    name_index = -1
    tolerant_name = re.compile(r"^(?:नाव|नांव|नाम|नाच|नाल|नाज)\s*[:：!\-–*]?\s*(.+)$")
    for index, line in enumerate(lines):
        if not line:
            continue
        epic_match = EPIC_RE.search(line.upper())
        if epic_match:
            epic = epic_match.group(1).replace(" ", "").replace("/", "")
        elif not epic and epic_prefix:
            digits = re.search(r"(?<!\d)(\d{7})(?!\d)", to_ascii_digits(line))
            if digits:
                epic = epic_prefix + digits.group(1)
        match = tolerant_name.match(line)
        if match and not name:
            name = mar.clean_name(_clean(match.group(1)))
            name_index = index
            continue
        match = DEV_RELATION_RE.match(line)
        if match and not relation:
            relation_type = mar.relation_type_of(match.group(1)) or match.group(1)
            relation = mar.clean_name(_clean(match.group(2)))
        elif name and not relation and index == name_index + 1 and line.startswith(":"):
            relation = mar.clean_name(_clean(line.lstrip(":： ")))
        house_match = DEV_HOUSE_RE.search(line)
        if house_match and not house:
            house = _clean(house_match.group(1))
        age_match = DEV_AGE_RE.search(line)
        if age_match and not age:
            age = to_ascii_digits(age_match.group(1))
        gender_match = DEV_GENDER_RE.search(line)
        if gender_match and not gender:
            raw_gender = gender_match.group(1)
            gender = mar.GENDER_MAP.get(raw_gender, raw_gender)
    if len(re.findall(r"[\u0900-\u097f]+", name)) < 2:
        return None
    return VoterRecord(
        name=name, relation_name=relation, relation_type=relation_type,
        epic=epic, serial=str(serial), house=house, age=age, gender=gender,
        page=page_no,
    )


def _recover_single_missing_card(
    page: pymupdf.Page,
    page_no: int,
    rows: list[dict],
    expected: set[int],
    anchors: list[Line],
) -> bool:
    """Recover one omitted card from a tightly cropped high-resolution OCR pass."""
    actual = _numeric_serials(rows)
    missing = expected - set(actual)
    if (len(missing) != 1 or len(rows) + 1 != len(expected)
            or len(actual) != len(rows) or len(actual) != len(set(actual))):
        return False
    serial = next(iter(missing))
    serial_anchors = []
    for x, y, value in anchors:
        if not DEV_SERIAL_RE.fullmatch(value.strip()):
            continue
        try:
            if int(to_ascii_digits(value.strip())) == serial:
                serial_anchors.append((x, y))
        except ValueError:
            pass
    try:
        import pytesseract  # noqa: WPS433
        from PIL import Image
    except Exception:  # pragma: no cover
        return False
    _configure_tesseract(pytesseract)
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    if len(serial_anchors) != 1:
        # Layout OCR can read a perfectly clear printed serial but omit its
        # bounding box on a different Tesseract build. Locate it independently
        # with a digits-only sparse-text pass before giving up.
        pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
        locator = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        located: list[tuple[float, float]] = []
        for psm in (11, 12):
            try:
                data = pytesseract.image_to_data(
                    locator,
                    lang=config.OCR_LANG or "eng",
                    config=f"--psm {psm} -c tessedit_char_whitelist=0123456789",
                    output_type=pytesseract.Output.DICT,
                )
            except Exception as exc:  # pragma: no cover
                log.debug("serial locator failed on page %s: %s", page_no, exc)
                continue
            scale = 72 / 300
            for index, value in enumerate(data.get("text", [])):
                if to_ascii_digits(str(value).strip()) == str(serial):
                    point = (float(data["left"][index]) * scale,
                             float(data["top"][index]) * scale)
                    if not any(abs(point[0] - old[0]) < 5 and abs(point[1] - old[1]) < 5
                               for old in located):
                        located.append(point)
        serial_anchors = located
    if len(serial_anchors) != 1:
        return False

    x, y = serial_anchors[0]
    column_width = page.rect.width / 3
    column = max(0, min(2, int(x / column_width)))
    clip = pymupdf.Rect(
        column * column_width + 5,
        max(0, y - 30),
        min(page.rect.width, (column + 1) * column_width - 5),
        min(page.rect.height, y + 235),
    )
    pix = page.get_pixmap(dpi=600, colorspace=pymupdf.csGRAY, clip=clip)
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    prefixes = Counter()
    for _, _, value in anchors:
        match = EPIC_RE.search(value.upper())
        if match:
            compact = match.group(1).replace(" ", "").replace("/", "")
            if re.fullmatch(r"[A-Z]{3}\d{7}", compact):
                prefixes[compact[:3]] += 1
    prefix = prefixes.most_common(1)[0][0] if prefixes else ""
    candidates: list[VoterRecord] = []
    variants = [image] + [image.point(lambda pixel, level=level: 0 if pixel < level else 255)
                          for level in (170, 190, 210)]
    for variant in variants:
        for psm in (6, 11):
            try:
                text = pytesseract.image_to_string(
                    variant,
                    lang=f'{config.OCR_LANG_DEV}+{config.OCR_LANG or "eng"}',
                    config=f"--psm {psm}",
                )
            except Exception as exc:  # pragma: no cover
                log.debug("card OCR failed on page %s serial %s: %s", page_no, serial, exc)
                continue
            record = _card_record_from_text(
                text, serial=serial, page_no=page_no, epic_prefix=prefix
            )
            if record is not None:
                candidates.append(record)
    if not candidates:
        return False
    record = max(candidates, key=lambda item: (
        bool(item.relation_name), bool(item.epic), bool(item.age), bool(item.gender),
        len(item.name.split()), len(item.name),
    ))
    rows.append(record.to_row())
    return True


def _recover_single_card_serial(
    rows: list[dict], expected: set[int], anchors: list[Line], page_width: float
) -> bool:
    """Use a uniquely positioned printed serial for a one-card page."""
    if (len(rows) != 1 or len(expected) != 1
            or str(rows[0].get("serial") or "").strip()
            or not str(rows[0].get("name") or "").strip()):
        return False
    serial = next(iter(expected))
    serial_anchors = []
    name_anchors = []
    for x, y, text in anchors:
        value = text.strip()
        if DEV_SERIAL_RE.fullmatch(value):
            try:
                if int(to_ascii_digits(value)) == serial:
                    serial_anchors.append((x, y))
            except ValueError:
                pass
        elif DEV_NAME_RE.match(text) or NAME_RE.match(text):
            name_anchors.append((x, y))
    if len(serial_anchors) != 1 or len(name_anchors) != 1:
        return False
    serial_x, serial_y = serial_anchors[0]
    name_x, name_y = name_anchors[0]
    column_width = page_width / 3
    if (int(serial_x / column_width) != int(name_x / column_width)
            or not 0 < name_y - serial_y < 90):
        return False
    rows[0]["serial"] = str(serial)
    return True


def _recover_page_serials(path: Path, page_no: int, rows: list[dict], expected: set[int]) -> bool:
    """Recover a suspect page using layout and digit passes plus neighbour bounds."""
    with pymupdf.open(path) as doc:
        page = doc[page_no - 1]
        bilingual = _ocr_lines(
            page, lang=f'{config.OCR_LANG_DEV}+{config.OCR_LANG or "eng"}', psm=6
        )
        other = parse_page_text(order_by_columns(bilingual), page_no).records if bilingual else []
        if _merge_complete_page(rows, other, expected):
            log.info("Recovered complete page %d with alternate layout OCR", page_no)
            return True
        if (expected and len(expected) == len(rows)
                and _apply_verified_page_serials(rows, other, min(expected))):
            log.info("Recovered page %d serials by matching bilingual OCR names", page_no)
            return True
        if _recover_single_card_serial(rows, expected, bilingual, page.rect.width):
            log.info("Recovered serial on one-card page %d from its printed header", page_no)
            return True
        if _recover_single_missing_card(page, page_no, rows, expected, bilingual):
            log.info("Recovered one missing voter card on page %d", page_no)
            return True

        confirmed = _digit_candidates(page, bilingual, expected)
    before = [str(row.get("serial") or "") for row in rows]
    if _apply_digit_verified_serials(rows, expected, confirmed):
        after = [str(row.get("serial") or "") for row in rows]
        log.info("Digit-verified serial correction on page %d: %s -> %s", page_no, before, after)
        return True
    return False


def _neighbour_expected(results: list[tuple[int, str, bool, list[dict]]], index: int) -> set[int]:
    """Serial interval bounded by the nearest populated pages on both sides."""
    previous: int | None = None
    following: int | None = None
    for earlier in range(index - 1, -1, -1):
        values = _numeric_serials(results[earlier][3])
        if values:
            previous = max(values)
            break
    for later in range(index + 1, len(results)):
        values = _numeric_serials(results[later][3])
        if values:
            following = min(values)
            break
    row_count = len(results[index][3])
    if previous is not None and following is not None:
        if following <= previous + 1:
            return set()
        expected = set(range(previous + 1, following))
    elif previous is not None and row_count:
        expected = set(range(previous + 1, previous + row_count + 1))
    elif following is not None and row_count:
        expected = set(range(following - row_count, following))
    else:
        return set()
    # Electoral pages contain at most about 30 cards. A much larger interval
    # is an official gap or an untrusted neighbour, not safe repair evidence.
    return expected if len(expected) <= 40 else set()


def _recover_missing_sequence_serials(rows: list[dict]) -> int:
    """Fill blank serials only when the complete sequence proves them.

    With one blank, a unique missing value in an otherwise complete 1..N set
    is sufficient proof even if OCR returned two cards out of display order.
    Multiple blanks are filled only when every visible value also matches its
    row position.  Wrong, duplicated, or unexpected values disable recovery.
    """
    blank_positions: list[int] = []
    serials: list[int] = []
    for position, row in enumerate(rows, start=1):
        value = str(row.get("serial") or "").strip()
        if not value:
            blank_positions.append(position)
            continue
        if not value.isdigit():
            return 0
        serials.append(int(value))
    if not blank_positions or len(serials) != len(set(serials)):
        return 0
    expected = set(range(1, len(rows) + 1))
    if not set(serials) <= expected:
        return 0
    missing = expected - set(serials)
    if len(missing) != len(blank_positions):
        return 0
    if len(blank_positions) == 1:
        rows[blank_positions[0] - 1]["serial"] = str(next(iter(missing)))
        return 1
    if any(
        str(row.get("serial") or "").strip()
        and int(row["serial"]) != position
        for position, row in enumerate(rows, start=1)
    ):
        return 0
    for position in blank_positions:
        rows[position - 1]["serial"] = str(position)
    return len(blank_positions)


def parse_pdf(
    path: str | Path,
    *,
    workers: int = 1,
    progress: "Callable[[int, int], None] | None" = None,
    recover_serials: bool = True,
) -> PdfParseResult:
    """Extract voter records from a PDF.

    ``workers`` > 1 parses pages in parallel processes – OCR of scanned rolls is
    CPU bound (several seconds per page) so this scales almost linearly.
    ``progress(done_pages, total_pages)`` is invoked as pages complete.
    """
    path = Path(path)
    with pymupdf.open(path) as doc:
        page_count = doc.page_count
        # Do not silently publish an empty index for an image-only roll.  This
        # used to mark scanned PDFs as successfully indexed with zero records
        # when the Tesseract executable was missing, which is much harder for
        # an administrator to diagnose than an explicit indexing error.
        needs_ocr = config.OCR_ENABLED and any(
            len(page.get_text().strip()) < config.OCR_MIN_TEXT_CHARS for page in doc
        )
    if needs_ocr and not _ocr_tesseract_version():
        raise RuntimeError(
            "This PDF contains scanned pages, but Tesseract OCR is not installed "
            "or is not available on PATH. Install Tesseract, restart the server, "
            "and rebuild the index."
        )
    jobs = [(str(path), i) for i in range(page_count)]
    results: list[tuple[int, str, bool, list[dict]]] = []

    if workers <= 1 or page_count <= 1:
        for i, job in enumerate(jobs):
            results.append(_parse_page_job(job))
            if progress:
                progress(i + 1, page_count)
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(max_workers=min(workers, page_count)) as pool:
            futures = [pool.submit(_parse_page_job, job) for job in jobs]
            for n, fut in enumerate(as_completed(futures)):
                results.append(fut.result())
                if progress:
                    progress(n + 1, page_count)

    results.sort(key=lambda r: r[0])
    # Marathi OCR remains authoritative for names. Re-read only pages whose
    # printed serial interval conflicts with the populated pages on both sides.
    # This handles full pages, sparse one-card pages, official page sizes, and
    # a completely missed card without assuming serial == extracted row count.
    if recover_serials:
        for index, (page_no, _, used_ocr, rows) in enumerate(results):
            if not used_ocr or not rows:
                continue
            expected = _neighbour_expected(results, index)
            if not expected:
                continue
            actual = _numeric_serials(rows)
            if (len(actual) != len(rows) or len(actual) != len(set(actual))
                    or set(actual) != expected or len(rows) != len(expected)):
                _recover_page_serials(path, page_no, rows, expected)
    records: list[VoterRecord] = []
    ocr_pages = 0
    part_hint = ""
    for page_no, part, used_ocr, rows in results:
        if part:
            part_hint = part
        if used_ocr:
            ocr_pages += 1
        for row in rows:
            if not row.get("part"):
                row["part"] = part_hint
            records.append(VoterRecord(**row))
    return PdfParseResult(path=str(path), pages=page_count, records=records, ocr_pages=ocr_pages, part=part_hint)


def pdf_page_count(path: str | Path) -> int:
    try:
        with pymupdf.open(path) as doc:
            return doc.page_count
    except Exception:
        return 0
