"""Refresh report: diffs and Markdown rendering. No network."""

import copy
from datetime import date

from refresh.report import diff_catalog, diff_offerings, render_report

C = {"courses": {"DSC 180A": {
    "title": "Data Science Project I", "units": 4.0, "units_max": 4.0,
    "prereq_groups": [["DSC 102"], ["MATH 189"]], "conditions": ["major restriction"],
    "ambiguities": [], "catalog_url": "https://catalog.ucsd.edu/courses/DSC.html#dsc180a",
    "stale": False}}}


def _new():
    n = copy.deepcopy(C)
    n["courses"]["DSC 180A"]["prereq_groups"][1].append("DSC 152")
    return n


def test_prereq_option_added_is_reported():
    lines = diff_catalog(C, _new())
    assert any("DSC 180A" in l and "DSC 152" in l for l in lines)


def test_catalog_other_changes():
    n = copy.deepcopy(C)
    c = n["courses"]["DSC 180A"]
    c.update(title="Capstone I", units=2.0, units_max=2.0, stale=True,
             conditions=["upper-division standing"],
             ambiguities=[{"kind": "nested-and", "fragment": "A and B"}])
    n["courses"]["DSC 190"] = dict(c, title="Topics", ambiguities=[])
    text = "\n".join(diff_catalog(C, n))
    for bit in ("Capstone I", "2.0", "upper-division standing", "major restriction",
                "A and B", "#dsc180a", "stale", "DSC 190"):
        assert bit in text
    assert "removed" in "\n".join(diff_catalog(n, C))


def test_diff_missing_old_is_empty_baseline():
    assert diff_catalog({}, C)  # everything is new, no crash
    assert diff_catalog(C, C) == []


def test_offering_diff():
    old = {"scheduled": {"FA26": {"courses": ["DSC 10"]}},
           "tentative": {"2026-27": {"DSC": {"courses": {"DSC 10": ["FA", "WI"]}}}}}
    new = {"scheduled": {"WI27": {"courses": ["DSC 10"]}},
           "tentative": {"2026-27": {"DSC": {"courses": {"DSC 10": ["FA", "SP"],
                                                          "DSC 20": ["FA"]}}}}}
    text = "\n".join(diff_offerings(old, new))
    assert "DSC 10" in text and "gained SP" in text and "lost WI" in text
    assert "DSC 20" in text and "WI27" in text and "FA26" in text
    assert diff_offerings(old, old) == []
    assert diff_offerings({}, {})== []


def test_failed_source_listed_first():
    src = {"cse": {"ok": True, "source_url": "u1", "error": None},
           "math": {"ok": False, "source_url": "u2", "error": "ShapeError: html not csv"}}
    md = render_report([], [], src, None, today=date(2026, 11, 13))
    assert md.index("math") < md.index("cse")
    assert "ShapeError: html not csv" in md


def test_no_changes_says_so():
    md = render_report([], [], {}, "12 passed", today=date(2026, 11, 13))
    assert md.count("No changes") == 2
    assert "12 passed" in md
    assert md.index("Sources") < md.index("Catalog changes") < md.index("Offering changes") < md.index("Tests")


def test_next_year_reminder_in_march(tmp_path):
    sources = {"2026-27": {"DSC": {}, "CSE": {}}, "2027-28": {"DSC": {}}}
    kw = dict(sources_plan=sources)
    md = render_report([], [], {}, None, today=date(2027, 3, 10), **kw)
    assert "No plan found for next academic year" in md and "CSE" in md and "2027-28" in md
    assert "DSC" not in md.split("No plan found")[1].split("\n")[0]
    # outside March-June: silent; Aug 2026 -> next year is 2027-28 only after Sept
    assert "No plan found" not in render_report([], [], {}, None, today=date(2026, 11, 13), **kw)


def test_run_writes_report(tmp_path):
    import json
    from tests.test_refresh_run import FakeSession, _setup, FIX
    d = _setup(tmp_path)
    s = FakeSession({"DSC": (FIX / "catalog_dsc.html").read_text(),
                     "CSE": (FIX / "catalog_cse.html").read_text()})
    rep = tmp_path / "r.md"
    from refresh.run import main
    assert main(["--only", "catalog", "--data-dir", str(d), "--report", str(rep)], session=s) == 0
    md = rep.read_text()
    assert "## Sources" in md and "| catalog | ok |" in md and "DSC 30" in md


def _g(groups):
    n = copy.deepcopy(C)
    n["courses"]["DSC 180A"]["prereq_groups"] = groups
    return n


def _old(groups):
    return _g(groups)


def test_group_reorder_is_silent():
    assert diff_catalog(_old([["X"], ["Y", "Z"]]), _g([["Z", "Y"], ["X"]])) == []


def test_option_added_to_group():
    t = "\n".join(diff_catalog(_old([["X"], ["Y", "Z"]]), _g([["X"], ["Y", "Z", "W"]])))
    assert "DSC 180A" in t and "W" in t and "became" in t and t.count("\n") == 0


def test_group_split_is_one_line():
    lines = diff_catalog(_old([["X"], ["Y", "Z"]]), _g([["X"], ["Y"], ["Z"]]))
    assert len(lines) == 1 and "Y or Z" in lines[0] and "became" in lines[0]


def test_group_removed_and_added():
    assert "no longer requires one of A, B" in "\n".join(diff_catalog(_old([["A", "B"]]), _g([])))
    assert "now requires one of A, B" in "\n".join(diff_catalog(_old([]), _g([["B", "A"]])))


def test_only_offerings_run_marks_catalog_not_run(tmp_path):
    import json
    from tests.test_refresh_run import _setup
    from refresh.run import main
    d = _setup(tmp_path)
    (d / "catalog.json").write_text(json.dumps(
        {"fetched_at": "2026-11-01T00:00:00Z", "courses": {}, "status": {"ok": True, "error": None}}))
    (d / "sources.json").write_text("{}")
    rep = tmp_path / "r.md"
    main(["--only", "offerings", "--data-dir", str(d), "--report", str(rep)], session=object())
    row = [l for l in rep.read_text().splitlines() if l.startswith("| catalog")][0]
    assert "not run this time" in row and "2026-11-01" in row


def test_classplanner_only_marks_departments_not_run(tmp_path):
    import json
    from tests.test_refresh_run import _setup
    from refresh.run import main
    d = _setup(tmp_path)
    (d / "offerings.json").write_text(json.dumps({"sources": {"cse": {
        "ok": True, "fetched_at": "2026-11-02T01:00:00Z", "source_url": "https://x.edu/a", "error": None}}}))

    class Boom:
        def get(self, url):
            raise RuntimeError("down")
    rep = tmp_path / "r.md"
    main(["--only", "classplanner", "--data-dir", str(d), "--report", str(rep)], session=Boom())
    lines = rep.read_text().splitlines()
    cse = [l for l in lines if l.startswith("| cse")][0]
    assert "not run this time" in cse and "2026-11-02" in cse
    assert [l for l in lines if l.startswith("| classplanner")][0].split("|")[2].strip() == "FAILED"


def test_sources_table_labels_and_hosts():
    src = {"cse": {"ok": True, "fetched_at": "2026-11-02T01:00:00Z",
                   "source_url": "https://docs.google.com/spreadsheets/" + "x" * 150, "error": None}}
    md = render_report([], [], src, None, today=date(2026, 11, 13), ran={"cse"})
    assert "docs.google.com" in md and "x" * 50 not in md and "2026-11-02" in md
    md2 = render_report([], [], src, None, today=date(2026, 11, 13), ran=set())
    assert "not run this time" in md2
