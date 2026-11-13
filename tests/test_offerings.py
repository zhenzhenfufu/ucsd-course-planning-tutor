import json
from pathlib import Path

import pytest

from offerings import load_offerings
from prereq_graph import build
from terms import Term
from validator import validate

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


def test_tentative_listed_with_no_quarter(off):
    s = off.lookup("DSC 80", "DSC", Term("SP", 2027))
    assert s.kind == "tentative_no_quarter"
    assert s.academic_year == "2026-27"
    assert off.lookup("DSC 80", "DSC", Term("FA", 2026)).kind == "tentative_no_quarter"
    assert off.lookup("DSC 80", "DSC", Term("SP", 2027), {"DSC 80"}).kind == "exempt"


def test_summary_no_quarter_planned(off):
    s = off.summary("DSC 80", "DSC")
    assert "listed, no quarter planned" in s
    assert "not listed" not in s
    assert "not listed" in off.summary("DSC 20", "DSC")


# ---- hand-entered quarters (offerings_manual.json) -------------------------

REAL = Path(__file__).resolve().parent.parent / "data"
VALID_QUARTERS = {"FA", "WI", "SP"}


def _manual(tmp_path, courses):
    off = tmp_path / "off.json"
    off.write_text(json.dumps({"generated_at": "2026-11-01T00:00:00Z",
                               "scheduled": {}, "tentative": {}}))
    man = tmp_path / "man.json"
    man.write_text(json.dumps({"2026-27": {"CHEM": {
        "entered_at": "2026-11-02", "source_url": "https://example.test/chem",
        "courses": courses}}}))
    return load_offerings(off, man)


def _chem(off):
    return off.tentative["2026-27"]["CHEM"]["courses"]


def test_manual_full_names_any_case_are_normalised(tmp_path):
    off = _manual(tmp_path, {"CHEM 6A": ["Fall", "winter"], "CHEM 6B": ["sp", "FA"]})
    assert _chem(off) == {"CHEM 6A": ["FA", "WI"], "CHEM 6B": ["FA", "SP"]}
    s = off.lookup("CHEM 6A", "CHEM", Term("SP", 2027))
    assert s.kind == "tentative_other_quarters" and s.quarters == ["FA", "WI"]


def test_manual_string_value_is_dropped_not_split(tmp_path):
    off = _manual(tmp_path, {"CHEM 6A": ["FA"], "CHEM 6B": "WI"})
    assert _chem(off) == {"CHEM 6A": ["FA"]}


def test_manual_garbage_quarters_are_dropped(tmp_path):
    off = _manual(tmp_path, {"CHEM 6A": ["Fall", "Autumn", 3, None, "SU"], "CHEM 6B": None})
    assert _chem(off) == {"CHEM 6A": ["FA"]}


def test_validator_survives_bad_manual_entries(tmp_path):
    off = _manual(tmp_path, {"CHEM 6A": ["Fall"], "CHEM 6B": "WI", "CHEM 6C": ["Fall", "Winter"]})
    plan = [{"term": "Spring 2027", "courses": ["CHEM 6A", "CHEM 6B", "CHEM 6C"]}]
    msgs = [v.message for v in validate(plan, build(), offerings=off)
            if v.code == "NOT_OFFERED"]
    assert any("CHEM 6A is listed for Fall only" in m for m in msgs)


def test_offerings_json_quarters_are_normalised(tmp_path):
    off = tmp_path / "off.json"
    off.write_text(json.dumps({"generated_at": "x", "scheduled": {}, "tentative": {"2026-27": {
        "DSC": {"source_url": "u", "fetched_at": "t",
                "courses": {"DSC 10": ["Winter", "fa", "bogus"], "DSC 20": "FA"}}}}}))
    o = load_offerings(off, tmp_path / "missing.json")
    assert o.tentative["2026-27"]["DSC"]["courses"] == {"DSC 10": ["FA", "WI"]}


@pytest.mark.parametrize("name", ["offerings.json", "offerings_manual.json"])
def test_committed_quarter_lists_are_canonical(name):
    """CI blocks a hand edit (or adapter change) that writes anything but FA/WI/SP lists."""
    data = json.loads((REAL / name).read_text(encoding="utf-8"))
    years = data["tentative"] if name == "offerings.json" else data
    for ay, depts in years.items():
        for dept, entry in depts.items():
            courses = entry["courses"]
            assert isinstance(courses, dict), (name, ay, dept)
            for cid, qs in courses.items():
                assert isinstance(qs, list), (name, ay, dept, cid, qs)
                assert set(qs) <= VALID_QUARTERS, (name, ay, dept, cid, qs)
