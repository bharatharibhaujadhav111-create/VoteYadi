"""Unit tests for the Marathi layer – no PDF, no server, no network.

    python backend/tests/test_marathi.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import devanagari as dev  # noqa: E402
from app.core import marathi as mar  # noqa: E402
from app.core.text_utils import (  # noqa: E402
    equivalent_word, normalize, phonetic_key, phonetic_keys, tokenize, variants_of,
)
from app.search_index.index_store import SearchIndex  # noqa: E402
from app.pdf_manager.pdf_parser import (  # noqa: E402
    _parse_page_job, _repair_ocr_epics, ocr_language_for, order_by_columns, parse_page_text,
)

FAILS: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    if not ok:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"   got={got!r} want={want!r}"))


def check_true(label: str, value) -> None:
    check(label, bool(value), True)


print("== normalisation ==")
check("NFC + nukta fold", dev.fold("क़रीम"), "करीम")
check("chandrabindu -> anusvara", dev.fold("जाँभळे") == dev.fold("जांभळे"), True)
check("ZWJ stripped", dev.fold("क\u200dष"), "कष")
check("danda -> space", dev.fold("नाव।"), "नाव")
check("devanagari digits folded", dev.fold("भाग ७"), "भाग 7")

print("\n== script detection ==")
check("pure devanagari", dev.detect_script("रामचंद्र जाधव"), "devanagari")
check("pure latin", dev.detect_script("Ramchandra Jadhav"), "latin")
check("marathi page profile -> mar+eng", mar.page_profile("नाव : रामचंद्र जाधव EPIC ZCG1234567")["suggested_lang"], "mar+eng")
check("english page profile -> eng", mar.page_profile("Name : Vinayshree Bharat Jadhav")["suggested_lang"], "eng")
check("scanned Marathi page uses Marathi OCR", ocr_language_for("नाव : राजकुमार गुंड", scanned=True), "mar")
check("scanned English page uses English OCR", ocr_language_for("Name: Vinayshree Jadhav Father Name: Bharat Jadhav", scanned=True), "eng")
with tempfile.TemporaryDirectory() as temp_dir:
    sample = Path(temp_dir) / "short-text-layer.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "STAMP")
        pdf.save(sample)
    with patch("app.pdf_manager.pdf_parser._ocr_lines", return_value=[]) as mocked_ocr:
        _parse_page_job((str(sample), 0))
    check("short text layer still uses scanned Marathi OCR", mocked_ocr.call_args.kwargs["lang"], "mar")

print("\n== cross-script skeleton (the accuracy core) ==")
for latin, deva in [
    ("jadhav", "जाधव"), ("jadav", "जादव"), ("jadhaw", "जाधव"),
    ("bharat", "भारत"), ("shinde", "शिंदे"), ("ghandure", "घंदुरे"),
    ("kale", "काळे"), ("gayakwad", "गायकवाड"), ("patil", "पाटील"),
    ("ramchandra", "रामचंद्र"), ("more", "मोरे"), ("tamboli", "तांबोळी"),
]:
    check_true(
        f"skeleton {latin} == {deva}",
        any(dev.text_skeleton(latin, b) == dev.text_skeleton(deva, b) for b in (False, True)),
    )

check("aspirate tolerant: dhadhav ~ dadav", dev.text_skeleton("dhadhav"), dev.text_skeleton("dadav"))
check("sibilant tolerant: shinde ~ sinde", dev.dev_skeleton("शिंदे"), dev.dev_skeleton("सिंदे"))
check("phonetic key is script independent", phonetic_key("jadhav"), phonetic_key("जाधव"))

print("\n== tokenisation keeps matras ==")
check("marathi tokens", tokenize("वडिलांचे नाव : रामचंद्र जाधव"),
      ["वडिलांचे", "नाव", "रामचंद्र", "जाधव"])
check("latin unchanged", normalize("Vinayshree  Bharat-JADHAV"), "vinayshree bharat jadhav")

print("\n== query understanding ==")
q = mar.parse_marathi_query("वडिलांचे नाव भरत जाधव असलेल्या विजयसिंह जाधव")
check("marathi name extracted", q["name"], "विजयसिंह जाधव")
check("marathi relation extracted", q["relation_name"], "भरत जाधव")
check("relation type", q["relation_type"], "father")
check("honorific stripped", mar.strip_honorifics("श्री रामचंद्र जाधव"), "रामचंद्र जाधव")
check("smt honorific stripped", mar.strip_honorifics("श्रीमती अनिता पाटील"), "अनिता पाटील")
check("label-only word rejected", mar.is_label("नाव"), True)
check("name word kept", mar.is_label("जाधव"), False)
check("clean_name drops labels", mar.clean_name("नाव : श्री रामचंद्र जाधव"), "रामचंद्र जाधव")

print("\n== cross-script query variants ==")
check_true("jadhav has a devanagari variant", any(dev.has_devanagari(v) for v, _ in variants_of("jadhav")))
check_true("जाधव has a latin variant", any(not dev.has_devanagari(v) for v, _ in variants_of("जाधव")))
check("prefix match on the Romanised twin", equivalent_word("jadha", {"jadhava"}, set()), True)
check("phonetic match", equivalent_word("jadaw", set(), set(phonetic_keys("जाधव"))), True)

print("\n== alias table: Latin query -> corpus spelling ==")
idx = SearchIndex.build([("Marathi/roll.pdf", [
    {"name": "रामचंद्र भरत जाधव", "relation_name": "भरत जाधव", "relation_type": "father",
     "epic": "ZCG1000001", "age": "45", "gender": "पुरुष", "part": "1", "page": 1},
    {"name": "सुनील दत्तात्रय पाटील", "relation_name": "दत्तात्रय पाटील", "relation_type": "father",
     "epic": "ZCG1000002", "age": "38", "gender": "पुरुष", "part": "1", "page": 1},
])])
check("alias lookup jadhav -> जाधव", idx.alias_token_of("jadhav"), "जाधव")
check_true("devanagari name romanised in the index", "jadhav" in idx.rec_name_dev[0])
check_true("cross-script tokens exposed",
           any(t.startswith("jadhav") for t in idx.searchable_tokens(0)))
check_true("record exposes romanised name", idx.record(0)["name_dev"].split()[-1].startswith("jadhav"))

print("\n== OCR card header pairing ==")
ocr_lines = [
    (62.0, 100.0, "1"),
    (510.0, 100.0, "ZCG1000001"),
    (62.0, 140.0, "नाव: अमित जाधव"),
    (62.0, 165.0, "वडिलांचे नाव: भारत जाधव"),
    # Serial 2 is deliberately absent; its EPIC has ZCG misread as 206.
    (1145.0, 100.0, "2061000002"),
    (696.0, 140.0, "नाव: सुनील पाटील"),
    (696.0, 165.0, "वडिलांचे नाव: राम पाटील"),
    (1493.0, 100.0, "3"),
    (1778.0, 100.0, "ZCG1000003"),
    (1329.0, 140.0, "नाव: विजय शिंदे"),
    (1329.0, 165.0, "वडिलांचे नाव: मोहन शिंदे"),
]
ocr_records = parse_page_text(order_by_columns(_repair_ocr_epics(ocr_lines)), 1, "").records
check("three-column record count", len(ocr_records), 3)
check("serials paired and missing one inferred", [r.serial for r in ocr_records], ["1", "2", "3"])
check("digit-shaped EPIC prefix repaired", [r.epic for r in ocr_records],
      ["ZCG1000001", "ZCG1000002", "ZCG1000003"])

split_name_lines = [
    (208.0, 112.0, "481"),
    (62.0, 158.0, "नाव: शबाना"),
    (230.0, 152.0, "जाकीरहुसेन सय्यद"),
    (62.0, 179.0, "पतीचे नाव: जाकीरहुसेन सय्यद"),
    (696.0, 158.0, "नाव: दुसरे नाव"),
    (1329.0, 158.0, "नाव: तिसरे नाव"),
]
split_records = parse_page_text(order_by_columns(split_name_lines), 19, "").records
check("same-line Marathi name fragments rejoined", len(split_records), 3)
check("complete split Marathi name retained", split_records[0].name, "शबाना जाकीरहुसेन सय्यद")
check("split-name serial retained", split_records[0].serial, "481")

# A damaged relation label can look like a name label and be indented within
# the first card. It must not create a false fourth column and corrupt every
# spatially inferred serial on the page.
shifted_label_lines = [
    (208.0, 112.0, "331"),
    (839.0, 112.0, "332"),
    (1473.0, 112.0, "333"),
    (62.0, 152.0, "नाव: पहिले नाव"),
    (696.0, 152.0, "नाव: दुसरे नाव"),
    (1329.0, 152.0, "नाव: तिसरे नाव"),
    (208.0, 377.0, "334"),
    (839.0, 377.0, "335"),
    (1473.0, 377.0, "336"),
    (108.0, 417.0, "नाव: चौथे नाव"),
    (696.0, 417.0, "नाव: पाचवे नाव"),
    (1329.0, 417.0, "नाव: सहावे नाव"),
]
shifted_records = parse_page_text(order_by_columns(shifted_label_lines), 14, "").records
check("indented label stays in the three-column grid", len(shifted_records), 6)
check("indented label preserves serial sequence", [r.serial for r in shifted_records],
      ["331", "334", "332", "335", "333", "336"])

damaged_relation = parse_page_text([
    "403",
    "नाव * १ हसेन महमद मुजाफीर महमद",
    "ांचे नाव: महमद मुजाफीर महमद",
], 16, "").records
check("truncated relation label does not create a duplicate voter", len(damaged_relation), 1)
check("numeric OCR debris removed from voter name", damaged_relation[0].name,
      "हसेन महमद मुजाफीर महमद")
check("truncated relation value retained", damaged_relation[0].relation_name,
      "महमद मुजाफीर महमद")

print("\n== romanisation quality ==")
for deva, want in [("जाधव", "jadhav"), ("भारत", "bharat"), ("शिंदे", "shinde"),
                   ("काळे", "kale"), ("पाटील", "patil"), ("मोरे", "more")]:
    check(f"romanise {deva}", dev.devanagari_to_roman(deva).rstrip("a") if deva != "शिंदे" else dev.devanagari_to_roman(deva), want)

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S)")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("all Marathi unit tests passed")
