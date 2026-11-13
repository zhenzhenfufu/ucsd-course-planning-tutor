"""Prerequisite graph built from the generated catalog snapshot (data/catalog.json).

Requirements are an AND of OR-groups, already parsed by the refresh code:

    [[DSC 40B, CSE 12], [DSC 80, CSE 15L], [<probability>]]

Groups may contain abstract tokens ("a probability course") that no single code
satisfies; ABSTRACT_SATISFIERS lists the courses the catalog itself names as
acceptable. Options outside the scope are kept in the groups (a completed
out-of-scope course still satisfies its group) but never become graph nodes.
Reviewed decisions the catalog cannot carry live in `prereq_overrides.json`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from refresh.prereq_parse import ABSTRACT_PATTERNS, ABSTRACT_SATISFIERS  # noqa: F401

# A fragment the parser could not turn into a course names a test-score route in.
PLACEMENT_RE = re.compile(r"placement|\bAP\b")
DATA = Path(__file__).with_name("data")
CATALOG_PATH = DATA / "catalog.json"
SCOPE_PATH = DATA / "scope.json"
OVERRIDES_PATH = Path(__file__).with_name("prereq_overrides.json")

@dataclass
class Requirement:
    """One course's prerequisites: AND over groups, OR within a group."""

    course: str
    groups: list[list[str]] = field(default_factory=list)
    concurrent_ok: bool = False

    def atoms(self) -> list[str]:
        return [a for g in self.groups for a in g]

    def is_empty(self) -> bool:
        return not self.groups


@dataclass
class CourseGraph:
    graph: nx.DiGraph                    # prerequisite DAG
    advisory: nx.DiGraph                 # "recommended before" hints
    requirements: dict[str, Requirement]
    ambiguities: list[dict]
    courses: dict[str, dict]
    substitutes: dict[str, set[str]]     # course -> courses accepted in its place
    abstract_satisfiers: dict[str, list[str]] = field(default_factory=dict)
    by_arrangement: set[str] = field(default_factory=set)
    referenced: dict[str, dict] = field(default_factory=dict)
    catalog_meta: dict = field(default_factory=dict)

    def satisfied(self, group: list[str], taken: set[str]) -> bool:
        """A group is met if any option, or an accepted substitute, is taken."""
        for atom in group:
            if atom in taken:
                return True
            if taken & self.substitutes.get(atom, set()):
                return True
            if atom in self.abstract_satisfiers:
                satisfiers = self.abstract_satisfiers[atom]
                if not satisfiers:      # standing/approval: not checkable here
                    return True
                if taken & set(satisfiers):
                    return True
        return False

    def missing_groups(self, course: str, taken: set[str]) -> list[list[str]]:
        req = self.requirements.get(course)
        if req is None:
            return []
        return [g for g in req.groups if not self.satisfied(g, taken)]

    def concurrent_ok(self, course: str) -> bool:
        req = self.requirements.get(course)
        return bool(req and req.concurrent_ok)

    def units(self, course: str) -> float:
        return float(self.courses.get(course, {}).get("units") or 0)

    def known(self, course: str) -> bool:
        return course in self.courses


def _load_overrides(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def build(catalog_path: Path | str = CATALOG_PATH,
          scope_path: Path | str = SCOPE_PATH,
          overrides_path: Path | str = OVERRIDES_PATH):
    """Build the prerequisite DAG from the catalog snapshot plus reviewed overrides."""
    snap = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    scope = json.loads(Path(scope_path).read_text(encoding="utf-8"))
    overrides = _load_overrides(Path(overrides_path))
    in_scope = set(scope["courses"])

    by_id: dict[str, dict] = {}
    reqs: dict[str, Requirement] = {}
    ambiguities: list[dict] = []
    for cid, rec in snap["courses"].items():
        if cid not in in_scope:
            continue
        links = dict(scope["courses"][cid].get("links") or {})
        links["Catalog"] = rec["catalog_url"]
        by_id[cid] = {
            "id": cid, "department": rec["department"], "name": rec["title"],
            "units": rec["units"], "units_max": rec["units_max"],
            "keywords": list(scope["courses"][cid].get("keywords") or []),
            "links": links, "catalog_url": rec["catalog_url"],
            "conditions": list(rec.get("conditions") or []),
            "stale": bool(rec.get("stale")),
        }
        reqs[cid] = Requirement(cid, [list(g) for g in rec["prereq_groups"]],
                                bool(rec.get("concurrent_ok")))
        if any(PLACEMENT_RE.search(a["fragment"]) for a in rec.get("ambiguities") or []):
            # A placement exam or AP score also satisfies the line, and the planner
            # cannot see test scores. The catalog's course groups are therefore not
            # hard gates; orderings that still bind come back through add_edges.
            reqs[cid].groups = []
            ambiguities.append({"course": cid, "kind": "placement-bypass",
                                "text": "placement or AP score also satisfies"})
        for amb in rec.get("ambiguities") or []:
            ambiguities.append({"course": cid, "kind": amb["kind"],
                                "text": amb["fragment"]})
    valid = set(by_id)

    # Reviewed corrections: facts the catalog line leaves out.
    abstract = {k: list(v) for k, v in ABSTRACT_SATISFIERS.items()}
    for extra in overrides.get("add_edges", []):
        src, dst = extra["from"], extra["to"]
        if src in valid and dst in valid and src not in reqs[dst].atoms():
            reqs[dst].groups.append([src])
    for token, sats in overrides.get("abstract_satisfiers", {}).items():
        abstract[token] = sorted(set(abstract.get(token, [])) | set(sats))
    substitutes: dict[str, set[str]] = {}
    for sub in overrides.get("substitutes", []):
        substitutes.setdefault(sub["replaces"], set()).add(sub["course"])

    graph = nx.DiGraph()
    for cid, c in by_id.items():
        graph.add_node(cid, name=c["name"], units=c.get("units"),
                       department=c.get("department"))
    # Single-option groups first; an alternative that would close a cycle
    # (cross-listed courses naming each other, e.g. DSC 148 / CSE 158) is dropped.
    for want_single in (True, False):
        for cid, req in reqs.items():
            for group in req.groups:
                if (len(group) == 1) != want_single:
                    continue
                for atom in group:
                    if atom not in valid or atom == cid:
                        continue
                    if not want_single and nx.has_path(graph, cid, atom):
                        ambiguities.append({"course": cid, "kind": "cycle-edge-dropped",
                                            "text": f"{atom} before {cid}"})
                        continue
                    graph.add_edge(atom, cid, kind="prereq", alternatives=len(group))
    # Advisory edges are kept for visualisation but never gate a plan.
    advisory_graph = nx.DiGraph()
    advisory_graph.add_nodes_from(graph.nodes)
    advisory_graph.add_edges_from(
        (e["from"], e["to"]) for e in overrides.get("advisory_edges", [])
        if e["from"] in valid and e["to"] in valid)

    return CourseGraph(
        graph=graph, advisory=advisory_graph, requirements=reqs,
        ambiguities=ambiguities, courses=by_id, substitutes=substitutes,
        abstract_satisfiers=abstract,
        by_arrangement=set(scope.get("by_arrangement") or []),
        referenced=dict(snap.get("referenced") or {}),
        catalog_meta={"fetched_at": snap.get("fetched_at"),
                      "catalog_edition": snap.get("catalog_edition")},
    )


def check_acyclic(graph: nx.DiGraph) -> list[list[str]]:
    """Return every cycle found; an empty list means the graph is a DAG."""
    try:
        return [] if nx.is_directed_acyclic_graph(graph) else list(nx.simple_cycles(graph))
    except nx.NetworkXNoCycle:
        return []


def topo_layers(graph: nx.DiGraph) -> list[list[str]]:
    """Courses grouped by earliest possible term (longest path from a root)."""
    return [sorted(layer) for layer in nx.topological_generations(graph)]


def unlocks(graph: nx.DiGraph, course: str) -> list[str]:
    """Courses that become reachable once `course` is taken."""
    return sorted(nx.descendants(graph, course)) if course in graph else []


if __name__ == "__main__":
    cg = build()
    g, reqs = cg.graph, cg.requirements
    cycles = check_acyclic(g)
    with_reqs = sum(1 for r in reqs.values() if not r.is_empty())
    or_groups = sum(1 for r in reqs.values() for grp in r.groups if len(grp) > 1)
    abstract = sum(1 for r in reqs.values() for grp in r.groups
                   for a in grp if a in ABSTRACT_SATISFIERS)

    print(f"courses            : {g.number_of_nodes()}")
    print(f"prerequisite edges : {g.number_of_edges()}")
    print(f"advisory edges     : {cg.advisory.number_of_edges()}")
    print(f"substitution rules : {sum(len(v) for v in cg.substitutes.values())}")
    print(f"with requirements  : {with_reqs}")
    print(f"OR groups          : {or_groups}")
    print(f"abstract atoms     : {abstract}")
    print(f"cycles             : {len(cycles)} {cycles if cycles else '(DAG)'}")
    print(f"ambiguities        : {len(cg.ambiguities)}")
    print(f"depth (layers)     : {len(topo_layers(g))}")
