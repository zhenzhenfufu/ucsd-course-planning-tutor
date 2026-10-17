"""Prerequisite graph built from the free-text course descriptions.

The catalog stores prerequisites as prose, in two opposite directions:

    "Prerequisite: MATH 20C."              -> MATH 20C is a prereq OF this course
    "Prerequisite for MATH 20C and ..."    -> this course is a prereq of MATH 20C

Parsing the second form as if it were the first reverses the edge, so direction
is decided per sentence before any course code is extracted.

Requirements are kept as an AND of OR-groups:

    "Prerequisites: DSC 40B or CSE 12, DSC 80 or CSE 15L, and a probability course"
    -> [[DSC 40B, CSE 12], [DSC 80, CSE 15L], [<probability>]]

Groups may contain abstract tokens ("a probability course") that no single code
satisfies; ABSTRACT_SATISFIERS lists the courses the catalog itself names as
acceptable. Anything that resolves to neither a code nor a known abstract token
is recorded in `ambiguities` rather than silently dropped.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

CATALOG_PATH = Path(__file__).with_name("dsc_courses.json")
OVERRIDES_PATH = Path(__file__).with_name("prereq_overrides.json")

# A course code: department prefix + number with optional letter suffix.
COURSE_RE = re.compile(r"\b([A-Z]{2,5})\s*(\d{1,3}[A-Z]{0,2})\b")
# A bare number continuing an earlier prefix: "DSC 140A, 140B, 148, and 155".
BARE_NUM_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,3}[A-Z]{0,2})(?![A-Za-z0-9])")

# Three forward-facing sentence kinds with different meanings. Order matters:
# SUBSTITUTION is checked before ADVISORY, and ADVISORY before HARD_FORWARD,
# because "required or recommended for" contains "required ... for".
#
#   substitution -> this course can stand IN PLACE OF the named ones
#   advisory     -> this course is suggested before them, but is not required
#   hard forward -> this course is genuinely a prerequisite of the named ones
SUBSTITUTION_RE = re.compile(r"accepted as|alternative to|alternative probability", re.I)
ADVISORY_RE = re.compile(
    r"required or recommended for|recommended for|strongly recommended|required for", re.I
)
HARD_FORWARD_RE = re.compile(r"(?:required\s+)?prerequisite for", re.I)
# Sentences that state what this course needs.
BACKWARD_RE = re.compile(r"prerequisites?\s*:", re.I)
NONE_RE = re.compile(r"no prerequisites?", re.I)

CONCURRENT_RE = re.compile(r"concurrent", re.I)

# Requirements the catalog phrases in prose, and the courses it names as
# acceptable ways to satisfy them.
ABSTRACT_SATISFIERS: dict[str, list[str]] = {
    "<probability>": ["MATH 180A", "MATH 183", "CSE 103", "ECE 109"],
    "<programming>": ["DSC 20", "DSC 30", "CSE 11", "CSE 12", "DSC 10"],
    "<upper-division standing>": [],   # standing, not a course
    "<instructor approval>": [],       # administrative
    "<qualifying elective>": [],       # depends on the student's track
    "<high school chemistry>": [],     # external
}

ABSTRACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"probability(\s+course)?", re.I), "<probability>"),
    (re.compile(r"programming(\s+(course|background))?", re.I), "<programming>"),
    (re.compile(r"upper-division standing", re.I), "<upper-division standing>"),
    (re.compile(r"instructor approval", re.I), "<instructor approval>"),
    (re.compile(r"qualifying elective", re.I), "<qualifying elective>"),
    (re.compile(r"high school chemistry", re.I), "<high school chemistry>"),
]

# Tails too vague to become edges; recorded as ambiguities instead.
VAGUE_RE = re.compile(
    r"many upper-division|most stem majors|several dsc|some upper-division|"
    r"and most|equivalent",
    re.I,
)


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


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", text or "") if s.strip()]


def _extract_codes(text: str, valid: set[str]) -> list[str]:
    """Pull course codes, expanding bare numbers that continue a prefix."""
    codes: list[str] = []
    last_dept: str | None = None
    pos = 0
    for m in COURSE_RE.finditer(text):
        # Bare numbers sitting between the previous match and this one.
        if last_dept:
            for bm in BARE_NUM_RE.finditer(text[pos:m.start()]):
                cand = f"{last_dept} {bm.group(1)}"
                if cand in valid:
                    codes.append(cand)
        dept, num = m.group(1), m.group(2)
        code = f"{dept} {num}"
        if code in valid:
            codes.append(code)
            last_dept = dept
        pos = m.end()
    if last_dept:
        for bm in BARE_NUM_RE.finditer(text[pos:]):
            cand = f"{last_dept} {bm.group(1)}"
            if cand in valid:
                codes.append(cand)
    # de-duplicate, keep order
    seen: set[str] = set()
    return [c for c in codes if not (c in seen or seen.add(c))]


def _parse_backward(clause: str, valid: set[str]) -> tuple[list[list[str]], list[str]]:
    """Parse the part after 'Prerequisite:' into AND-of-OR groups."""
    body = re.split(r"prerequisites?\s*:", clause, flags=re.I)[-1]
    body = body.rstrip(". ")
    groups: list[list[str]] = []
    unresolved: list[str] = []

    # AND separators: commas and the word "and" (but not inside an "or" pair).
    for chunk in re.split(r",\s*(?:and\s+)?|\s+and\s+", body):
        chunk = chunk.strip()
        if not chunk:
            continue
        options: list[str] = []
        for alt in re.split(r"\s+or\s+", chunk):
            alt = alt.strip()
            if not alt:
                continue
            codes = _extract_codes(alt, valid)
            if codes:
                options.extend(codes)
                continue
            token = next((tok for pat, tok in ABSTRACT_PATTERNS if pat.search(alt)), None)
            if token:
                options.append(token)
            elif not VAGUE_RE.search(alt):
                unresolved.append(alt)
        if options:
            groups.append(options)
    return groups, unresolved


def _load_overrides(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def build(catalog_path: Path | str = CATALOG_PATH,
          overrides_path: Path | str = OVERRIDES_PATH):
    """Parse the catalog into a prerequisite DAG.

    Reviewed corrections come from `prereq_overrides.json` so that the parser
    stays honest about what the prose actually says, and every departure from
    it is written down with a reason.
    """
    courses = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    overrides = _load_overrides(Path(overrides_path))
    by_id = {c["id"]: c for c in courses}
    valid = set(by_id)

    reqs: dict[str, Requirement] = {cid: Requirement(cid) for cid in valid}
    ambiguities: list[dict] = []
    hard_forward: list[tuple[str, str]] = []
    # target course -> courses the catalog says may be taken in its place
    substitutes: dict[str, set[str]] = {}
    advisories: list[tuple[str, str]] = []

    for course in courses:
        cid = course["id"]
        for sent in _split_sentences(course.get("description", "")):
            if NONE_RE.search(sent):
                continue
            if BACKWARD_RE.search(sent):
                groups, unresolved = _parse_backward(sent, valid)
                reqs[cid].groups.extend(groups)
                if CONCURRENT_RE.search(sent):
                    reqs[cid].concurrent_ok = True
                for u in unresolved:
                    ambiguities.append(
                        {"course": cid, "kind": "out-of-catalog-requirement",
                         "text": u, "sentence": sent}
                    )
                continue

            if SUBSTITUTION_RE.search(sent):
                kind, bucket = "substitution", None
            elif ADVISORY_RE.search(sent):
                kind, bucket = "advisory", None
            elif HARD_FORWARD_RE.search(sent):
                kind, bucket = "hard-forward", None
            else:
                continue

            targets = [t for t in _extract_codes(sent, valid) if t != cid]
            for t in targets:
                if kind == "substitution":
                    substitutes.setdefault(t, set()).add(cid)
                elif kind == "advisory":
                    advisories.append((cid, t))
                else:
                    hard_forward.append((cid, t))
            if VAGUE_RE.search(sent) or not targets:
                ambiguities.append(
                    {"course": cid, "kind": f"vague-{kind}",
                     "text": sent, "sentence": sent}
                )

    # Only genuine "prerequisite for" statements become requirements.
    # Substitutions and advisories deliberately do not: treating
    # "accepted as alternative to DSC 140A" as a prerequisite of DSC 140A
    # inverts its meaning, and "recommended for" is not a hard gate.
    for src, dst in hard_forward:
        if src not in reqs[dst].atoms():
            reqs[dst].groups.append([src])

    # Reviewed corrections: facts the prose leaves out.
    abstract = {k: list(v) for k, v in ABSTRACT_SATISFIERS.items()}
    for extra in overrides.get("add_edges", []):
        src, dst = extra["from"], extra["to"]
        if src in valid and dst in valid and src not in reqs[dst].atoms():
            reqs[dst].groups.append([src])
    for token, sats in overrides.get("abstract_satisfiers", {}).items():
        abstract[token] = sorted(set(abstract.get(token, [])) | set(sats))

    graph = nx.DiGraph()
    for cid, c in by_id.items():
        graph.add_node(cid, name=c["name"], units=c.get("units"),
                       department=c.get("department"))
    for cid, req in reqs.items():
        for group in req.groups:
            for atom in group:
                if atom in valid:
                    graph.add_edge(atom, cid, kind="prereq", alternatives=len(group))
    # Advisory edges are kept for visualisation but never gate a plan, so they
    # go in a separate graph rather than polluting the prerequisite DAG.
    advisory_graph = nx.DiGraph()
    advisory_graph.add_nodes_from(graph.nodes)
    advisory_graph.add_edges_from((s, t) for s, t in advisories)

    return CourseGraph(
        graph=graph,
        advisory=advisory_graph,
        requirements=reqs,
        ambiguities=ambiguities,
        courses=by_id,
        substitutes=substitutes,
        abstract_satisfiers=abstract,
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
