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
    # "MATH 20B ... Prerequisite for MATH 20C"
    assert cg.graph.has_edge("MATH 20B", "MATH 20C")
    assert not cg.graph.has_edge("MATH 20C", "MATH 20B")


def test_substitution_is_not_a_prerequisite(cg):
    """'CSE 151A accepted as alternative to DSC 140A' must not make CSE 151A a
    prerequisite of DSC 140A — that inverts the sentence."""
    assert "CSE 151A" not in [a for g in cg.requirements["DSC 140A"].groups for a in g]
    assert "CSE 151A" in cg.substitutes["DSC 140A"]


def test_advisory_is_not_a_prerequisite(cg):
    """'MATH 180A required or recommended for DSC 140A' is not a hard gate;
    DSC 140A's probability requirement has other satisfiers."""
    groups = cg.requirements["DSC 140A"].groups
    assert ["MATH 180A"] not in groups
    assert any("<probability>" in g for g in groups)


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
    texts = {a["text"] for a in cg.ambiguities}
    assert "CHEM 4" in texts        # named in prose, absent from the catalog
    assert all(a["kind"] for a in cg.ambiguities)


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
