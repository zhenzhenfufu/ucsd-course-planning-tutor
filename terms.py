"""Quarter labels for the planner, validator and offerings lookup.

Conventions:
- Quarters are FA, WI, SP, SU. The academic year runs Fall to Summer, so
  FA26, WI27, SP27 and SU27 all belong to "2026-27". A Summer term's
  academic year is the one that started the previous Fall.
- next_term skips summer: SP -> FA of the same calendar year. (SU, if given,
  also steps to FA of the same year.)
- term_from_code raises ValueError on a bad code; it is only fed validated
  Class Planner codes. parse_term never raises: labels it cannot place
  ("Term 1", "F", "Fall", ...) return None.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Quarter = Literal["FA", "WI", "SP", "SU"]

_NAMES = {"FA": "Fall", "WI": "Winter", "SP": "Spring", "SU": "Summer"}
_BY_NAME = {v.lower(): k for k, v in _NAMES.items()}
_NAME_RE = re.compile(r"^(fall|winter|spring|summer)\s+(\d{4})$", re.I)
_CODE_RE = re.compile(r"^(FA|WI|SP|SU)(\d{2})$", re.I)


@dataclass(frozen=True)
class Term:
    quarter: Quarter
    year: int

    @property
    def code(self) -> str:
        return f"{self.quarter}{self.year % 100:02d}"

    @property
    def name(self) -> str:
        return f"{_NAMES[self.quarter]} {self.year}"

    @property
    def academic_year(self) -> str:
        start = self.year if self.quarter == "FA" else self.year - 1
        return f"{start}-{(start + 1) % 100:02d}"


def parse_term(label: str) -> Term | None:
    if not isinstance(label, str):
        return None
    s = label.strip()
    m = _NAME_RE.match(s)
    if m:
        return Term(_BY_NAME[m.group(1).lower()], int(m.group(2)))  # type: ignore[arg-type]
    m = _CODE_RE.match(s)
    if m:
        return Term(m.group(1).upper(), 2000 + int(m.group(2)))  # type: ignore[arg-type]
    return None


def term_from_code(code: str) -> Term:
    t = parse_term(code) if isinstance(code, str) and _CODE_RE.match(code.strip()) else None
    if t is None:
        raise ValueError(f"bad term code: {code!r}")
    return t


def next_term(t: Term) -> Term:
    if t.quarter == "FA":
        return Term("WI", t.year + 1)
    if t.quarter == "WI":
        return Term("SP", t.year)
    return Term("FA", t.year)  # SP (and SU) -> next Fall; summer skipped


def terms_from(start: Term, n: int) -> list[Term]:
    out: list[Term] = []
    t = start
    for _ in range(max(n, 0)):
        out.append(t)
        t = next_term(t)
    return out
