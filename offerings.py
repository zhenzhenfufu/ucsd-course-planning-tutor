"""Offerings snapshot and lookup (spec "Validator: NOT_OFFERED").

data/offerings.json is written by the refresh run; data/offerings_manual.json
holds hand-entered departments (CHEM, BIOL). Lookup order: exempt -> scheduled
(only when the course's subject has a count > 0 for that term) -> tentative
(official adapter data, else manual) -> unknown. Summer is always unknown.
A missing or unreadable file gives available=False and every lookup is unknown.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from terms import Term, term_from_code

DATA = Path(__file__).parent / "data"
_ORDER = ["FA", "WI", "SP"]

Kind = Literal["exempt", "scheduled_offered", "scheduled_absent", "tentative_offered",
               "tentative_other_quarters", "tentative_unlisted", "tentative_no_quarter",
               "unknown"]


@dataclass
class OfferingStatus:
    kind: Kind
    quarters: list[str] = field(default_factory=list)
    academic_year: str | None = None
    source_url: str | None = None
    # Scheduled: Class Planner's last_full_refresh_at date, else our fetch time.
    # Tentative: when the department plan was fetched (or entered by hand).
    as_of: str | None = None


_UNKNOWN = OfferingStatus("unknown")


def _subject(course_id: str) -> str:
    return course_id.split(" ", 1)[0]


def _read(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _qsort(qs):
    return sorted(qs, key=lambda q: _ORDER.index(q) if q in _ORDER else 9)


_QUARTER_ALIASES = {"fa": "FA", "fall": "FA", "wi": "WI", "winter": "WI",
                    "sp": "SP", "spring": "SP"}


def _norm_quarters(value) -> list[str] | None:
    """A quarters list as FA/WI/SP in that order; None if `value` is not a list.

    Accepts Fall/Winter/Spring or FA/WI/SP in any case and drops anything else,
    so a typo in the hand-entered file cannot reach the validator.
    """
    if not isinstance(value, list):
        return None
    out = {_QUARTER_ALIASES.get(q.strip().lower()) for q in value if isinstance(q, str)}
    return _qsort(out - {None})


def _norm_courses(courses) -> dict[str, list[str]]:
    """{course: quarters} with every quarters list normalised; non-list values dropped."""
    if not isinstance(courses, dict):
        return {}
    out = {}
    for cid, qs in courses.items():
        norm = _norm_quarters(qs)
        if norm is not None:
            out[cid] = norm
    return out


class Offerings:
    def __init__(self, generated_at=None, available=False, scheduled=None, tentative=None):
        self.generated_at = generated_at
        self.available = available
        self.scheduled: dict[str, dict] = scheduled or {}
        self.tentative: dict[str, dict] = tentative or {}

    def _scheduled_block(self, course_id: str, term: Term):
        block = self.scheduled.get(term.code)
        if not isinstance(block, dict):
            return None
        subjects = block.get("subjects") or {}
        count = subjects.get(_subject(course_id), 0)
        if not isinstance(count, int) or count <= 0:
            return None
        return block

    def lookup(self, course_id: str, department: str, term: Term,
               by_arrangement: set[str] = frozenset()) -> OfferingStatus:
        if course_id in by_arrangement:
            return OfferingStatus("exempt")
        if not self.available or term.quarter == "SU":
            return OfferingStatus("unknown")
        block = self._scheduled_block(course_id, term)
        if block is not None:
            kind = "scheduled_offered" if course_id in (block.get("courses") or []) else "scheduled_absent"
            # Class Planner's own refresh date says how current the schedule
            # is; our fetch time is only the fallback.
            last_full = block.get("last_full_refresh_at")
            as_of = last_full[:10] if isinstance(last_full, str) and last_full else block.get("fetched_at")
            return OfferingStatus(kind, [term.quarter], term.academic_year, None, as_of)
        ay = term.academic_year
        entry = (self.tentative.get(ay) or {}).get(department)
        courses = entry.get("courses") if isinstance(entry, dict) else None
        if not courses:
            return OfferingStatus("unknown")
        meta = dict(academic_year=ay, source_url=entry.get("source_url"), as_of=entry.get("fetched_at"))
        quarters = courses.get(course_id)
        if quarters is None:
            return OfferingStatus("tentative_unlisted", [], **meta)
        if not quarters:
            return OfferingStatus("tentative_no_quarter", [], **meta)
        kind = "tentative_offered" if term.quarter in quarters else "tentative_other_quarters"
        return OfferingStatus(kind, _qsort(quarters), **meta)

    def summary(self, course_id: str, department: str) -> str:
        if not self.available:
            return "offerings unavailable"
        parts = []
        for ay in sorted(self.tentative):
            entry = self.tentative[ay].get(department)
            courses = entry.get("courses") if isinstance(entry, dict) else None
            if not courses:
                continue
            qs = courses.get(course_id)
            text = "not listed" if qs is None else (
                ", ".join(_qsort(qs)) if qs else "listed, no quarter planned")
            parts.append(f"{ay} tentative: {text}")
        for code in sorted(self.scheduled, key=lambda c: (term_from_code(c).year, _ORDER.index(term_from_code(c).quarter))
                           if _valid(c) else (9999, 9)):
            block = self._scheduled_block(course_id, term_from_code(code)) if _valid(code) else None
            if block is not None:
                yes = course_id in (block.get("courses") or [])
                parts.append(f"{code} scheduled: {'yes' if yes else 'no'}")
        return " · ".join(parts) if parts else "no offering data"


def _valid(code: str) -> bool:
    try:
        term_from_code(code)
        return True
    except ValueError:
        return False


def _merge_manual(tentative: dict, manual) -> None:
    if not isinstance(manual, dict):
        return
    for ay, depts in manual.items():
        if not isinstance(depts, dict):
            continue
        for dept, entry in depts.items():
            courses = _norm_courses(entry.get("courses")) if isinstance(entry, dict) else {}
            if not courses:
                continue  # unfilled placeholder: not coverage
            existing = tentative.setdefault(ay, {}).get(dept)
            if isinstance(existing, dict) and existing.get("courses"):
                continue  # official adapter data wins
            tentative[ay][dept] = {"source_url": entry.get("source_url"),
                                   "fetched_at": entry.get("entered_at"),
                                   "status": "manual", "courses": courses}


def load_offerings(path: Path = DATA / "offerings.json",
                   manual_path: Path = DATA / "offerings_manual.json") -> Offerings:
    data = _read(path)
    if not isinstance(data, dict):
        return Offerings()
    scheduled, tentative = data.get("scheduled", {}), data.get("tentative", {})
    if not isinstance(scheduled, dict) or not isinstance(tentative, dict):
        return Offerings()
    tentative = {ay: {dept: ({**entry, "courses": _norm_courses(entry.get("courses"))}
                             if isinstance(entry, dict) else entry)
                      for dept, entry in d.items()} if isinstance(d, dict) else {}
                 for ay, d in tentative.items()}
    _merge_manual(tentative, _read(manual_path))
    return Offerings(data.get("generated_at"), True, scheduled, tentative)
