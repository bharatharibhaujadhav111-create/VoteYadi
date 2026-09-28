"""Marathi language layer: labels, honorifics, relation words, page profiles.

Kept separate from ``devanagari.py`` (which is pure script mechanics) so the
language data – the words that actually appear on a Maharashtra electoral roll –
is reviewable in one place.
"""
from __future__ import annotations

from . import devanagari as dev

# ---------------------------------------------------------------------------
# honourifics / prefixes and suffixes seen on roll pages and in queries
# ---------------------------------------------------------------------------
HONORIFICS = (
    "श्री", "श्रीमती", "श्रीमान", "सौ", "कु", "कुमारी", "डॉ", "डाॅ", "अॅड", "ॲड",
    "प्रो", "प्रा", "मे", "पद्मश्री", "माननीय", "श्रीयुत", "जनाब", "सेठ",
    "mr", "mrs", "ms", "shri", "smt", "dr", "late",
)

# ---------------------------------------------------------------------------
# relation words  →  relation_type
# ---------------------------------------------------------------------------
RELATION_WORDS: dict[str, str] = {
    # father
    "वडिलांचे": "father", "वडिलाचे": "father", "वडील": "father", "वडिल": "father",
    "पित्याचे": "father", "पिताचे": "father", "पिता": "father", "जनकाचे": "father",
    "बापाचे": "father",
    # husband
    "पतीचे": "husband", "पतीचा": "husband", "पती": "husband", "पतिचे": "husband",
    # mother
    "आईचे": "mother", "आईचा": "mother", "आई": "mother", "मातेचे": "mother", "माता": "mother",
    # wife  / guardian / other
    "पत्नीचे": "wife", "पत्नी": "wife",
    "पालकाचे": "other", "पालक": "other", "इतराचे": "other", "इतर": "other", "अन्य": "other",
}

# ---------------------------------------------------------------------------
# field labels – must never be read as part of a person's name
# ---------------------------------------------------------------------------
FIELD_LABELS: tuple[str, ...] = (
    "नाव", "नाम", "नावे", "वडिलांचे", "वडिलाचे", "पतीचे", "आईचे", "मातेचे",
    "घर", "क्रमांक", "गृह", "वय", "लिंग", "मतदार", "मतदान", "मतदारसंघ",
    "ओळखपत्र", "ओळख", "अनुक्रमांक", "क्र", "अनु", "भाग", "विभाग", "पान",
    "यादी", "गाव", "तालुका", "जिल्हा", "विधानसभा", "संपूर्ण", "फोटो", "छायाचित्र",
    "उपलब्ध", "उपलब्धता", "पुरुष", "स्त्री", "महिला", "इतर", "अन्य", "एकूण",
    "अनुसूचित", "जात", "प्रकार", "जन्म", "तारीख", "दिनांक", "वर्ष", "जुना",
    "नवीन", "बदल", "केलेला", "सुधारित", "मसुदा", "प्रारूप", "अंतर्भूत", "सलग",
    "खालील", "वर", "आणि", "किंवा", "ही", "हा", "हे", "या", "ते", "सर्व",
    "नंबर", "नं", "नो", "address", "photo", "available", "elector", "name",
)
FIELD_LABEL_SET = set(FIELD_LABELS)

# words that only ever appear as labels in *English* Marathi-transliterated rolls
EN_FIELD_LABELS: tuple[str, ...] = (
    "name", "father", "husband", "mother", "wife", "other", "house", "number",
    "age", "gender", "sex", "male", "female", "third", "part", "section",
    "assembly", "constituency", "photo", "available", "not", "elector",
    "electoral", "roll", "draft", "published", "village", "taluka", "district",
    "serial", "epic", "no", "sr", "and", "of", "the", "card", "identity",
)

# connector / question words that end a name span in a Marathi sentence
CONNECTORS = {
    "असलेल्या", "असलेला", "असलेले", "असलेल्याचे", "असलेल्यांचे", "यांचे", "यांचा", "याचे", "याचा",
    "म्हणजे", "नावाच्या", "नावाचा", "व", "आणि", "किंवा", "आहे", "आहेत", "हवा", "हवे", "पाहिजे",
    "शोधा", "दाखवा", "दाखव", "कोण", "कोणाचे", "सांगा", "पहा", "चा", "चे", "ची", "ला", "ना",
    "whose", "where", "and", "the", "of", "with", "show", "find", "search", "me", "for",
}
HONORIFIC_FOLDED = {dev.fold(h) for h in HONORIFICS}

GENDER_MAP: dict[str, str] = {
    "पुरुष": "Male", "पु": "Male", "male": "Male", "m": "Male",
    "स्त्री": "Female", "महिला": "Female", "स्त्र": "Female", "female": "Female", "f": "Female",
    "इतर": "Third Gender", "अन्य": "Third Gender", "third": "Third Gender", "t": "Third Gender",
}


def strip_honorifics(text: str) -> str:
    """Remove श्री / श्रीमती / डॉ … from the front of a name."""
    t = dev.fold(text or "").strip(" .:-")
    if not t:
        return ""
    changed = True
    while changed:
        changed = False
        for h in HONORIFICS:
            hf = dev.fold(h)
            if not hf:
                continue
            low = t.lower()
            if low.startswith(hf + " ") or low.startswith(hf + "."):
                t = t[len(hf):].lstrip(" .").strip()
                changed = True
                break
    return t


def clean_name(text: str) -> str:
    """Drop labels/honourifics/junk, keep the person's name only."""
    t = strip_honorifics(dev.repair_line(text or ""))
    if not t:
        return ""
    out: list[str] = []
    for tok in t.split():
        bare = tok.strip(" .,:;-|/_()[]'\"")
        if not bare:
            continue
        if bare.isdigit():
            continue  # serial/house OCR leaked into the person's name
        folded = dev.fold(bare)
        if folded in FIELD_LABEL_SET or folded in HONORIFIC_FOLDED or bare.lower() in EN_FIELD_LABELS:
            continue
        if len(bare) == 1 and not bare.isdigit():
            continue  # lone OCR debris
        out.append(bare)
    return " ".join(out).strip(" .,:;-|")


def relation_type_of(word: str) -> str:
    w = (word or "").strip(" .:")
    if w in RELATION_WORDS:
        return RELATION_WORDS[w]
    folded = dev.fold(w)
    for k, v in RELATION_WORDS.items():
        if dev.fold(k) == folded:
            return v
    return ""


def is_label(word: str) -> bool:
    w = (word or "").strip(" .,:")
    return w in FIELD_LABEL_SET or dev.fold(w) in FIELD_LABEL_SET or w.lower() in EN_FIELD_LABELS


# ---------------------------------------------------------------------------
# page profiling: which OCR language should this page be read with?
# ---------------------------------------------------------------------------
def page_profile(text: str) -> dict:
    """Decide the OCR language(s) and report the script mix of a page."""
    letters_dev = letters_lat = 0
    for ch in text or "":
        if dev.is_devanagari_char(ch) and ch.isalpha():
            letters_dev += 1
        elif ch.isascii() and ch.isalpha():
            letters_lat += 1
    total = letters_dev + letters_lat
    ratio = (letters_dev / total) if total else 0.0
    if ratio >= 0.45:
        script, lang = "devanagari", "mar+eng"
    elif ratio <= 0.02:
        script, lang = "latin", "eng"
    else:
        script, lang = "mixed", "mar+eng"
    return {
        "script": script,
        "devanagari_ratio": round(ratio, 4),
        "devanagari_letters": letters_dev,
        "latin_letters": letters_lat,
        "suggested_lang": lang,
    }


# ---------------------------------------------------------------------------
# Marathi natural-language query parsing
# ---------------------------------------------------------------------------
def parse_marathi_query(text: str) -> dict:
    """Pull a name / relative's name out of a Marathi sentence.

    ``"वडिलांचे नाव भारत असलेल्या विजय जाधव"`` → name "विजय जाधव",
    relation "भारत".  Labels and question words are dropped, honourifics
    stripped, and the leftover words kept as ``remaining`` for free-text search.
    """
    t = dev.fold(text or "").strip()
    result = {
        "name": "",
        "relation_name": "",
        "relation_type": "",
        "remaining": "",
        "honorifics": [],
        "is_marathi": bool(dev.has_devanagari(t)),
    }
    if not t:
        return result

    parts = [tok.strip(" .,:;?!()[]'\"|/") for tok in t.split()]
    parts = [tok for tok in parts if tok]
    n = len(parts)

    def is_labelish(tok: str) -> bool:
        return is_label(tok) or dev.fold(tok) in HONORIFIC_FOLDED

    skipped: set[int] = set()
    for i, tok in enumerate(parts):
        if is_labelish(tok):
            skipped.add(i)
            if dev.fold(tok) in HONORIFIC_FOLDED:
                result["honorifics"].append(tok)

    # "… वडिलांचे नाव भरत जाधव असलेल्या …" – the words after a relation label, up
    # to the next connector, are the relative's name and not the voter's.
    rel_words: list[str] = []
    for i, tok in enumerate(parts):
        rt = relation_type_of(tok)
        if not rt:
            continue
        result["relation_type"] = rt
        skipped.add(i)
        for j in range(i + 1, n):
            nxt = parts[j]
            if is_labelish(nxt):
                if rel_words:
                    break
                skipped.add(j)
                continue
            if nxt in CONNECTORS or relation_type_of(nxt):
                break
            rel_words.append(nxt)
            skipped.add(j)
        if rel_words:
            break
    result["relation_name"] = " ".join(rel_words)

    cleaned = []
    for i, tok in enumerate(parts):
        if i in skipped:
            continue
        if tok in CONNECTORS:
            continue
        if dev.fold(tok).isdigit() and len(tok) > 3:
            continue  # long digit strings are EPIC/serial, not names
        cleaned.append(tok)

    result["name"] = " ".join(cleaned).strip()
    if not result["name"]:
        result["remaining"] = " ".join(cleaned)
    return result


def romanize(value: str) -> str:
    """Latin spelling of a name for cross-script display/search."""
    if not value:
        return ""
    if dev.has_devanagari(value):
        return dev.to_roman_text(value)
    return value
