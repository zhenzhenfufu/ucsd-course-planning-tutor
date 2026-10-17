"""Deterministic validation of a quarter-by-quarter course plan.

The language model proposes a plan; this module decides whether the plan is
legal. Nothing here calls an API, so the same plan always produces the same
verdict, and a failure can be explained by pointing at a specific rule.

A plan is an ordered list of terms:

    [{"term": "Fall 2026", "courses": ["DSC 10", "MATH 20A"]},
     {"term": "Winter 2027", "courses": ["DSC 20"]}]

Order in the list is the order the terms are taken.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Literal

from prereq_graph import ABSTRACT_SATISFIERS, CourseGraph, build

Severity = Literal["error", "warning"]

# UCSD full-time undergraduate load.
MIN_UNITS_PER_TERM = 12.0
MAX_UNITS_PER_TERM = 22.0
# Above this, the plan is legal but heavy enough to be worth flagging.
HEAVY_UNITS_PER_TERM = 19.0


@dataclass(frozen=True)
class Violation:
    code: str
    severity: Severity
    term: str | None
    course: str | None
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


def _norm(plan: Iterable[dict]) -> list[dict]:
    out = []
    for i, term in enumerate(plan):
        out.append(
            {
                "term": str(term.get("term") or f"Term {i + 1}"),
                "courses": [str(c).strip().upper() for c in term.get("courses", []) if str(c).strip()],
            }
        )
    return out


def validate(plan: Iterable[dict], cg: CourseGraph | None = None,
             completed: Iterable[str] = ()) -> list[Violation]:
    """Check one plan and return every violation found, most severe first.

    `completed` lists courses already finished before the plan starts.
    """
    cg = cg or build()
    terms = _norm(plan)
    violations: list[Violation] = []

    taken: set[str] = {c.strip().upper() for c in completed}
    seen_at: dict[str, str] = {c: "(completed)" for c in taken}
    # Everything the plan contains, in any term. Used only to word the message:
    # "scheduled too late" and "not in the plan at all" are different mistakes
    # and the student needs to be told which one they made.
    anywhere: set[str] = taken | {c for t in terms for c in t["courses"]}

    for term in terms:
        name, courses = term["term"], term["courses"]

        # --- unknown / duplicate -------------------------------------------
        for course in courses:
            if not cg.known(course):
                violations.append(Violation(
                    "UNKNOWN_COURSE", "error", name, course,
                    f"{course} is not in the catalog."))
            elif course in seen_at:
                violations.append(Violation(
                    "DUPLICATE_COURSE", "error", name, course,
                    f"{course} is already scheduled in {seen_at[course]}."))

        if len(set(courses)) != len(courses):
            dupes = sorted({c for c in courses if courses.count(c) > 1})
            for d in dupes:
                violations.append(Violation(
                    "DUPLICATE_IN_TERM", "error", name, d,
                    f"{d} appears twice in {name}."))

        # --- prerequisites ---------------------------------------------------
        # Courses in the same term do not count unless the catalog allows the
        # prerequisite to be taken concurrently.
        same_term = set(courses)
        for course in courses:
            if not cg.known(course):
                continue
            pool = taken | (same_term if cg.concurrent_ok(course) else set())
            for group in cg.missing_groups(course, pool):
                readable = " or ".join(
                    a.strip("<>").replace("-", " ") if a in ABSTRACT_SATISFIERS else a
                    for a in group
                )
                if cg.satisfied(group, taken | same_term):
                    why = "which is scheduled in the same term, not before it"
                elif cg.satisfied(group, anywhere):
                    why = "which the plan schedules in a later term"
                else:
                    why = "which the plan never includes"
                violations.append(Violation(
                    "PREREQ_MISSING", "error", name, course,
                    f"{course} in {name} requires {readable}, {why}."))

        # --- unit load -------------------------------------------------------
        units = sum(cg.units(c) for c in courses if cg.known(c))
        if courses and units < MIN_UNITS_PER_TERM:
            violations.append(Violation(
                "UNITS_BELOW_FULL_TIME", "error", name, None,
                f"{name} has {units:g} units; full-time standing needs "
                f"{MIN_UNITS_PER_TERM:g}."))
        if units > MAX_UNITS_PER_TERM:
            violations.append(Violation(
                "UNITS_OVER_CAP", "error", name, None,
                f"{name} has {units:g} units; the per-quarter cap is "
                f"{MAX_UNITS_PER_TERM:g}."))
        elif units >= HEAVY_UNITS_PER_TERM:
            violations.append(Violation(
                "UNITS_HEAVY", "warning", name, None,
                f"{name} has {units:g} units — legal but heavy."))
        if not courses:
            violations.append(Violation(
                "EMPTY_TERM", "warning", name, None, f"{name} has no courses."))

        for course in courses:
            taken.add(course)
            seen_at.setdefault(course, name)

    order = {"error": 0, "warning": 1}
    return sorted(violations, key=lambda v: (order[v.severity], v.term or "", v.course or ""))


def is_legal(plan: Iterable[dict], cg: CourseGraph | None = None,
             completed: Iterable[str] = ()) -> bool:
    """True when a plan has no errors. Warnings do not make a plan illegal."""
    return not any(v.severity == "error" for v in validate(plan, cg, completed))


def repair_hint(violations: list[Violation]) -> str:
    """A short, machine-readable summary to feed back to the model."""
    errors = [v for v in violations if v.severity == "error"]
    if not errors:
        return ""
    lines = [f"- [{v.code}] {v.message}" for v in errors]
    return (
        "The plan you proposed failed deterministic validation:\n"
        + "\n".join(lines)
        + "\nReturn a corrected plan in the same JSON format. "
          "Do not explain; return only JSON."
    )


if __name__ == "__main__":
    cg = build()
    demo = [
        {"term": "Fall 2026", "courses": ["DSC 10", "MATH 20A", "CSE 11"]},
        {"term": "Winter 2027", "courses": ["DSC 100", "MATH 20B", "DSC 20"]},
    ]
    for v in validate(demo, cg):
        print(f"[{v.severity:7}] {v.code:22} {v.message}")
