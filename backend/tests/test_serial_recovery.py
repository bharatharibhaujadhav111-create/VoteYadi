"""Serial recovery must never publish an unverified card mapping."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.pdf_manager.pdf_parser import (
    VoterRecord,
    _apply_digit_verified_serials,
    _apply_verified_page_serials,
    _card_record_from_text,
    _merge_complete_page,
    _neighbour_expected,
    _recover_single_card_serial,
    _recover_missing_sequence_serials,
)


def records(serials: list[int]) -> list[VoterRecord]:
    return [VoterRecord(name=f"मतदार {number}", serial=str(number)) for number in serials]


bad = [{"name": f"मराठी नाव {number}", "serial": str(number)} for number in (555, 556, 557)]
assert _apply_verified_page_serials(bad, records([955, 956, 957]), 955)
assert [row["serial"] for row in bad] == ["955", "956", "957"]
assert bad[0]["name"] == "मराठी नाव 555"

for other in (records([955, 956]), records([955, 956, 956]), records([955, 956, 958])):
    rows = [{"serial": "555"}, {"serial": "556"}, {"serial": "557"}]
    assert not _apply_verified_page_serials(rows, other, 955)
    assert [row["serial"] for row in rows] == ["555", "556", "557"]

rows = [{"serial": "955"}, {"serial": "556"}, {"serial": "557"}]
assert not _apply_verified_page_serials(rows, records([956, 955, 957]), 955)
assert [row["serial"] for row in rows] == ["955", "556", "557"]

one_missed_name = [
    {"name": "पहिले नाव", "serial": "275"},
    {"name": "दुसरे नाव", "serial": "294"},
    {"name": "तिसरे नाव", "serial": "305"},
]
other = [VoterRecord(name="पहिले नाव", serial="276"),
         VoterRecord(name="तिसरे नाव", serial="278")]
assert _apply_verified_page_serials(one_missed_name, other, 276)
assert [row["serial"] for row in one_missed_name] == ["276", "277", "278"]

unsafe = [{"name": "पहिले नाव", "serial": "275"}, {"name": "दुसरे नाव", "serial": "294"},
          {"name": "तिसरे नाव", "serial": "305"}]
assert not _apply_verified_page_serials(unsafe,
    [VoterRecord(name="नाव वेगळे", serial="276"), VoterRecord(name="तिसरे नाव", serial="278")], 276)
assert [row["serial"] for row in unsafe] == ["275", "294", "305"]

complete_except_one = [{"serial": str(number)} for number in range(1, 301)]
complete_except_one[200]["serial"] = ""
assert _recover_missing_sequence_serials(complete_except_one) == 1
assert complete_except_one[200]["serial"] == "201"

# A page/column ordering variation elsewhere must not hide a uniquely proven
# missing value. The set is still complete except for the one blank serial.
single_blank_with_reordered_cards = [{"serial": str(number)} for number in range(1, 6)]
single_blank_with_reordered_cards[1], single_blank_with_reordered_cards[2] = (
    single_blank_with_reordered_cards[2], single_blank_with_reordered_cards[1]
)
single_blank_with_reordered_cards[4]["serial"] = ""
assert _recover_missing_sequence_serials(single_blank_with_reordered_cards) == 1
assert single_blank_with_reordered_cards[4]["serial"] == "5"

multiple_blanks = [{"serial": "1"}, {"serial": ""}, {"serial": ""}, {"serial": "4"}]
assert _recover_missing_sequence_serials(multiple_blanks) == 2
assert [row["serial"] for row in multiple_blanks] == ["1", "2", "3", "4"]

for ambiguous in (
    [{"serial": "1"}, {"serial": "4"}, {"serial": ""}],
    [{"serial": "1"}, {"serial": "not-a-number"}, {"serial": ""}],
):
    before = [row["serial"] for row in ambiguous]
    assert _recover_missing_sequence_serials(ambiguous) == 0
    assert [row["serial"] for row in ambiguous] == before

unique_set_proof = [{"serial": "2"}, {"serial": ""}, {"serial": "3"}]
assert _recover_missing_sequence_serials(unique_set_proof) == 1
assert unique_set_proof[1]["serial"] == "1"

# Sparse pages are bounded by printed serials on the surrounding pages.
page_results = [
    (12, "", True, [{"serial": "300"}]),
    (13, "", True, [{"serial": ""}]),
    (14, "", True, [{"serial": "302"}]),
]
assert _neighbour_expected(page_results, 1) == {301}

last_page_results = [
    (35, "", True, [{"serial": "954"}]),
    (36, "", True, [{"serial": ""}]),
    (37, "", True, []),
]
assert _neighbour_expected(last_page_results, 1) == {955}

single_card = [{"name": "मतदार नाव", "serial": ""}]
single_card_anchors = [(205.3, 111.8, "955"), (62.0, 152.4, "नाव : मतदार नाव")]
assert _recover_single_card_serial(single_card, {955}, single_card_anchors, 1983.0)
assert single_card[0]["serial"] == "955"

misaligned_serial = [{"name": "मतदार नाव", "serial": ""}]
assert not _recover_single_card_serial(
    misaligned_serial, {955}, [(700.0, 111.8, "955"), (62.0, 152.4, "नाव : मतदार नाव")], 1983.0
)
assert misaligned_serial[0]["serial"] == ""

cropped = _card_record_from_text(
    """| 112 | ISF7014244
नाच : हुसेन उ अब्बास सय्यद
: अब्बास इब्राहिम सय्यद
घर क्रमांक :
वय : 71 लिंग : पुरुष""",
    serial=112,
    page_no=6,
    epic_prefix="ISF",
)
assert cropped is not None
assert cropped.serial == "112"
assert cropped.name == "हुसेन अब्बास सय्यद"
assert cropped.relation_name == "अब्बास इब्राहिम सय्यद"
assert cropped.age == "71"

# Tesseract sometimes substitutes ज for the final व in the Marathi name label.
label_substitution = _card_record_from_text(
    "\u0928\u093e\u091c : \u0939\u0941\u0938\u0947\u0928 \u0905\u092c\u094d\u092c\u093e\u0938 \u0938\u092f\u094d\u092f\u0926",
    serial=112,
    page_no=6,
)
assert label_substitution is not None
assert label_substitution.name == "\u0939\u0941\u0938\u0947\u0928 \u0905\u092c\u094d\u092c\u093e\u0938 \u0938\u092f\u094d\u092f\u0926"

# Digits-only OCR must independently confirm both lone-card and full-page fixes.
lone = [{"serial": ""}]
assert _apply_digit_verified_serials(lone, {301}, {301})
assert lone[0]["serial"] == "301"
wrong_hundreds = [{"serial": str(number)} for number in range(570, 593)]
assert _apply_digit_verified_serials(wrong_hundreds, set(range(970, 993)), set(range(970, 993)))
assert [row["serial"] for row in wrong_hundreds] == [str(number) for number in range(970, 993)]

# On a substantial page, one verification miss is allowed only when all OCR
# serials share the same exact offset into the neighbour-proven interval.
one_digit_missed = [{"serial": str(number)} for number in range(570, 593)]
expected_full_page = set(range(970, 993))
assert _apply_digit_verified_serials(one_digit_missed, expected_full_page, expected_full_page - {975})
assert [row["serial"] for row in one_digit_missed] == [str(number) for number in range(970, 993)]

sparse_offset = [{"serial": "300"}, {"serial": "301"}]
assert not _apply_digit_verified_serials(sparse_offset, {700, 701}, {700})
assert [row["serial"] for row in sparse_offset] == ["300", "301"]

unconfirmed = [{"serial": "570"}]
assert not _apply_digit_verified_serials(unconfirmed, {970}, set())
assert unconfirmed[0]["serial"] == "570"

# An alternate layout pass may add a missed card, while primary text is kept.
primary = [{"name": "नाव 482", "epic": "ABC0000482", "serial": "482"}]
alternate = [
    VoterRecord(name="नाव 481", epic="ABC0000481", serial="481"),
    VoterRecord(name="alternate text", epic="ABC0000482", serial="482"),
]
assert _merge_complete_page(primary, alternate, {481, 482})
assert [row["serial"] for row in primary] == ["481", "482"]
assert primary[1]["name"] == "नाव 482"

print("PASS: serial recovery requires matching cards and complete sequence")
