"""AI Query Parser.

Turns natural language such as

    "Find Vijay whose father is Bharat"
    "show pratapsinh bharat jadhav"
    "MH/12/345/678901"

into a :class:`SearchQuery`.  Two layers:

1. **Rule based parser** – instant, offline, handles the vast majority of
   queries (names, EPIC numbers, "father is X", "husband X", "part 12", …).
2. **LLM parser** – optional, only used for longer conversational queries
   that the rules cannot confidently structure.  It receives *only* the user
   sentence and returns JSON filters.  It never sees PDFs or voter data.

Both paths are pure functions of the query text.
"""
from __future__ import annotations

import json
import logging
import re

from .. import config
from ..core.text_utils import EPIC_RE, normalize, normalize_epic
from ..search_engine.query import SearchQuery

log = logging.getLogger(__name__)

STOPWORDS = {
    "find", "search", "show", "me", "get", "look", "up", "for", "the", "a", "an", "of", "please", "voter",
    "voters", "named", "name", "called", "who", "whose", "with", "is", "are", "in", "list", "record", "records",
    "details", "detail", "person", "people", "any", "all", "give", "display", "and", "electoral", "roll",
    "epic", "number", "no", "id", "card", "having", "has", "have", "that", "this", "someone", "anyone",
    "i", "am", "im", "we", "you", "my", "our", "his", "her", "their", "looking", "want", "need", "can", "could",
    "would", "like", "to", "know", "tell", "about", "there", "where", "what", "which", "from", "village", "ward",
    "booth", "pdf", "file", "kindly", "pls", "plz", "hey", "hi", "hello", "ok", "okay", "also", "or", "but", "he", "she",
    "it", "lives", "living", "staying", "stays", "resident", "as", "by", "at", "on", "be", "been", "was", "were",
    "named", "mr", "mrs", "ms", "shri", "smt", "sau", "kumari", "shree",
}
RELATION_WORDS = r"(?:father|husband|dad|papa|mother|wife|guardian|spouse|parent)"
RELATION_PATTERNS = [
    # "whose father is Bharat", "father's name Bharat", "father Bharat Jadhav"
    re.compile(rf"(?:whose\s+)?{RELATION_WORDS}(?:'?s)?(?:\s+name)?\s*(?:is|=|:|-|named|called)?\s+([a-z][a-z .]*?)(?=\s+(?:and|with|in|from|part|page|epic|whose|aged?|age)\b|[,;]|$)", re.I),
    # "son of Bharat", "daughter of Bharat", "wife of Vijay", "w/o Vijay", "s/o Bharat"
    re.compile(r"(?:son|daughter|wife|child)\s+of\s+([a-z][a-z .]*?)(?=\s+(?:and|with|in|from|part|page|epic|whose)\b|[,;]|$)", re.I),
    re.compile(r"\b[sdwch]/o\.?\s+([a-z][a-z .]*?)(?=\s+(?:and|with|in|from|part|page|epic|whose)\b|[,;]|$)", re.I),
]
PART_PATTERN = re.compile(r"\bpart\s*(?:no|number)?\.?\s*[:#]?\s*(\d{1,4})\b", re.I)
PAGE_PATTERN = re.compile(r"\bpage\s*(?:no|number)?\.?\s*[:#]?\s*(\d{1,4})\b", re.I)
AGE_PATTERN = re.compile(r"\b(?:aged?|age\s*(?:is|of|=|:)?)\s*(\d{1,3})\b", re.I)
GENDER_PATTERN = re.compile(r"\b(male|female|man|woman|men|women|lady|gent|third gender|transgender)\b", re.I)
PDF_PATTERN = re.compile(r"\b(?:in|from|file|pdf)\s+([\w\- ]+\.pdf)\b", re.I)
CONVERSATIONAL_HINT = re.compile(r"\b(whose|who|is|are|find|show|search|with|named|called|of|from|in|has|having|that)\b", re.I)


def _strip_stopwords(text: str) -> str:
    return " ".join(t for t in text.split() if t not in STOPWORDS)


# ----------------------------------------------------------------------------
# Rule based parser
# ----------------------------------------------------------------------------
def parse_rules(text: str) -> SearchQuery:
    q = SearchQuery(raw=text, source="rules")
    working = text.strip()

    # EPIC numbers ------------------------------------------------------
    m = EPIC_RE.search(working.upper())
    if m:
        q.epic = normalize_epic(m.group(1))
        working = working[: m.start()] + " " + working[m.end():]
    else:
        # Slightly relaxed: ABC 1234567 or abc1234567 anywhere in text
        m2 = re.search(r"\b([A-Za-z]{3}\s?\d{7})\b", working)
        if m2:
            q.epic = normalize_epic(m2.group(1))
            working = working.replace(m2.group(1), " ")

    # Explicit filters ---------------------------------------------------
    m = PDF_PATTERN.search(working)
    if m:
        q.pdf = m.group(1).strip()
        working = working.replace(m.group(0), " ")
    m = PART_PATTERN.search(working)
    if m:
        q.part = m.group(1)
        working = working.replace(m.group(0), " ")
    m = PAGE_PATTERN.search(working)
    if m:
        q.page = int(m.group(1))
        working = working.replace(m.group(0), " ")
    m = AGE_PATTERN.search(working)
    if m:
        q.age = int(m.group(1))
        working = working.replace(m.group(0), " ")
    m = GENDER_PATTERN.search(working)
    if m:
        g = m.group(1).lower()
        q.gender = "Female" if g in {"female", "woman", "women", "lady"} else "Third Gender" if g in {"third gender", "transgender"} else "Male"
        working = working.replace(m.group(0), " ")

    # Relation -----------------------------------------------------------
    for pattern in RELATION_PATTERNS:
        m = pattern.search(working)
        if m:
            rel = _strip_stopwords(normalize(m.group(1)))
            if rel:
                q.relation_name = rel
                working = working[: m.start()] + " " + working[m.end():]
                break

    # Whatever remains is the voter name ----------------------------------
    rest = _strip_stopwords(normalize(working))
    rest = re.sub(r"\b\d+\b", " ", rest).strip()  # stray numbers are not names
    rest = re.sub(r"\s+", " ", rest)
    if rest:
        if q.relation_name:
            q.name = rest
        else:
            # Plain "Vinayshree Bharat Jadhav" – could match name or relation field
            q.any_text = rest
    return q


# ----------------------------------------------------------------------------
# LLM parser (optional)
# ----------------------------------------------------------------------------
_SYSTEM_PROMPT = """You convert a user's request about an Indian electoral roll into JSON search filters.
Return ONLY a JSON object with these optional keys:
  name            - voter's own name (partial allowed)
  relation_name   - father's / husband's / mother's name
  epic            - EPIC / voter id (letters+digits)
  part            - part number (string)
  page            - page number (integer)
  gender          - "Male" | "Female" | "Third Gender"
  age             - integer
  pdf             - pdf file name if mentioned
Do not invent values. Use empty string / omit when unknown. No prose."""


def _llm_available() -> bool:
    return bool(config.LLM_ENABLED and config.LLM_API_KEY)


def parse_llm(text: str) -> SearchQuery | None:
    if not _llm_available():
        return None
    try:
        import httpx  # via fastapi deps
    except Exception:  # pragma: no cover
        return None
    payload = {
        "model": config.LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    try:
        with httpx.Client(timeout=config.LLM_TIMEOUT) as client:
            resp = client.post(
                config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                json=payload,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        content = content.strip()
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
        data = json.loads(content)
    except Exception as exc:
        log.info("LLM parse unavailable (%s) – using rules", exc)
        return None

    q = SearchQuery(raw=text, source="llm")
    q.name = normalize(str(data.get("name") or ""))
    q.relation_name = normalize(str(data.get("relation_name") or ""))
    q.epic = normalize_epic(str(data.get("epic") or ""))
    q.part = str(data.get("part") or "").strip()
    q.pdf = str(data.get("pdf") or "").strip()
    q.gender = str(data.get("gender") or "").strip().title()
    try:
        q.page = int(data["page"]) if data.get("page") else None
    except (TypeError, ValueError):
        q.page = None
    try:
        q.age = int(data["age"]) if data.get("age") else None
    except (TypeError, ValueError):
        q.age = None
    return q if not q.is_empty() else None


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------
def parse_query(text: str, *, allow_llm: bool = True) -> SearchQuery:
    text = (text or "").strip()
    if not text:
        return SearchQuery(raw=text)
    rules = parse_rules(text)

    # Decide whether the sentence looks conversational enough to warrant the LLM.
    # Rules are instant; the LLM only runs for sentences the rules probably
    # mangled (long free text, or an implausibly long "name" leftover).
    word_count = len(text.split())
    conversational = bool(CONVERSATIONAL_HINT.search(text)) and word_count >= 4
    leftover = (rules.name or rules.any_text).split()
    unresolved = conversational and (
        rules.epic == "" and (not rules.relation_name or len(leftover) > 3 or word_count >= 8)
    )
    if allow_llm and unresolved and _llm_available():
        llm = parse_llm(text)
        if llm is not None:
            llm.notes.append("parsed by AI")
            return llm
    return rules
