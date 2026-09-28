"""Serial recovery must never publish an unverified card mapping."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.pdf_manager.pdf_parser import (
    VoterRecord,
    _apply_verified_page_serials,
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

multiple_blanks = [{"serial": "1"}, {"serial": ""}, {"serial": ""}, {"serial": "4"}]
assert _recover_missing_sequence_serials(multiple_blanks) == 2
assert [row["serial"] for row in multiple_blanks] == ["1", "2", "3", "4"]

for ambiguous in (
    [{"serial": "1"}, {"serial": "4"}, {"serial": ""}],
    [{"serial": "1"}, {"serial": "not-a-number"}, {"serial": ""}],
    [{"serial": "2"}, {"serial": ""}, {"serial": "3"}],
):
    before = [row["serial"] for row in ambiguous]
    assert _recover_missing_sequence_serials(ambiguous) == 0
    assert [row["serial"] for row in ambiguous] == before

print("PASS: serial recovery requires matching cards and complete sequence")
