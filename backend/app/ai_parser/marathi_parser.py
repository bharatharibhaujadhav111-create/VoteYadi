"""Marathi-aware query parser.

Wraps the existing rule/LLM parser (:mod:`query_parser`) and adds what a
Devanagari query needs:

* the sentence is segmented by Marathi labels ("वडिलांचे नाव …", "भाग ७"),
* honourifics (श्री / श्रीमती / डॉ …) are stripped from both name fields,
* cross-script: a Latin sentence is left exactly as before, and a Marathi
  sentence that the base parser cannot read (because it only knows English
  labels) gets its name/relative extracted directly.

Every other endpoint that used ``query_parser.parse_query`` can import this
module instead – signature and return type are identical.
"""
from __future__ import annotations

import logging

from ..core import devanagari as dev
from ..core import marathi as mar
from .query_parser import parse_query as _base_parse_query

log = logging.getLogger(__name__)


def parse_query(q: str, allow_llm: bool = True):
    """Parse a query in Marathi, English or a mix of both."""
    parsed = _base_parse_query(q, allow_llm=allow_llm)
    text = (q or "").strip()
    if not text:
        return parsed

    if dev.has_devanagari(text):
        extracted = mar.parse_marathi_query(text)
        if extracted["name"] and (not parsed.name or not dev.has_devanagari(parsed.name)):
            parsed.name = extracted["name"]
        if extracted["relation_name"] and not parsed.relation_name:
            parsed.relation_name = extracted["relation_name"]
        if extracted["relation_type"] and not parsed.relation_type:
            parsed.relation_type = extracted["relation_type"]
        if not parsed.name and not parsed.relation_name and extracted.get("remaining"):
            parsed.any_text = parsed.any_text or extracted["remaining"]
        # Devanagari digits in the query ("भाग ७") behave like ASCII ones
        if parsed.part:
            parsed.part = parsed.part.translate(str.maketrans(dev.DEV_TO_ASCII_DIGIT))
        parsed.notes = list(parsed.notes) + ["marathi"]

    parsed.name = mar.strip_honorifics(parsed.name)
    parsed.relation_name = mar.strip_honorifics(parsed.relation_name)
    parsed.any_text = mar.strip_honorifics(parsed.any_text)
    return parsed
