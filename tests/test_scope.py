import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCOPE = json.loads((ROOT / "data" / "scope.json").read_text(encoding="utf-8"))
OVERRIDES = json.loads((ROOT / "prereq_overrides.json").read_text(encoding="utf-8"))


def test_scope_has_every_current_course():
    old = {c["id"] for c in json.loads((ROOT / "dsc_courses.json").read_text(encoding="utf-8"))}
    courses = SCOPE["courses"]
    assert len(courses) == 69
    assert set(courses) == old
    for cid, c in courses.items():
        assert c["department"], cid
        assert c["keywords"], cid


def test_keywords_are_short():
    for cid, c in SCOPE["courses"].items():
        assert 3 <= len(c["keywords"]) <= 6, cid
        for kw in c["keywords"]:
            assert len(kw.split()) <= 4, (cid, kw)
            assert "." not in kw, (cid, kw)


def test_by_arrangement_are_in_scope():
    assert set(SCOPE["by_arrangement"]) <= set(SCOPE["courses"])


def test_overrides_have_reasons():
    for key in ("substitutes", "advisory_edges", "add_edges"):
        assert OVERRIDES[key], key
        for entry in OVERRIDES[key]:
            assert entry["why"].strip(), (key, entry)
