"""Search the index from the command line – Marathi, English or a mix.

    python backend/tools/search_cli.py "जाधव"
    python backend/tools/search_cli.py "jadhav" --village Tirhe
    python backend/tools/search_cli.py "वडिलांचे नाव भरत जाधव असलेल्या विजयसिंह जाधव"
    python backend/tools/search_cli.py "जाधव" --rebuild --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai_parser.marathi_parser import parse_query  # noqa: E402
from app.core import devanagari as dev  # noqa: E402
from app.pdf_manager.pdf_store import PdfStore  # noqa: E402
from app.search_engine.engine import SearchEngine  # noqa: E402
from app.search_index.index_manager import IndexManager  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--village", default="")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--rebuild", action="store_true", help="re-index before searching")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    store = PdfStore()
    indexer = IndexManager(store)
    indexer.startup()
    if args.rebuild:
        indexer.index_now(full=True)
    else:
        thread = indexer._thread  # noqa: SLF001 – wait for the startup pass
        if thread is not None:
            thread.join()

    engine = SearchEngine(lambda: indexer.index)
    parsed = parse_query(args.query, allow_llm=False)
    parsed.village = args.village
    result = engine.search(parsed, page=1, page_size=args.limit).to_dict()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    name = parsed.name
    roman = dev.to_roman_text(name) if dev.has_devanagari(name) else ""
    print(f"query      : {args.query}")
    print(f"understood : name={name!r}{f' ({roman})' if roman else ''} "
          f"relation={parsed.relation_name!r} ({parsed.relation_type or '-'}) "
          f"part={parsed.part or '-'} village={parsed.village or '-'}")
    print(f"hits       : {result.get('total', len(result.get('results', [])))}")
    for r in result.get("results", []):
        mark = "exact" if r.get("exact") else "fuzzy"
        dev_name = f"  [{r['name_dev']}]" if r.get("name_dev") else ""
        print(f"  {r.get('score', 0):5.1f} {mark:5} {r.get('name', ''):<26}"
              f"{dev_name:<26} {r.get('relation_type') or '-':<7} "
              f"{r.get('relation_name', ''):<22} "
              f"part {r.get('part') or '-':<3} p{r.get('page')} {r.get('village') or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
