"""Tests for the parts that must not drift: the graph, the checker, retrieval.

None of these touch the network, so they run in CI and without an API key.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prereq_graph import build, check_acyclic, topo_layers  # noqa: E402
from retrieval import TfidfIndex, build_documents, expand_along_graph  # noqa: E402
from validator import (  # noqa: E402
    MAX_UNITS_PER_TERM,
    MIN_UNITS_PER_TERM,
    is_legal,
    validate,
)


@pytest.fixture(scope="module")
def cg():
    return build()


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------
def test_graph_is_a_dag(cg):
    assert check_acyclic(cg.graph) == []


def test_every_course_is_a_node(cg):
    assert set(cg.graph.nodes) == set(cg.courses)


def test_backward_statement_points_the_right_way(cg):
    # "DSC 100 ... Prerequisites: DSC 40B and DSC 80"
    assert cg.graph.has_edge("DSC 80", "DSC 100")
    assert not cg.graph.has_edge("DSC 100", "DSC 80")


def test_forward_statement_points_the_right_way(cg):
    # MATH 20B -> MATH 20C is a reviewed ordering (add_edges) and must bind.
    assert cg.graph.has_edge("MATH 20B", "MATH 20C")
    assert not cg.graph.has_edge("MATH 20C", "MATH 20B")
    assert ["MATH 20A"] in cg.requirements["MATH 20B"].groups
    assert cg.missing_groups("MATH 20B", set()) == [["MATH 20A"]]
    assert cg.missing_groups("MATH 20B", {"MATH 20A"}) == []
    assert cg.missing_groups("MATH 20C", set()) == [["MATH 20B"]]


def test_validator_enforces_the_add_edges_ordering(cg):
    wrong = [{"term": "F", "courses": ["MATH 20B", "DSC 10", "CSE 11"]},
             {"term": "W", "courses": ["MATH 20A", "DSC 20", "CSE 12"]}]
    bad = [v for v in validate(wrong, cg) if v.code == "PREREQ_MISSING"]
    assert any(v.course == "MATH 20B" for v in bad)
    plan = [{"term": "F", "courses": ["MATH 20B", "DSC 10", "CSE 11"]}]
    assert not any(v.code == "PREREQ_MISSING" and v.course == "MATH 20B"
                   for v in validate(plan, cg, completed=["MATH 20A"]))


def test_substitution_is_not_a_prerequisite(cg):
    """'CSE 151A accepted as alternative to DSC 140A' must not make CSE 151A a
    prerequisite of DSC 140A — that inverts the sentence."""
    assert "CSE 151A" not in [a for g in cg.requirements["DSC 140A"].groups for a in g]
    assert "CSE 151A" in cg.substitutes["DSC 140A"]


def test_advisory_is_not_a_prerequisite(cg):
    """'MATH 180A required or recommended for DSC 140A' is not a hard gate.

    The catalog names six courses that satisfy DSC 140A's probability
    requirement, so MATH 180A must appear as one option among several rather
    than as a requirement of its own. (Before the October 2026 catalog rebuild
    this group was the abstract token <probability>; the dataset now carries the
    named alternatives, which is the same claim stated more precisely.)
    """
    groups = cg.requirements["DSC 140A"].groups
    assert ["MATH 180A"] not in groups
    probability = next(g for g in groups if "MATH 180A" in g)
    assert {"ECE 109", "MATH 183"} <= set(probability)


def test_or_group_is_kept_as_alternatives(cg):
    groups = cg.requirements["CSE 158"].groups
    assert sorted(["DSC 40B", "CSE 12"]) in [sorted(g) for g in groups]


def test_abstract_requirement_has_named_satisfiers(cg):
    assert cg.satisfied(["<probability>"], {"ECE 109"})
    assert cg.satisfied(["<probability>"], {"MATH 183"})
    assert not cg.satisfied(["<probability>"], {"DSC 10"})


def test_substitute_satisfies_a_group(cg):
    assert cg.satisfied(["DSC 80"], {"CSE 15L"})


def test_out_of_catalog_references_are_reported_not_dropped(cg):
    # MATH 31AH is an honours alternative the catalog names but the scope omits.
    assert "MATH 31AH" in cg.referenced
    options = {o for g in cg.requirements["DSC 40A"].groups for o in g}
    assert "MATH 31AH" in options
    assert all(a["kind"] for a in cg.ambiguities)


def test_dsc_180a_accepts_dsc_152(cg):
    assert ["DSC 152", "MATH 189"] in [sorted(g) for g in cg.requirements["DSC 180A"].groups]


def test_completed_out_of_scope_option_satisfies(cg):
    assert "ECON 120A" not in cg.courses
    assert cg.satisfied(["ECON 120A", "MATH 180A"], {"ECON 120A"})


def test_topological_layers_cover_everything(cg):
    layers = topo_layers(cg.graph)
    assert sum(len(x) for x in layers) == len(cg.courses)


# --------------------------------------------------------------------------
# validator
# --------------------------------------------------------------------------
def test_legal_plan_passes(cg):
    plan = [
        {"term": "F", "courses": ["DSC 10", "MATH 20A", "CSE 11"]},
        {"term": "W", "courses": ["DSC 20", "MATH 20B", "MATH 18"]},
    ]
    assert is_legal(plan, cg)


def test_prereq_after_dependent_is_rejected(cg):
    plan = [
        {"term": "F", "courses": ["DSC 100", "MATH 20A", "CSE 11"]},
        {"term": "W", "courses": ["DSC 80", "MATH 20B", "MATH 18"]},
    ]
    codes = {v.code for v in validate(plan, cg) if v.severity == "error"}
    assert "PREREQ_MISSING" in codes


def test_same_term_prereq_is_rejected_unless_concurrent(cg):
    plan = [{"term": "F", "courses": ["DSC 10", "DSC 20", "DSC 30"]}]
    assert not is_legal(plan, cg)


def test_concurrent_prereq_is_allowed(cg):
    # "PHYS 2A ... Prerequisite: MATH 20B (concurrent OK)"
    plan = [{"term": "F", "courses": ["PHYS 2A", "MATH 20B", "DSC 10"]}]
    assert is_legal(plan, cg, completed=["MATH 20A"])


def test_completed_courses_satisfy_prerequisites(cg):
    plan = [{"term": "F", "courses": ["DSC 100", "MATH 20A", "CSE 11"]}]
    assert is_legal(plan, cg, completed=["DSC 40B", "DSC 80"])


def test_under_full_time_is_an_error(cg):
    plan = [{"term": "F", "courses": ["DSC 10", "MATH 20A"]}]      # 8 units
    codes = {v.code for v in validate(plan, cg)}
    assert "UNITS_BELOW_FULL_TIME" in codes


def test_over_cap_is_an_error(cg):
    courses = ["DSC 10", "MATH 20A", "CSE 11", "MATH 18", "CHEM 11", "BILD 1"]
    plan = [{"term": "F", "courses": courses}]
    total = sum(cg.units(c) for c in courses)
    assert total > MAX_UNITS_PER_TERM
    assert "UNITS_OVER_CAP" in {v.code for v in validate(plan, cg)}


def test_duplicate_across_terms_is_an_error(cg):
    plan = [
        {"term": "F", "courses": ["DSC 10", "MATH 20A", "CSE 11"]},
        {"term": "W", "courses": ["DSC 10", "MATH 20B", "MATH 18"]},
    ]
    assert "DUPLICATE_COURSE" in {v.code for v in validate(plan, cg)}


def test_unknown_course_is_an_error(cg):
    plan = [{"term": "F", "courses": ["DSC 999", "MATH 20A", "CSE 11"]}]
    assert "UNKNOWN_COURSE" in {v.code for v in validate(plan, cg)}


def test_heavy_load_is_a_warning_not_an_error(cg):
    plan = [{"term": "F", "courses": ["DSC 10", "MATH 20A", "CSE 11", "MATH 18",
                                      "CHEM 11"]}]                 # 20 units
    vs = validate(plan, cg)
    assert MIN_UNITS_PER_TERM < 20 <= MAX_UNITS_PER_TERM
    assert "UNITS_HEAVY" in {v.code for v in vs}
    assert is_legal(plan, cg)


def test_violations_carry_the_term_and_course(cg):
    plan = [{"term": "Fall", "courses": ["DSC 100", "MATH 20A", "CSE 11"]}]
    v = next(v for v in validate(plan, cg) if v.code == "PREREQ_MISSING")
    assert v.term == "Fall" and v.course == "DSC 100"


# --------------------------------------------------------------------------
# retrieval
# --------------------------------------------------------------------------
def test_documents_include_structure(cg):
    docs = build_documents(cg)
    assert "Prerequisites:" in docs["DSC 100"]
    assert "DSC 40B" in docs["DSC 100"]
    assert "Leads to:" in docs["DSC 80"]


def test_documents_have_keywords_not_descriptions(cg):
    docs = build_documents(cg)
    assert "Topics:" in docs["DSC 100"] and "SQL" in docs["DSC 100"]
    assert all(d.count("Prerequisites:") == 1 for d in docs.values())


def test_tfidf_finds_sql(cg):
    index = TfidfIndex(build_documents(cg))
    hits = [h.course_id for h in index.search("SQL", k=3)]
    assert "DSC 100" in hits


def test_tfidf_finds_an_obvious_match(cg):
    index = TfidfIndex(build_documents(cg))
    hits = [h.course_id for h in index.search("machine learning", k=5)]
    assert any(h.startswith("DSC 140") or h.startswith("CSE 151") for h in hits)


def test_graph_expansion_adds_missing_prerequisites(cg):
    """The point of expansion: a retrieved course drags its prereqs in."""
    expanded = expand_along_graph(["DSC 100"], cg, hops=1)
    assert "DSC 40B" in expanded and "DSC 80" in expanded


def test_graph_expansion_is_stable_on_roots(cg):
    assert expand_along_graph(["DSC 10"], cg, hops=1) == ["DSC 10"]


def test_retrieval_context_is_much_smaller_than_the_catalog(cg):
    import json

    from retrieval import context_for

    index = TfidfIndex(build_documents(cg))
    ctx = context_for("what do I need before DSC 100", index, k=6, cg=cg)
    full = json.dumps(cg.courses, ensure_ascii=False)
    assert len(ctx) < 0.25 * len(full)


def test_current_data_needs_no_dropped_edges(cg):
    assert [a for a in cg.ambiguities if a["kind"] == "cycle-edge-dropped"] == []
    assert check_acyclic(cg.graph) == []


def test_cse_158_has_only_its_real_prerequisites(cg):
    flat = {o for g in cg.requirements["CSE 158"].groups for o in g}
    assert not flat & {"CSE 258", "CSE 158R", "DSC 148"}


# --------------------------------------------------------------------------
# NOT_OFFERED
# --------------------------------------------------------------------------

from offerings import load_offerings  # noqa: E402

_FIX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def off():
    return load_offerings(_FIX / "offerings_small.json", _FIX / "no_manual.json")


def _no(plan, cg, off):
    return [v for v in validate(plan, cg, offerings=off) if v.code == "NOT_OFFERED"]


def test_not_offered_scheduled_error(cg, off):
    (v,) = _no([{"term": "Winter 2027", "courses": ["DSC 30"]}], cg, off)
    assert v.severity == "error" and v.term == "Winter 2027" and v.course == "DSC 30"
    assert v.message == ("DSC 30 is not on the published Winter 2027 Schedule of Classes "
                         "(Class Planner, refreshed 2026-11-12T00:00:00Z).")
    assert not is_legal([{"term": "Winter 2027", "courses": ["DSC 30"]}], cg, offerings=off)


def test_not_offered_other_quarters_warning(cg, off):
    plan = [{"term": "Spring 2027", "courses": ["DSC 30"]}]
    (v,) = _no(plan, cg, off)
    assert v.severity == "warning"
    assert v.message == ("DSC 30 is listed for Fall only in the DSC 2026-27 tentative plan, "
                         "not Spring.")
    assert not any(x.code == "NOT_OFFERED" and x.severity == "error"
                   for x in validate(plan, cg, offerings=off))


def test_not_offered_unlisted_warning(cg, off):
    (v,) = _no([{"term": "Spring 2027", "courses": ["DSC 20"]}], cg, off)
    assert v.severity == "warning"
    assert v.message == ("DSC 20 is not on the DSC 2026-27 tentative course list; "
                         "check the Schedule of Classes.")


def test_not_offered_no_quarter_warning(cg, off):
    (v,) = _no([{"term": "Spring 2027", "courses": ["DSC 80"]}], cg, off)
    assert v.severity == "warning"
    assert v.message == ("DSC 80 is on the DSC 2026-27 tentative plan with no quarter "
                         "planned; check the Schedule of Classes.")


@pytest.mark.parametrize("label,course", [
    ("Term 1", "DSC 30"), ("F", "DSC 30"), ("fall 2026", "DSC 30"),
    ("Summer 2027", "DSC 30"), ("Fall 2030", "DSC 30"),
    ("Winter 2027", "DSC 199"), ("Spring 2027", "DSC 10"),
])
def test_not_offered_silent_cases(cg, off, label, course):
    assert _no([{"term": label, "courses": [course]}], cg, off) == []


def test_not_offered_silent_when_unavailable(cg, tmp_path):
    gone = load_offerings(tmp_path / "missing.json", tmp_path / "missing2.json")
    assert not gone.available
    assert _no([{"term": "Winter 2027", "courses": ["DSC 30"]}], cg, gone) == []


# --------------------------------------------------------------------------
# Planner / retrieval use real quarters
# --------------------------------------------------------------------------
from datetime import date  # noqa: E402

from planner import default_start_term, eligible_now  # noqa: E402
from terms import parse_term  # noqa: E402


def test_eligible_drops_scheduled_absent(cg, off):
    wi27 = parse_term("Winter 2027")
    taken = {"DSC 10", "DSC 20"}
    assert "DSC 30" in eligible_now(cg, taken, term=None, offerings=off)
    assert "DSC 30" not in eligible_now(cg, taken, term=wi27, offerings=off)
    assert "DSC 30" in eligible_now(cg, taken)
    assert "DSC 20" in eligible_now(cg, {"DSC 10"}, term=wi27, offerings=off)


def test_eligible_without_offerings_data_unchanged(cg, tmp_path):
    gone = load_offerings(tmp_path / "missing.json", tmp_path / "missing2.json")
    wi27 = parse_term("Winter 2027")
    assert eligible_now(cg, set(), term=wi27, offerings=gone) == eligible_now(cg, set())


def test_default_start_term_uses_latest_scheduled(off):
    assert default_start_term(off, date(2026, 11, 12)).code == "WI27"


def test_default_start_term_without_data(tmp_path):
    gone = load_offerings(tmp_path / "missing.json", tmp_path / "missing2.json")
    assert default_start_term(gone, date(2026, 11, 12)).name == "Fall 2027"
    assert default_start_term(gone, date(2027, 9, 1)).name == "Fall 2027"
    assert default_start_term(gone, date(2027, 6, 1)).name == "Fall 2027"


def test_documents_include_offerings(cg, off):
    docs = build_documents(cg, off)
    assert "Offered: " + off.summary("DSC 30", "DSC") in docs["DSC 30"]
    assert "Offered:" not in build_documents(cg)["DSC 30"]
