"""Text normalisation helpers shared by the parser, index and search engine.

Script aware: English rolls (and Latin EPIC numbers) behave exactly as before,
while Marathi/Devanagari text keeps its letters and matras instead of being
folded away to nothing.  See ``core/devanagari.py`` for the language layer.
"""
from __future__ import annotations

import re

from . import devanagari as dev

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u0900-\u097f]+")
_MULTI_SPACE = re.compile(r"\s+")

# Older EPIC format:  ABC/12/345/678901   Newer format: ABC1234567
EPIC_RE = re.compile(r"\b([A-Z]{2,3}/\d{2}/\d{3}/\d{6}|[A-Z]{3}\d{7})\b")


def normalize(text: str) -> str:
    """Lowercase, NFC/Nukta-folded, whitespace-collapsed, script-preserving text.

    Latin: ``Vinayshree  Bharat-Jadhav`` → ``vinayshree bharat jadhav``.
    Marathi: ``विजयसिंह  जाधव`` → ``विजयसिंह जाधव`` (matras kept, no ASCII-only
    filtering – an ASCII regex would reduce a Marathi name to an empty string).
    """
    folded = dev.fold(text).lower()
    tokens = _TOKEN_RE.findall(folded)
    return _MULTI_SPACE.sub(" ", " ".join(tokens)).strip()


def tokenize(text: str) -> list[str]:
    return [t for t in normalize(text).split(" ") if t]


def normalize_epic(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", dev.fold(text or "").upper())


def phonetic_key(token: str, nasal_blind: bool = False) -> str:
    """Consonant skeleton of a token, script independent.

    ``jadhav``/``Jadav``/``जाधव`` → ``जदव``; ``Vinayshree`` → ``वनसर``.
    Latin tokens that carry no Marathi consonants fall back to the historic
    English-insensitive key so EPIC-ish junk still collides with itself.
    """
    t = normalize(token).replace(" ", "")
    if not t:
        return ""
    if t.isdigit():
        return t
    key = (
        dev.dev_skeleton(t, nasal_blind)
        if dev.has_devanagari(t)
        else dev.dev_skeleton(dev.roman_to_devanagari(t), nasal_blind)
    )
    if key:
        return key
    return _latin_phonetic_key(t)


def phonetic_keys(token: str) -> list[str]:
    """Every key a token should be findable under.

    Both script forms and both nasal readings (see ``dev.dev_skeleton``), plus
    the historic Latin-insensitive key for non-Marathi tokens.  The index stores
    all of them; a query hit on any one of them counts.
    """
    keys: list[str] = []
    for blind in (False, True):
        key = phonetic_key(token, nasal_blind=blind)
        if key and key not in keys:
            keys.append(key)
    t = normalize(token).replace(" ", "")
    if t and not dev.has_devanagari(t) and not t.isdigit():
        alt = _latin_phonetic_key(t)
        if alt and alt not in keys:
            keys.append(alt)
    return keys


# --- historic English-insensitive rules (kept for non-Marathi tokens) ---
_PHONETIC_RULES = [
    (re.compile(r"ph"), "f"),
    (re.compile(r"(bh|dh|gh|jh|kh|th|ch|sh)"),
     lambda m: {"bh": "b", "dh": "d", "gh": "g", "jh": "j", "kh": "k", "th": "t", "ch": "c", "sh": "s"}[m.group(1)]),
    (re.compile(r"ck"), "k"),
    (re.compile(r"q"), "k"),
    (re.compile(r"w"), "v"),
    (re.compile(r"z"), "j"),
    (re.compile(r"x"), "ks"),
    (re.compile(r"ee|ii|ea"), "i"),
    (re.compile(r"oo|ou"), "u"),
    (re.compile(r"ai|ay|ei|ey"), "e"),
    (re.compile(r"au|aw"), "o"),
    (re.compile(r"y"), "i"),
    (re.compile(r"ngh|nh"), "n"),
    (re.compile(r"h(?![aeiou])"), ""),
]
_DOUBLE = re.compile(r"(.)\1+")


def _latin_phonetic_key(t: str) -> str:
    for pattern, repl in _PHONETIC_RULES:
        t = pattern.sub(repl, t)  # type: ignore[arg-type]
    t = _DOUBLE.sub(r"\1", t)
    if len(t) > 1:
        head, tail = t[0], t[1:]
        tail = re.sub(r"[aeiou]+$", "", tail)
        tail = re.sub(r"[aeiou]", "", tail)
        t = head + tail
    return t


def variants_of(token: str) -> list[tuple[str, float]]:
    """Spelling equivalents of a typed token with a match weight.

    A Latin query also matches the Devanagari form of the same name and vice
    versa, which is what makes "jadhav" find जाधव and "जाधव" find "Jadhav".
    """
    out: list[tuple[str, float]] = [(token, 1.0)]
    t = normalize(token)
    if not t or t.isdigit():
        return out
    if dev.has_devanagari(t):
        roman = dev.devanagari_to_roman(t)
        if roman and roman != t:
            out.append((roman, 0.92))
    else:
        devw = dev.roman_to_devanagari(t)
        if devw and devw != t:
            out.append((devw, 0.92))
        # common transliteration doublets: v/w, y/i, double letters
        alt = t.replace("w", "v")
        if alt != t:
            out.append((alt, 0.95))
        alt2 = re.sub(r"(.)\1", r"\1", t)
        if alt2 != t:
            out.append((alt2, 0.95))
    dedup: list[tuple[str, float]] = []
    seen = set()
    for v, w in out:
        if v and v not in seen:
            seen.add(v)
            dedup.append((v, w))
    return dedup


def equivalent_word(token: str, words: set[str], keys: set[str]) -> bool:
    """Is ``token`` present in ``words`` exactly, as a prefix, cross-script or
    as a same-sounding spelling?  Used for the "every typed word matched" flag."""
    if not token:
        return False
    cands = [token] + [v for v, _ in variants_of(token)]
    for c in cands:
        if c in words:
            return True
        if len(c) >= 3 and any(w.startswith(c) for w in words):
            return True
    if len(token) >= 3:
        for k in phonetic_keys(token):
            if k in keys:
                return True
    return False


def romanize_value(value: str) -> str:
    """Latin spelling of any name, in either script (empty for empty input)."""
    if not value:
        return ""
    return dev.to_roman_text(value) if dev.has_devanagari(value) else value


def devanagari_to_roman(value: str) -> str:
    return dev.devanagari_to_roman(value) if dev.has_devanagari(value) else ""


def roman_to_devanagari(value: str) -> str:
    return dev.roman_to_devanagari(value) if value and not dev.has_devanagari(value) else value


def text_skeleton(value: str, nasal_blind: bool = False) -> str:
    """Consonant skeleton of a whole name, in either script.

    ``"jadhav"``/``"जाधव"`` -> the same key, which is what lets a Latin query and
    a Devanagari record be compared directly.
    """
    return dev.text_skeleton(value, nasal_blind) if value else ""


def text_skeletons(value: str) -> list[str]:
    """Skeleton of every 1..3-token prefix of a name, in *both* nasal readings.

    This is what makes a partial Indian name work: "jaya jadhav" reaches
    "जया भरत जाधव" without the middle name, and "रामचंद्र" matches "रामचंद्र"
    whether the roll printed a full nasal or an anusvara.
    """
    tokens = tokenize(value)
    out: list[str] = []
    for n in range(1, min(3, len(tokens)) + 1):
        prefix = " ".join(tokens[:n])
        for blind in (False, True):
            key = dev.text_skeleton(prefix, blind)
            if key and key not in out:
                out.append(key)
    return out
