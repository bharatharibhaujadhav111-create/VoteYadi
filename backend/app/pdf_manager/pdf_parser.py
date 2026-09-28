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
    rf"^\s*(?!वडिल|वडील|वडिलां|पित|पती|आई|माते|माता|पत्नी|पालक|इतर|अन्य|जनक|बाप)"
    rf"[\u0900-\u097f]*\s*(?:नाव|नाम)\s*[:：\-–]?\s*(.+?)\s*$"
)
#  वडिलांचे नाव : भारत जाधव / पतीचे नाव : … / आईचे नाव : …
DEV_RELATION_RE = re.compile(
    rf"^\s*(वडिलांचे|वडिलाचे|वडिल|वडील|पित्याचे|पिताचे|पिता|जनकाचे|बापाचे|पतीचे|पतीचा|पती|"
    rf"आईचे|आईचा|आई|मातेचे|माता|पत्नीचे|पत्नी|पालकाचे|पालक|इतराचे|इतर|अन्य)"
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

COLUMN_GAP_PT = 28.0  # lines whose left edge differ by more than this start a new column


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


def _ocr_lines(page: pymupdf.Page, lang: str | None = None) -> list[Line]:
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
            img, lang=use_lang, config=f"--psm {config.OCR_PSM}", output_type=Output.DICT
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
        ordered.extend(l[2] for l in col)
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


def _recover_page_serials(path: Path, page_no: int, rows: list[dict], first_serial: int) -> bool:
    """Re-read suspect card numbers with both models, retaining Marathi names."""
    with pymupdf.open(path) as doc:
        bilingual = _ocr_lines(doc[page_no - 1], lang=f'{config.OCR_LANG_DEV}+{config.OCR_LANG or "eng"}')
    if not bilingual:
        return False
    other = parse_page_text(order_by_columns(bilingual), page_no).records
    if not _apply_verified_page_serials(rows, other, first_serial):
        return False
    log.info("Recovered %d serials on page %d using bilingual OCR", len(rows), page_no)
    return True


def _recover_missing_sequence_serials(rows: list[dict]) -> int:
    """Fill blank serials only when record order independently proves them.

    A normal electoral part is stored in serial order.  We require every
    serial OCR did read to equal that row's 1-based position before filling a
    blank.  A wrong, duplicated, shifted, or non-numeric value disables this
    recovery and leaves the quality gate to hold the PDF for review.
    """
    missing_positions: list[int] = []
    for position, row in enumerate(rows, start=1):
        value = str(row.get("serial") or "").strip()
        if not value:
            missing_positions.append(position)
            continue
        if not value.isdigit() or int(value) != position:
            return 0
    if not missing_positions:
        return 0
    for position in missing_positions:
        rows[position - 1]["serial"] = str(position)
    return len(missing_positions)


def parse_pdf(path: str | Path, *, workers: int = 1, progress: "Callable[[int, int], None] | None" = None) -> PdfParseResult:
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
    # Marathi-only OCR is best for names, but on some scans it confuses the
    # hundreds digit (955 -> 555) for a whole page. Re-read only pages whose
    # serials disagree with their position in the roll, never all pages.
    next_serial = 1
    for page_no, _, used_ocr, rows in results:
        if used_ocr and rows:
            expected = set(range(next_serial, next_serial + len(rows)))
            try:
                actual = {int(row["serial"]) for row in rows}
            except (ValueError, TypeError):
                actual = set()
            if actual != expected:
                _recover_page_serials(path, page_no, rows, next_serial)
        next_serial += len(rows)
    all_rows = [row for _, _, _, rows in results for row in rows]
    recovered = _recover_missing_sequence_serials(all_rows)
    if recovered:
        log.info("Inferred %d blank serial(s) from the complete roll sequence", recovered)
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
