"""Search Engine.

Executes a :class:`SearchQuery` against the in-memory :class:`SearchIndex`.
Never touches PDF files.

Matching strategy per query token (cheap → expensive, stops early when enough
candidates are found):

1. exact token            (``jadhav``)
2. prefix                 (``jad`` → ``jadhav``, ``jadav`` …)  – partial names
3. phonetic key           (``jadav`` ~ ``jadhav``, ``vijai`` ~ ``vijay``)
4. fuzzy (RapidFuzz)      (``vinayshri`` ~ ``vinayshree``)     – spelling mistakes

Candidate record sets are intersected (AND) and, when that yields nothing,
relaxed to a scored union (OR).  Final ranking uses RapidFuzz similarity of the
full names plus small boosts for exact / same-field matches.
"""
from __future__ import annotations

import time
from array import array
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from .. import config
from ..core.text_utils import (
    normalize,
    normalize_epic,
    phonetic_key,
    phonetic_keys,
    tokenize,
    variants_of,
)
from ..search_index.index_store import SearchIndex
from .query import SearchQuery


@dataclass
class SearchResponse:
    results: list[dict]
    total: int
    page: int
    page_size: int
    took_ms: float
    query: dict
    relaxed: bool = False
    suggestions: list[str] = field(default_factory=list)
    exact_match: bool = True                 # some result contains every typed word exactly
    unmatched_words: list[str] = field(default_factory=list)  # typed words found in no result

    def to_dict(self) -> dict:
        return {
            "results": self.results,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "took_ms": self.took_ms,
            "query": self.query,
            "relaxed": self.relaxed,
            "suggestions": self.suggestions,
            "exact_match": self.exact_match,
            "unmatched_words": self.unmatched_words,
        }



def _phonetic_lookup(groups: dict[str, list[str]], token: str) -> list[str]:
    """All corpus tokens filed under any phonetic key of ``token``.

    A Marathi name has several valid keys (Devanagari/Latin spelling, full nasal
    or anusvara); the index stores all of them, so the query must ask for all of
    them instead of a single "the" key.
    """
    out: list[str] = []
    for key in phonetic_keys(token):
        for tok in groups.get(key, ()):
            if tok not in out:
                out.append(tok)
    return out


class SearchEngine:
    def __init__(self, index_provider) -> None:
        # callable returning the *current* SearchIndex (swapped atomically on rebuild)
        self._index_provider = index_provider

    @property
    def index(self) -> SearchIndex:
        return self._index_provider()

    # ------------------------------------------------------------ token expansion
    def _expand_token(self, tok: str, vocab: list[str], postings: dict[str, array], phonetic: dict[str, list[str]]) -> dict[str, float]:
        """Return candidate index tokens with a match weight (1.0 = exact)."""
        cands: dict[str, float] = {}
        if tok in postings:
            cands[tok] = 1.0
        if len(tok) >= 2:
            for t in self.index.prefix_tokens(vocab, tok, 40):
                cands.setdefault(t, 0.85 if len(tok) >= 3 else 0.6)
        if len(tok) >= 3:
            for t in _phonetic_lookup(phonetic, tok):
                cands.setdefault(t, 0.8)
        if len(tok) >= 4 and len(cands) < 3 and vocab:
            # RapidFuzz over the vocabulary – bounded cost even for large vocabularies
            for match, score, _ in process.extract(
                tok, vocab, scorer=fuzz.ratio, limit=config.FUZZY_VOCAB_LIMIT, score_cutoff=config.FUZZY_SCORE_CUTOFF
            ):
                cands.setdefault(match, 0.5 + (score / 100.0) * 0.3)
        return cands

    def _records_for(self, tok: str, field_name: str) -> tuple[set[int], dict[int, float]]:
        idx = self.index
        if field_name == "name":
            groups = [(idx.name_vocab, idx.name_postings, idx.name_phonetic)]
        elif field_name == "relation":
            groups = [(idx.rel_vocab, idx.rel_postings, idx.rel_phonetic)]
        else:
            groups = [
                (idx.name_vocab, idx.name_postings, idx.name_phonetic),
                (idx.rel_vocab, idx.rel_postings, idx.rel_phonetic),
            ]
        ids: set[int] = set()
        weights: dict[int, float] = {}
        for vocab, postings, phonetic in groups:
            for cand, w in self._expand_token(tok, vocab, postings, phonetic).items():
                for rid in postings.get(cand, ()):
                    ids.add(rid)
                    if weights.get(rid, 0.0) < w:
                        weights[rid] = w
        return ids, weights

    # ------------------------------------------------------------------ search
    def search(self, q: SearchQuery, *, page: int = 1, page_size: int = 20) -> SearchResponse:
        t0 = time.perf_counter()
        idx = self.index
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        if q.is_empty() or len(idx) == 0:
            return SearchResponse([], 0, page, page_size, 0.0, q.to_dict())

        # Village scope: a pre-computed record set makes filtering O(1) per record
        scope: set[int] | None = None
        if q.village:
            scope = set(idx.village_records.get(q.village, ()))
            if not scope:
                return SearchResponse([], 0, page, page_size, round((time.perf_counter() - t0) * 1000, 2), q.to_dict())

        # ---- EPIC: exact hash lookup, then prefix scan fallback -----------
        if q.epic:
            epic = normalize_epic(q.epic)
            rid = idx.epic_lookup.get(epic)
            hits: list[tuple[int, float]] = []
            if rid is not None:
                hits = [(rid, 100.0)]
            else:
                for e, r in idx.epic_lookup.items():
                    if e.startswith(epic) or fuzz.ratio(e, epic) >= 85:
                        hits.append((r, fuzz.ratio(e, epic)))
                hits.sort(key=lambda x: -x[1])
            hits = [h for h in hits if self._passes_filters(h[0], q) and (scope is None or h[0] in scope)]
            resp = self._paginate(hits, q, page, page_size, t0)
            resp.exact_match = rid is not None and bool(resp.total)
            resp.unmatched_words = [] if resp.exact_match else [epic]
            return resp

        # ---- Name / relation tokens -----------------------------------------
        groups: list[tuple[str, list[str]]] = []
        if q.name:
            groups.append(("name", tokenize(q.name)))
        if q.relation_name:
            groups.append(("relation", tokenize(q.relation_name)))
        if q.any_text:
            groups.append(("any", tokenize(q.any_text)))

        token_sets: list[set[int]] = []
        weight_maps: list[dict[int, float]] = []
        for field_name, toks in groups:
            for tok in toks:
                ids, weights = self._records_for(tok, field_name)
                token_sets.append(ids)
                weight_maps.append(weights)

        relaxed = False
        if not token_sets:
            if q.has_filters():
                candidates: set[int] = set(scope) if scope is not None else set(range(len(idx)))
            else:
                candidates = set()
        else:
            candidates = set.intersection(*token_sets) if token_sets else set()
            if scope is not None:
                candidates &= scope
            if not candidates and len(token_sets) > 1:
                relaxed = True
                # OR semantics but require at least half of the tokens to match
                counts: dict[int, int] = {}
                for s in token_sets:
                    for rid in s:
                        counts[rid] = counts.get(rid, 0) + 1
                need = max(1, (len(token_sets) + 1) // 2)
                candidates = {rid for rid, c in counts.items() if c >= need}
                if scope is not None:
                    candidates &= scope

        # ---- Structured filters ------------------------------------------
        candidates = {rid for rid in candidates if self._passes_filters(rid, q)}

        # ---- Scoring -----------------------------------------------------
        scored = self._score(candidates, q, weight_maps)
        resp = self._paginate(scored, q, page, page_size, t0)
        resp.relaxed = relaxed
        if resp.total == 0:
            resp.suggestions = self.suggest_texts(q.name or q.any_text or q.relation_name, limit=5, village=q.village)
        return resp

    # ------------------------------------------------------------------ helpers
    def _passes_filters(self, rid: int, q: SearchQuery) -> bool:
        idx = self.index
        if q.part and idx.rec_part[rid] != q.part.lstrip("0"):
            if idx.rec_part[rid].lstrip("0") != q.part.lstrip("0"):
                return False
        if q.page and idx.rec_page[rid] != q.page:
            return False
        if q.gender and idx.rec_gender[rid].lower() != q.gender.lower():
            return False
        if q.age is not None and idx.rec_age[rid] != str(q.age):
            return False
        if q.pdf and q.pdf.lower() not in idx.pdf_names[idx.rec_pdf[rid]].lower():
            return False
        return True

    def _score(self, candidates: set[int], q: SearchQuery, weight_maps: list[dict[int, float]]) -> list[tuple[int, float]]:
        idx = self.index
        name_q = normalize(q.name)
        rel_q = normalize(q.relation_name)
        any_q = normalize(q.any_text)
        out: list[tuple[int, float]] = []
        # Cap the number of candidates we fully score to keep latency bounded.
        limit = config.MAX_RESULTS * 4
        for n, rid in enumerate(candidates):
            if n >= limit:
                break
            nm = normalize(idx.rec_name[rid])
            rl = normalize(idx.rec_relation[rid])
            nm_roman = normalize(idx.rec_name_dev[rid]) if rid < len(idx.rec_name_dev) else ""
            rl_roman = normalize(idx.rec_relation_roman[rid]) if rid < len(idx.rec_relation_roman) else ""
            score = 0.0
            if name_q:
                score += max(fuzz.token_set_ratio(name_q, nm), fuzz.token_set_ratio(name_q, nm_roman))
                if nm == name_q:
                    score += 25
                elif nm.startswith(name_q):
                    score += 10
            if rel_q:
                score += max(fuzz.token_set_ratio(rel_q, rl), fuzz.token_set_ratio(rel_q, rl_roman)) * 0.8
                if rl == rel_q:
                    score += 15
            if any_q:
                s_name = max(fuzz.token_set_ratio(any_q, nm), fuzz.token_set_ratio(any_q, nm_roman))
                s_both = max(
                    fuzz.token_set_ratio(any_q, f"{nm} {rl}"),
                    fuzz.token_set_ratio(any_q, f"{nm_roman} {rl_roman}"),
                )
                score += max(s_name, s_both * 0.95)
                if nm == any_q:
                    score += 25
                elif nm.startswith(any_q):
                    score += 10
            # token-level match quality
            tw = [wm[rid] for wm in weight_maps if rid in wm]
            if tw:
                score += (sum(tw) / len(weight_maps)) * 20
            out.append((rid, round(score, 2)))
        out.sort(key=lambda x: (-x[1], idx.rec_name[x[0]]))
        return out[: config.MAX_RESULTS]

    def _paginate(self, scored: list[tuple[int, float]], q: SearchQuery, page: int, page_size: int, t0: float) -> SearchResponse:
        idx = self.index
        total = len(scored)
        start = (page - 1) * page_size
        chunk = scored[start : start + page_size]
        results = []
        for rid, score in chunk:
            rec = idx.record(rid)
            rec["score"] = score
            results.append(rec)
        took = (time.perf_counter() - t0) * 1000
        resp = SearchResponse(results, total, page, page_size, round(took, 2), q.to_dict())
        self._annotate_exactness(resp, scored, q)
        return resp

    def _annotate_exactness(self, resp: SearchResponse, scored: list[tuple[int, float]], q: SearchQuery) -> None:
        """Decide whether every typed word is present *exactly* in at least one
        matched record.  Checked over the top-ranked records (not just the
        current page) so paging does not change the verdict.  A typed word of
        3+ letters also counts when it is a prefix of a record word (partial
        name searches)."""
        idx = self.index
        typed = [t for t in tokenize(" ".join(x for x in (q.name, q.relation_name, q.any_text) if x)) if t]
        if not typed:
            resp.exact_match = True
            resp.unmatched_words = []
            return
        if not scored:
            resp.exact_match = False
            resp.unmatched_words = list(typed)
            return
        found_any: set[str] = set()
        exact = False
        for rid, _ in scored[:200]:
            words = set(idx.searchable_tokens(rid))
            # cross-script equivalents: a Latin query counts as matched when the
            # roll stores the same name in Devanagari (and the other way round).
            words |= {v for w in list(words) for v, _ in variants_of(w)}
            keys = {phonetic_key(w) for w in words}
            ok = True
            for t in typed:
                # exact, prefix (partial name) or same-sounding spelling (Jadav ~ Jadhav)
                hit = (
                    t in words
                    or (len(t) >= 3 and any(w.startswith(t) for w in words))
                    or (len(t) >= 4 and phonetic_key(t) in keys)
                )
                if hit:
                    found_any.add(t)
                else:
                    ok = False
            if ok:
                exact = True
        resp.exact_match = exact
        resp.unmatched_words = [t for t in typed if t not in found_any]

    # ------------------------------------------------------------- suggestions
    def suggest(self, prefix: str, limit: int = 8, village: str = "") -> list[dict]:
        """Typeahead: return real voter entries matching the typed prefix.

        Each item: {"text": display name, "name", "relation_name", "village", "pdf", "page"}.
        Matching per token: prefix -> phonetic -> fuzzy (only for the last, still
        being typed, token when nothing else matched).  Ranked by how well the
        typed text matches the start of the name, then by name.
        """
        idx = self.index
        p = normalize(prefix)
        if not p or len(idx) == 0:
            return []
        toks = p.split(" ")
        if not toks:
            return []

        scope: set[int] | None = None
        if village:
            scope = set(idx.village_records.get(village, ()))
            if not scope:
                return []

        # candidate record ids: intersection over tokens (prefix/phonetic/fuzzy expanded)
        sets: list[set[int]] = []
        for i, tok in enumerate(toks):
            if len(tok) < 2 and i == len(toks) - 1 and len(toks) > 1:
                continue  # ignore a single just-typed character after a complete word
            cands = self._expand_token(tok, idx.name_vocab, idx.name_postings, idx.name_phonetic)
            if not cands:
                cands = self._expand_token(tok, idx.rel_vocab, idx.rel_postings, idx.rel_phonetic)
                postings = idx.rel_postings
            else:
                postings = idx.name_postings
            ids: set[int] = set()
            for cand in cands:
                ids.update(postings.get(cand, ()))
            if scope is not None:
                ids &= scope
            sets.append(ids)
        if not sets:
            return []
        candidates = set.intersection(*sets)
        if not candidates and len(sets) > 1:
            # relax: drop the last (partial) token
            candidates = set.intersection(*sets[:-1])
        if not candidates:
            return []

        # score & dedupe by (name, relation)
        scored: list[tuple[float, int]] = []
        first = toks[0]
        for rid in candidates:
            nm = normalize(idx.rec_name[rid])
            words = nm.split()
            score = fuzz.token_set_ratio(p, nm) * 0.6 + fuzz.partial_ratio(p, nm) * 0.4
            if nm.startswith(p):
                score += 60          # typed text is the beginning of the name
            elif words and words[0].startswith(first):
                score += 35          # first name matches what was typed first
            elif any(w.startswith(first) for w in words):
                score += 15          # some word starts with the first typed token
            # every typed token is a prefix of some word -> strong signal
            if all(any(w.startswith(t) for w in words) for t in toks if len(t) >= 2):
                score += 20
            scored.append((score, rid))
            if len(scored) > 3000:
                break
        scored.sort(key=lambda x: (-x[0], idx.rec_name[x[1]]))

        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for _, rid in scored:
            key = (normalize(idx.rec_name[rid]), normalize(idx.rec_relation[rid]))
            if key in seen:
                continue
            seen.add(key)
            rec = idx.record(rid)
            out.append({
                "text": rec["name"].title() if rec["name"].isupper() else rec["name"],
                "name": rec["name"],
                "relation_name": rec["relation_name"],
                "relation_type": rec["relation_type"],
                "village": rec["village"],
                "pdf": rec["pdf"],
                "page": rec["page"],
                "age": rec["age"],
                "gender": rec["gender"],
            })
            if len(out) >= limit:
                break
        return out

    def suggest_texts(self, prefix: str, limit: int = 8, village: str = "") -> list[str]:
        """Plain-string variant used for 'did you mean' after an empty search."""
        idx = self.index
        p = normalize(prefix)
        if not p or len(idx) == 0:
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in self.suggest(p, limit=limit, village=village):
            t = item["text"]
            if t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        if out:
            return out
        # fall back to token-level phonetic / fuzzy alternatives of each word
        alts: list[str] = []
        for tok in p.split(" "):
            cands = _phonetic_lookup(idx.name_phonetic, tok)
            if not cands:
                cands = [m for m, _, _ in process.extract(tok, idx.name_vocab, scorer=fuzz.ratio, limit=3, score_cutoff=70)]
            cands = [c for c in cands if c != tok]
            if cands:
                cands.sort(key=lambda t: -idx.name_freq.get(t, 0))
                alts.append(p.replace(tok, cands[0]))
        return [a.title() for a in alts[:limit]]
