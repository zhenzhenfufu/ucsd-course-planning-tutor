from pathlib import Path

import pytest

from offerings import load_offerings
from terms import Term

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def off():
    return load_offerings(FIX / "offerings_small.json", FIX / "offerings_manual_small.json")


def test_scheduled_offered(off):
    s = off.lookup("DSC 10", "DSC", Term("WI", 2027))
    assert s.kind == "scheduled_offered" and s.quarters == ["WI"]


def test_scheduled_absent(off):
    assert off.lookup("DSC 30", "DSC", Term("WI", 2027)).kind == "scheduled_absent"


def test_zero_course_subject_is_not_covered(off):
    assert off.lookup("MATH 18", "MATH", Term("WI", 2027)).kind == "tentative_offered"


def test_tentative_other_quarters(off):
    s = off.lookup("DSC 30", "DSC", Term("SP", 2027))
    assert s.kind == "tentative_other_quarters" and s.quarters == ["FA"]
    assert s.academic_year == "2026-27" and s.source_url == "https://example.test/dsc"


def test_out_of_year_is_unknown(off):
    assert off.lookup("DSC 30", "DSC", Term("WI", 2028)).kind == "unknown"


def test_unlisted(off):
    assert off.lookup("DSC 999", "DSC", Term("SP", 2027)).kind == "tentative_unlisted"


def test_exempt(off):
    assert off.lookup("DSC 199", "DSC", Term("SP", 2027), {"DSC 199"}).kind == "exempt"


def test_summer_is_unknown(off):
    assert off.lookup("DSC 10", "DSC", Term("SU", 2027)).kind == "unknown"


def test_manual_file_fills_chem(off):
    assert off.lookup("CHEM 6A", "CHEM", Term("FA", 2026)).kind == "tentative_offered"
    assert off.lookup("CHEM 6B", "CHEM", Term("FA", 2026)).kind == "tentative_other_quarters"


def test_empty_manual_block_is_not_coverage(off):
    assert off.lookup("BILD 1", "BIOL", Term("FA", 2026)).kind == "unknown"


def test_official_beats_manual(tmp_path):
    import json
    base = json.loads((FIX / "offerings_small.json").read_text())
    p = tmp_path / "o.json"
    p.write_text(json.dumps(base))
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"2026-27": {"DSC": {"entered_by": "x", "entered_at": "y", "source_url": "u",
                                                   "courses": {"DSC 10": ["SP"], "DSC 77": ["FA"]}}}}))
    o = load_offerings(p, man)
    assert o.lookup("DSC 77", "DSC", Term("FA", 2026)).kind == "tentative_unlisted"


def test_summary(off):
    s = off.summary("DSC 30", "DSC")
    assert "2026-27 tentative: FA" in s and "WI27 scheduled: no" in s
    assert "WI27 scheduled: yes" in off.summary("DSC 10", "DSC")
    assert "scheduled" not in off.summary("MATH 18", "MATH")


def test_missing_file_is_unknown(tmp_path):
    o = load_offerings(tmp_path / "none.json", tmp_path / "none2.json")
    assert not o.available
    assert o.lookup("DSC 10", "DSC", Term("WI", 2027)).kind == "unknown"
    assert "unavailable" in o.summary("DSC 10", "DSC")


@pytest.mark.parametrize("text", ["{not json", "[]", '{"scheduled": 5}', ""])
def test_corrupt_file_is_unknown(tmp_path, text):
    p = tmp_path / "bad.json"
    p.write_text(text)
    o = load_offerings(p, tmp_path / "none.json")
    assert not o.available
    assert o.lookup("DSC 10", "DSC", Term("WI", 2027)).kind == "unknown"
