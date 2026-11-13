"""CSE tentative offerings: published Google Sheet, CSV, one row per course."""

from __future__ import annotations

import re

from refresh.ids import normalize_id

from ._common import ShapeError, clean, finish, merge
from .csvgrid import read

DEPARTMENT = "CSE"
_HEADER = re.compile(r"(Fall|Winter|Spring) \d{4}")


def parse(text: str, academic_year: str) -> dict[str, list[str]]:
    header, rows, cols = read(text, ("Course #",), academic_year)
    if len(header) < 2 or header[1] != "Title" or not any(
            _HEADER.fullmatch(h) for h in header[2:]):
        raise ShapeError("CSE header must be Course #,Title,<quarter columns>")
    out: dict[str, set[str]] = {}
    for row in rows:
        cid = normalize_id(clean(row[0]), "CSE") if row else None
        if not cid or not cid.startswith("CSE "):
            continue
        merge(out, cid, {q for q, i in cols.items() if i < len(row) and clean(row[i])})
    return finish(out, "CSE")
