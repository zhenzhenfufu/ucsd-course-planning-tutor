"""COGS tentative offerings: published Google Sheet, gid=866922720 only."""

from __future__ import annotations

import re

from refresh.ids import normalize_id

from ._common import clean, finish, merge
from .csvgrid import read

DEPARTMENT = "COGS"
_SECTION = re.compile(r"\s+[A-Z]\d{2}$")  # "COGS 108 B00" -> "COGS 108"


def parse(text: str, academic_year: str) -> dict[str, list[str]]:
    _, rows, cols = read(text, ("Course",), academic_year)
    out: dict[str, set[str]] = {}
    for row in rows:
        raw = _SECTION.sub("", clean(row[0])) if row else ""
        cid = normalize_id(raw, "COGS") if raw else None
        if not cid or not cid.startswith("COGS "):
            continue
        merge(out, cid, {q for q, i in cols.items() if i < len(row) and clean(row[i])})
    return finish(out, "COGS")
