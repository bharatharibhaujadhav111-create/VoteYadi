"""Devanagari / Marathi language intelligence.

Four problems make Marathi electoral-roll search fail in a system written for
English rolls.  This module solves each of them in one place, with no external
dependency (pure stdlib):

1. **Normalisation** – NFC, ZWJ/ZWNJ stripping, nukta removal (क़ → क) and
   chandrabindu → anusvara folding, so the many spellings an OCR engine emits
   for नाव / जाधव / घंदुरे collapse onto one comparable form.  Devanagari
   digits are folded to ASCII digits so "भाग ७" and "भाग 7" behave the same.
2. **Tokenisation/keys** – Devanagari is a *combining-script*: matras (ि ी ु ू े …)
   are separate code points that an ASCII `\\w+` tokenizer tears apart, and every
   Marathi word ends in one.  Keys are therefore built from the consonant
   "skeleton" with vowels dropped – which is also what makes OCR/bilingual
   spelling variants (जादव ≈ जाधव, Vijay ≈ Vijai) collide.
3. **Cross-script matching** – a query typed in Latin ("jadhav") must find a roll
   printed in Devanagari (जाधव) and vice versa.  ITRANS-style transliteration in
   both directions bridges the two scripts, both at index and at query time.
4. **OCR tolerance** – OCR of Marathi output confuses aspirates (ध↔द, भ↔ब …),
   sibilants (श/ष/स), dental/retroflex (त/ट, द/ड) and nasals (न/ण/ं).  The
   skeleton merges exactly those classes.

Nothing here mutates the original record text: records keep the script and
spelling the PDF contained, and the derived keys live alongside it.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# character classes
# ---------------------------------------------------------------------------
DEV_START, DEV_END = 0x0900, 0x097F
DEV_RANGE_RE = re.compile(r"[\u0900-\u097f]")
ZW_CHARS = "\u200b\u200c\u200d\u200e\u200f\u2060\ufeff"
NUKTA = "\u093c"
VIRAMA = "\u094d"
ANUSVARA = "\u0902"
CHANDRABINDU = "\u0901"
VISARGA = "\u0903"
AVAGRAHA = "\u093d"
DEV_DANDA = "\u0964\u0965"

CONSONANTS = "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहळ"
INDEP_VOWELS = "अआइईउऊऋॠएऐओऔऍऑ"
MATRA_TO_VOWEL = {
    "\u093e": "आ", "\u093f": "इ", "\u0940": "ई", "\u0941": "उ", "\u0942": "ऊ",
    "\u0943": "ऋ", "\u0947": "ए", "\u0948": "ऐ", "\u094b": "ओ", "\u094c": "औ",
    "\u0945": "ऍ", "\u0949": "ऑ",
}
VOWEL_TO_MATRA = {v: k for k, v in MATRA_TO_VOWEL.items()}

DEV_DIGITS = "०१२३४५६७८९"
DEV_TO_ASCII_DIGIT = {d: str(i) for i, d in enumerate(DEV_DIGITS)}
ASCII_TO_DEV_DIGIT = {str(i): d for i, d in enumerate(DEV_DIGITS)}
_DIGIT_TRANS = str.maketrans(DEV_TO_ASCII_DIGIT)

# OCR often turns Devanagari digits into look-alikes; fold the usual suspects
_DIGIT_REPAIR = {
    "9": "९", "०": "०", "o": "०", "O": "०", "5": "५", "I": "१", "l": "१", "|": "१",
}

# ---------------------------------------------------------------------------
# 1. normalisation
# ---------------------------------------------------------------------------
_WS_RE = re.compile(r"\s+")


def fold(text: str) -> str:
    """Canonical, comparable form of mixed Marathi/English text (matching only).

    NFC → strip zero-width joiners → drop nukta → chandrabindu→anusvara →
    drop avagraha → ऱ→र → danda→space → Devanagari digits→ASCII → collapse
    whitespace.  The *display* text of a record is never touched by this.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    for ch in ZW_CHARS:
        if ch in t:
            t = t.replace(ch, "")
    t = t.replace(NUKTA, "")                       # क़ → क, ड़ → ड, ज़ → ज
    t = t.replace(CHANDRABINDU, ANUSVARA)          # ँ → ं
    t = re.sub(r"[\u0951-\u0954]", "", t)          # Vedic accents
    t = t.replace(AVAGRAHA, "")
    t = t.replace("\u0931", "\u0930")              # ऱ → र
    t = t.replace("\u0934", "\u0933")              # ऴ → ळ
    t = re.sub("[" + DEV_DANDA + "]", " ", t)
    t = t.translate(_DIGIT_TRANS)
    t = t.replace("\u00a0", " ")
    return _WS_RE.sub(" ", t).strip()


normalize_devanagari = fold


def is_devanagari_char(ch: str) -> bool:
    return bool(ch) and DEV_START <= ord(ch) <= DEV_END


def has_devanagari(text: str) -> bool:
    return bool(text) and DEV_RANGE_RE.search(text) is not None


def devanagari_ratio(text: str) -> float:
    """Share of Devanagari letters among all letters in ``text`` (0..1)."""
    dev = lat = 0
    for ch in text or "":
        if is_devanagari_char(ch):
            dev += 1
        elif ch.isalpha() and ch.isascii():
            lat += 1
    total = dev + lat
    return (dev / total) if total else 0.0


def detect_script(text: str) -> str:
    """'devanagari' | 'latin' | 'mixed' | 'other' for one string."""
    r = devanagari_ratio(text)
    if r >= 0.85:
        return "devanagari"
    if r <= 0.15:
        return "latin" if (text or "").strip() else "other"
    return "mixed"


script_of = detect_script

# ---------------------------------------------------------------------------
# 2. consonant skeleton (the matching key)
# ---------------------------------------------------------------------------
# aspirates → plain, sibilants → स, dental/retroflex merged, nasals merged
# (English transliterations of Marathi names do not distinguish them: "Gade"
# is गाडे and "d"/"t" stand for both द/ड and त/ट).
_CLASS = {
    "क": "क", "ख": "क", "ग": "ग", "घ": "ग", "ङ": "न",
    "च": "च", "छ": "च", "ज": "ज", "झ": "ज", "ञ": "न",
    "ट": "त", "ठ": "त", "ड": "द", "ढ": "द", "ण": "न",
    "त": "त", "थ": "त", "द": "द", "ध": "द", "न": "न",
    "प": "प", "फ": "प", "ब": "ब", "भ": "ब", "म": "म",
    "य": "य", "र": "र", "ल": "ल", "ळ": "ल", "व": "व",
    "श": "स", "ष": "स", "स": "स", "ह": "ह",
    ANUSVARA: "न", CHANDRABINDU: "न", VISARGA: "ह",
}
_DOUBLE_RE = re.compile(r"(.)\1+")
# consonants used when deciding "is this Latin token Marathi-shaped?"
_ROMAN_CONSONANT_LETTERS = set("bcdfghjklmnpqrstvwxyz")


def skeleton_char(ch: str) -> str:
    """Consonant class of a codepoint, or '' for vowels/matras/marks."""
    return _CLASS.get(ch, "")


def dev_skeleton(token: str, nasal_blind: bool = False) -> str:
    """Consonant skeleton of a Devanagari token (vowels/matras dropped).

    ``nasal_blind`` folds म to the generic nasal class as well.  Marathi writes
    the same name with a full nasal (तांबोळी, रामचंद्र) or an anusvara
    (टांबोळी), and a Latin query cannot say which – so both skeletons are
    indexed and a hit on either counts.
    """
    t = fold(token)
    s = "".join(skeleton_char(ch) for ch in t)
    if nasal_blind:
        s = s.replace("म", "न")
    return _DOUBLE_RE.sub(r"\1", s)


def text_skeleton(text: str, nasal_blind: bool = False) -> str:
    """Skeleton for a full name, whichever script it is written in.

    Latin text is first transliterated to Devanagari so that "jadhav" and
    "जाधव" produce the same key (जदव).  Tokens are joined without separator so
    word boundaries in the query and the record need not line up.
    """
    t = fold(text)
    if not t:
        return ""
    if has_devanagari(t):
        parts = [dev_skeleton(tok, nasal_blind) for tok in t.split() if tok]
        return _DOUBLE_RE.sub(r"\1", "".join(parts))
    # Latin: transliterate token by token, keep digits as-is
    out = []
    for tok in t.split():
        out.append(dev_skeleton(roman_to_devanagari(tok), nasal_blind))
    return _DOUBLE_RE.sub(r"\1", "".join(out))

# ---------------------------------------------------------------------------
# 3. transliteration (Latin ⇄ Devanagari)
# ---------------------------------------------------------------------------
# Roman→Devanagari units. Longest match wins, so 3-letter clusters come first.
_ROMAN_CONS = [
    ("kshh", "क्ष"), ("ksh", "क्ष"), ("dny", "ज्ञ"), ("gny", "ज्ञ"), ("jny", "ज्ञ"),
    ("chh", "छ"), ("ch", "च"), ("cch", "च"), ("shh", "ष"), ("sch", "श"),
    ("kh", "ख"), ("gh", "घ"), ("jh", "झ"), ("th", "थ"), ("dh", "ध"), ("ph", "फ"),
    ("bh", "भ"), ("sh", "श"), ("ss", "ष"), ("zh", "ळ"), ("ll", "ळ"), ("tt", "ट"),
    ("dd", "ड"), ("nn", "ण"), ("rr", "र"), ("yy", "य"), ("vv", "व"), ("mm", "म"),
    ("ck", "क"), ("ks", "क्स"), ("gn", "ज्ञ"), ("ng", "ंग"), ("nk", "ंक"),
    ("k", "क"), ("q", "क"), ("g", "ग"), ("j", "ज"), ("z", "ज"),
    ("t", "त"), ("d", "द"), ("n", "न"), ("p", "प"), ("f", "फ"), ("b", "ब"),
    ("m", "म"), ("y", "य"), ("r", "र"), ("l", "ल"), ("v", "व"), ("w", "व"),
    ("s", "स"), ("h", "ह"), ("c", "च"), ("x", "क्स"),
]
_ROMAN_VOWELS = [
    ("aa", "\u0906"), ("ai", "\u0910"), ("au", "\u0914"), ("ea", "\u0908"),
    ("ee", "\u0908"), ("ei", "\u0910"), ("ii", "\u0908"), ("oa", "\u0913"),
    ("oo", "\u090a"), ("ou", "\u090a"), ("uu", "\u0909"), ("ue", "\u0909"),
    ("a", "\u0905"), ("i", "\u0907"), ("u", "\u0909"), ("e", "\u090f"), ("o", "\u0913"),
]
_ROMAN_VOWEL_LETTERS = set("aeiou")
_NASALS = {"न", "म"}  # → anusvara before another consonant (शिंदे, घंदुरे)


def roman_to_devanagari(token: str) -> str:
    """ITRANS-style transliteration of one Latin token ("jadhav" → जधव).

    Marathi rolls are printed with an implicit final vowel (Jadhav = जाधव), so a
    trailing consonant is left without a virama, and a nasal immediately followed
    by a consonant becomes anusvara – exactly how the rolls are typeset.
    """
    t = (token or "").lower()
    if not t or has_devanagari(t):
        return token or ""
    units: list[tuple[str, str]] = []  # ("C"|"V", devanagari)
    i = 0
    while i < len(t):
        ch = t[i]
        if ch in _ROMAN_VOWEL_LETTERS:
            for seq, dev in _ROMAN_VOWELS:
                if t.startswith(seq, i):
                    units.append(("V", dev))
                    i += len(seq)
                    break
            else:
                i += 1
            continue
        for seq, dev in _ROMAN_CONS:
            if t.startswith(seq, i):
                units.append(("C", dev))
                i += len(seq)
                break
        else:
            i += 1  # digits / punctuation / unknown letters are skipped
    out: list[str] = []
    for k, (typ, devc) in enumerate(units):
        nxt = units[k + 1] if k + 1 < len(units) else None
        if typ == "V":
            prev = units[k - 1] if k else None
            if prev is None or prev[0] == "V":
                out.append(devc)  # independent vowel
            continue
        if nxt is None:
            out.append(devc)  # word-final consonant: implicit vowel (Marathi style)
        elif nxt[0] == "C":
            if devc in _NASALS:
                out.append(devc + ANUSVARA)  # श + ि + ं + द + े
            else:
                out.append(devc + VIRAMA)
        else:
            if nxt[1] == "अ":
                out.append(devc)
            else:
                out.append(devc + VOWEL_TO_MATRA.get(nxt[1], ""))
    return "".join(out)


_DEV_TO_ROMAN = [
    ("\u0915\u094d\u0937", "ksh"), ("\u091c\u094d\u091e", "dny"), ("\u0924\u094d\u0930", "tr"),
    ("\u0936\u094d\u0930", "shr"), ("\u092a\u094d\u0930", "pr"),
    ("\u0915", "k"), ("\u0916", "kh"), ("\u0917", "g"), ("\u0918", "gh"), ("\u0919", "ng"),
    ("\u091a", "ch"), ("\u091b", "chh"), ("\u091c", "j"), ("\u091d", "jh"), ("\u091e", "ny"),
    ("\u091f", "t"), ("\u0920", "th"), ("\u0921", "d"), ("\u0922", "dh"), ("\u0923", "n"),
    ("\u0924", "t"), ("\u0925", "th"), ("\u0926", "d"), ("\u0927", "dh"), ("\u0928", "n"),
    ("\u092a", "p"), ("\u092b", "ph"), ("\u092c", "b"), ("\u092d", "bh"), ("\u092e", "m"),
    ("\u092f", "y"), ("\u0930", "r"), ("\u0932", "l"), ("\u0933", "l"), ("\u0935", "v"),
    ("\u0936", "sh"), ("\u0937", "sh"), ("\u0938", "s"), ("\u0939", "h"),
    ("\u0905", "a"), ("\u0906", "a"), ("\u0907", "i"), ("\u0908", "i"), ("\u0909", "u"),
    ("\u090a", "u"), ("\u090b", "ru"), ("\u090f", "e"), ("\u0910", "ai"),
    ("\u0913", "o"), ("\u0914", "au"),
]
_DEV_TO_ROMAN_CLUSTERS = {"\u0915\u094d\u0937", "\u091c\u094d\u091e", "\u0924\u094d\u0930",
                          "\u0936\u094d\u0930", "\u092a\u094d\u0930"}


def devanagari_to_roman(token: str) -> str:
    """Romanise a Devanagari token the way ECI rolls spell it (जाधव → jadhav)."""
    t = fold(token)
    if not t or not has_devanagari(t):
        return token or ""
    out: list[str] = []
    i = 0
    while i < len(t):
        ch = t[i]
        if ch.isspace():
            out.append(ch)
            i += 1
            continue
        matched = None
        for seq, rom in _DEV_TO_ROMAN:
            if t.startswith(seq, i):
                matched = (seq, rom)
                break
        if matched is None:
            if ch == ANUSVARA:
                out.append("n")
            elif ch == VISARGA:
                out.append("h")
            elif ch in MATRA_TO_VOWEL:
                out.append(devanagari_to_roman(MATRA_TO_VOWEL[ch]))
            i += 1
            continue
        seq, rom = matched
        out.append(rom)
        nxt = t[i + len(seq)] if i + len(seq) < len(t) else None
        if seq in CONSONANTS or seq in _DEV_TO_ROMAN_CLUSTERS:
            # A consonant carries its inherent "a" unless a matra or virama follows.
            # जाधव -> ja-dh-av? no: ज+ा -> "ja", ध+व -> "dh", final व -> "va" = jadhav
            if nxt is None:
                out.append("a")                        # final व -> va  (Jadhav)
            elif nxt == ANUSVARA:
                out.append("a")                        # घ+ं -> gha+n (Ghandure)
            elif nxt in MATRA_TO_VOWEL or nxt == VIRAMA:
                pass                                   # matra / virama: no inherent vowel
            elif is_devanagari_char(nxt):
                after = t[i + len(seq) + 1] if i + len(seq) + 1 < len(t) else None
                if after != VIRAMA and after != "\u093c":  # not a conjunct (क्+त)
                    out.append("a")                    # जा-ध-व  ->  ja-dha-va
            else:
                out.append("a")                        # followed by digit / space
        i += len(seq)
    return "".join(out)


_DEV_TO_ROMAN_CLUSTERS = {"क्ष", "ज्ञ", "त्र", "श्र", "प्र"}


def to_devanagari_text(text: str) -> str:
    """Transliterate a whole Latin string to Devanagari (best effort)."""
    if not text:
        return ""
    if has_devanagari(text):
        return text
    return " ".join(roman_to_devanagari(tok) if tok.isalpha() else tok for tok in text.split())


def to_roman_text(text: str) -> str:
    """Transliterate a whole Devanagari string to Latin (best effort)."""
    if not text or not has_devanagari(text):
        return ""
    return " ".join(devanagari_to_roman(tok) for tok in text.split())

# ---------------------------------------------------------------------------
# 4. OCR clean-up for Marathi output
# ---------------------------------------------------------------------------
_STRAY_LATIN = re.compile(r"(?<=[\u0900-\u097f])[A-Za-z]{1,2}(?=$|[\s:,])")
_LONE_MATRA = re.compile(r"(^|\s)[\u093e-\u094c\u094d](?=\s|$)")


def repair_line(text: str) -> str:
    """Remove the junk an OCR pass leaves inside Marathi words.

    Marathi rolls put Latin text only in the EPIC/serial/part numbers, so a
    stray Latin letter attached to a Devanagari word (जाधवq, शिवाजीm) is noise.
    """
    if not text or not has_devanagari(text):
        return text
    t = text
    t = _STRAY_LATIN.sub("", t)
    t = _LONE_MATRA.sub(r"\1", t)
    t = re.sub(r"[\u0966-\u096f]{0,1}[|]{1,}", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# Words that appear on every Marathi roll page and must not be read as names.
MARATHI_LABEL_WORDS = (
    "नाव", "नाम", "वडिलांचे", "वडिलाचे", "वडील", "पतीचे", "पती", "आईचे", "आई",
    "पित्याचे", "पिता", "मातेचे", "माता", "गृह", "क्रमांक", "घर", "वय", "लिंग",
    "मतदार", "ओळखपत्र", "अनुक्रमांक", "भाग", "विभाग", "पान", "मतदान", "केंद्र",
    "अनुसूचित", "जात", "प्रकार", "छायाचित्र", "उपलब्ध", "यादी", "गाव", "तालुका",
    "जिल्हा", "विधानसभा", "मतदारसंघ", "एकूण", "पुरुष", "स्त्री", "इतर", "अन्य",
)
MARATHI_LABEL_SET = set(MARATHI_LABEL_WORDS)


def is_label_word(token: str) -> bool:
    return token in MARATHI_LABEL_SET or fold(token) in MARATHI_LABEL_SET
