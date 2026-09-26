"""In-memory search index + on-disk persistence.

Layout on disk (all derived data – delete the folder to force a full rebuild):

    index/
      meta.json                 version, status, timestamps, per-PDF fingerprints
      shards/<pdf>.json.gz      records extracted from one PDF
      index.pkl                 pickled in-memory structure for fast startup

The in-memory structure is columnar (lists of primitives) to keep millions of
records affordable.  Postings are ``array('I')`` of record ids.
"""
from __future__ import annotations

import bisect
import gzip
import json
import logging
import pickle
from array import array
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .. import config
from ..core import devanagari as dev
from ..core.text_utils import (
    devanagari_to_roman,
    normalize,
    normalize_epic,
    phonetic_key,
    phonetic_keys,
    text_skeletons,
    tokenize,
)

log = logging.getLogger(__name__)

INDEX_FORMAT = 6  # v6: Romanised Marathi tokens participate in normal prefix search


class SearchIndex:
    """Columnar record store with inverted / phonetic / prefix indexes."""

    def __init__(self) -> None:
        # columnar record data ------------------------------------------------
        self.pdf_names: list[str] = []          # pdf idx -> pdf id (relative path "Village/file.pdf")
        self.pdf_villages: list[str] = []       # pdf idx -> village ("" when unassigned)
        self.rec_pdf: array = array("I")        # record -> pdf idx
        self.village_records: dict[str, array] = {}  # village -> record ids
        self.rec_page: array = array("I")       # record -> page (1-based)
        self.rec_name: list[str] = []
        self.rec_relation: list[str] = []
        self.rec_relation_type: list[str] = []
        self.rec_epic: list[str] = []
        self.rec_serial: list[str] = []
        self.rec_part: list[str] = []
        self.rec_house: list[str] = []
        self.rec_age: list[str] = []
        self.rec_gender: list[str] = []
        # inverted indexes -------------------------------------------------------
        self.name_postings: dict[str, array] = {}
        self.rel_postings: dict[str, array] = {}
        self.name_phonetic: dict[str, list[str]] = {}   # phonetic key -> tokens
        self.rel_phonetic: dict[str, list[str]] = {}
        self.epic_lookup: dict[str, int] = {}
        self.name_vocab: list[str] = []                # sorted, for prefix lookups
        self.rel_vocab: list[str] = []
        self.name_freq: dict[str, int] = {}            # token -> occurrences (suggestions)
        self.full_name_freq: dict[str, int] = {}       # normalised full name -> count
        # --- Marathi / cross-script layer ------------------------------------
        self.rec_name_dev: list[str] = []         # romanisation of a Devanagari name
        self.rec_name_script: list[str] = []      # devanagari | latin | mixed | other
        self.rec_relation_roman: list[str] = []   # romanisation of a Devanagari relation
        self.name_postings_c: dict[str, array] = {}   # first-N-token skeleton -> rec ids
        self.rel_postings_c: dict[str, array] = {}
        self.alias_tokens: dict[str, str] = {}    # phonetic key -> best spelling in the corpus
        self.query_alias_hits: int = 0            # telemetry: queries rescued by the alias table

    # --- building ---------------------------------------------------------
    @classmethod
    def build(cls, shards: Iterable[tuple[str, list[dict]]]) -> "SearchIndex":
        idx = cls()
        name_post: dict[str, list[int]] = defaultdict(list)
        compound_post: dict[str, list[int]] = defaultdict(list)
        rel_post: dict[str, list[int]] = defaultdict(list)
        village_post: dict[str, list[int]] = defaultdict(list)
        for pdf_name, records in shards:
            pdf_id = len(idx.pdf_names)
            idx.pdf_names.append(pdf_name)
            village = pdf_name.split("/", 1)[0] if "/" in pdf_name else ""
            idx.pdf_villages.append(village)
            for r in records:
                rid = len(idx.rec_name)
                idx.rec_pdf.append(pdf_id)
                village_post[village].append(rid)
                idx.rec_page.append(int(r.get("page") or 1))
                name = r.get("name", "")
                rel = r.get("relation_name", "")
                idx.rec_name.append(name)
                idx.rec_relation.append(rel)
                idx.rec_relation_type.append(r.get("relation_type", ""))
                epic = normalize_epic(r.get("epic", ""))
                idx.rec_epic.append(epic)
                idx.rec_serial.append(str(r.get("serial", "")))
                idx.rec_part.append(str(r.get("part", "")))
                idx.rec_house.append(str(r.get("house", "")))
                idx.rec_age.append(str(r.get("age", "")))
                idx.rec_gender.append(str(r.get("gender", "")))
                # Marathi layer: keep the printed text, add a Romanised twin so a
                # Latin query ("jadhav") can reach a Devanagari record (जाधव).
                if dev.has_devanagari(name):
                    idx.rec_name_dev.append(devanagari_to_roman(name))
                    idx.rec_name_script.append("devanagari")
                elif dev.has_devanagari(rel):
                    idx.rec_name_dev.append("")
                    idx.rec_name_script.append("mixed")
                else:
                    idx.rec_name_dev.append("")
                    idx.rec_name_script.append("latin" if name.strip() else "other")
                idx.rec_relation_roman.append(
                    devanagari_to_roman(rel) if dev.has_devanagari(rel) else ""
                )
                if epic:
                    idx.epic_lookup[epic] = rid
                seen: set[str] = set()
                name_tokens = tokenize(name)
                if dev.has_devanagari(name):
                    name_tokens += tokenize(devanagari_to_roman(name))
                for tok in name_tokens:
                    if tok in seen:
                        continue
                    seen.add(tok)
                    name_post[tok].append(rid)
                    idx.name_freq[tok] = idx.name_freq.get(tok, 0) + 1
                seen.clear()
                relation_tokens = tokenize(rel)
                if dev.has_devanagari(rel):
                    relation_tokens += tokenize(devanagari_to_roman(rel))
                for tok in relation_tokens:
                    if tok in seen:
                        continue
                    seen.add(tok)
                    rel_post[tok].append(rid)
                nn = normalize(name)
                if nn:
                    idx.full_name_freq[nn] = idx.full_name_freq.get(nn, 0) + 1
                # "jaya jadhav" must also find "jaya bharat jadhav": index the
                # consonant skeleton of every 1..3-token prefix of the name.
                # "jaya jadhav" must also find "jaya bharat jadhav": index the
                # consonant skeleton of every 1..3-token prefix, in both nasal
                # readings (see text_skeletons).
                for key in text_skeletons(name):
                    compound_post[key].append(rid)

        idx.village_records = {k: array("I", v) for k, v in village_post.items()}
        idx.name_postings = {k: array("I", v) for k, v in name_post.items()}
        idx.rel_postings = {k: array("I", v) for k, v in rel_post.items()}
        idx.name_postings_c = {k: array("I", v) for k, v in compound_post.items()}
        idx.name_vocab = sorted(idx.name_postings)
        idx.rel_vocab = sorted(idx.rel_postings)
        # every token is filed under all of its phonetic keys (both scripts, both
        # nasal readings) so a query hit on any one of them retrieves the record
        ph_n: dict[str, list[str]] = defaultdict(list)
        for tok in idx.name_vocab:
            for key in phonetic_keys(tok):
                ph_n[key].append(tok)
        ph_r: dict[str, list[str]] = defaultdict(list)
        for tok in idx.rel_vocab:
            for key in phonetic_keys(tok):
                ph_r[key].append(tok)
        idx.name_phonetic = dict(ph_n)
        idx.rel_phonetic = dict(ph_r)
        # alias table: phonetic key -> the most frequent spelling of that name in
        # the corpus, in *either* script.  Lets "jadhav" seed जाधव directly.
        for tok, cnt in idx.name_freq.items():
            key = phonetic_key(tok)
            if not key or key.isdigit() or len(key) < 3:
                continue
            prev = idx.alias_tokens.get(key)
            if prev is None or idx.name_freq.get(prev, 0) < cnt:
                idx.alias_tokens[key] = tok
        for tok in idx.rel_vocab:
            key = phonetic_key(tok)
            if key and not key.isdigit() and len(key) >= 3 and key not in idx.alias_tokens:
                idx.alias_tokens[key] = tok
        for tok in idx.name_vocab:
            for key in phonetic_keys(tok):
                idx.alias_tokens.setdefault(key, tok)
        return idx

    # --- accessors --------------------------------------------------------
    def __len__(self) -> int:
        return len(self.rec_name)

    def record(self, rid: int) -> dict:
        return {
            "id": rid,
            "name": self.rec_name[rid],
            "relation_name": self.rec_relation[rid],
            "relation_type": self.rec_relation_type[rid],
            "epic": self.rec_epic[rid],
            "serial": self.rec_serial[rid],
            "part": self.rec_part[rid],
            "house": self.rec_house[rid],
            "age": self.rec_age[rid],
            "gender": self.rec_gender[rid],
            "page": self.rec_page[rid],
            "pdf": self.pdf_names[self.rec_pdf[rid]],
            "pdf_name": self.pdf_names[self.rec_pdf[rid]].rsplit("/", 1)[-1],
            "village": self.pdf_villages[self.rec_pdf[rid]],
            "name_dev": self.rec_name_dev[rid],
            "script": self.rec_name_script[rid] if rid < len(self.rec_name_script) else "",
        }

    # --- Marathi / cross-script helpers ----------------------------------
    def searchable_tokens(self, rid: int) -> list[str]:
        """Every spelling of a record's names: as printed, Romanised, cross-script.

        Used by the engine's exactness check, which then agrees with the
        phonetic index instead of rejecting a Thai-script hit as "partial".
        """
        out: list[str] = []
        seen: set[str] = set()
        for tok in tokenize(self.rec_name[rid]) + tokenize(self.rec_relation[rid]):
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
        if rid < len(self.rec_name_dev):
            for field in (self.rec_name_dev[rid], self.rec_relation_roman[rid]):
                for tok in tokenize(field):
                    if tok not in seen:
                        seen.add(tok)
                        out.append(tok)
        return out

    def alias_token_of(self, token: str) -> str:
        """The corpus spelling that sounds like ``token`` (either script)."""
        key = phonetic_key(token)
        if not key:
            return ""
        return self.alias_tokens.get(key, "")

    def matched_words(self, rid: int) -> set[str]:
        return set(self.searchable_tokens(rid))

    def village_counts(self) -> dict[str, int]:
        return {v: len(a) for v, a in self.village_records.items()}

    def prefix_tokens(self, vocab: list[str], prefix: str, limit: int) -> list[str]:
        if not prefix:
            return []
        lo = bisect.bisect_left(vocab, prefix)
        out: list[str] = []
        while lo < len(vocab) and len(out) < limit and vocab[lo].startswith(prefix):
            out.append(vocab[lo])
            lo += 1
        return out

    # --- persistence ------------------------------------------------------
    def save(self, path: Path) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump({"format": INDEX_FORMAT, "index": self}, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "SearchIndex | None":
        try:
            with open(path, "rb") as fh:
                payload = pickle.load(fh)
            if payload.get("format") != INDEX_FORMAT:
                return None
            idx = payload["index"]
            return idx if isinstance(idx, cls) else None
        except Exception as exc:  # corrupted / missing
            log.info("Could not load cached index (%s) – will rebuild from shards", exc)
            return None


# ----------------------------------------------------------------------------
# Shard persistence helpers
# ----------------------------------------------------------------------------
def shard_path(shards_dir: Path, pdf_name: str) -> Path:
    # pdf ids contain "/" for villages – flatten to a single file name
    return shards_dir / (pdf_name.replace("/", "__") + ".json.gz")


def write_shard(shards_dir: Path, pdf_name: str, payload: dict) -> None:
    shards_dir.mkdir(parents=True, exist_ok=True)
    tmp = shard_path(shards_dir, pdf_name).with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(shard_path(shards_dir, pdf_name))


def read_shard(shards_dir: Path, pdf_name: str) -> dict | None:
    p = shard_path(shards_dir, pdf_name)
    if not p.exists():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        log.warning("Corrupt shard %s: %s", p, exc)
        return None


def delete_shard(shards_dir: Path, pdf_name: str) -> None:
    shard_path(shards_dir, pdf_name).unlink(missing_ok=True)


def rename_shard(shards_dir: Path, old: str, new: str) -> bool:
    src = shard_path(shards_dir, old)
    if not src.exists():
        return False
    payload = read_shard(shards_dir, old)
    if payload is None:
        return False
    payload["pdf"] = new
    write_shard(shards_dir, new, payload)
    src.unlink(missing_ok=True)
    return True
