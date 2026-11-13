"""MATH planned offerings: Bootstrap tables whose first two columns use rowspan."""

from __future__ import annotations

from refresh.ids import normalize_id

from ._common import ShapeError, cell_grid, finish, merge, soup_of

DEPARTMENT = "MATH"
_HEADER = ["COURSE", "COURSE NAME", "LECT", "FALL", "WINTER", "SPRING"]
_COLS = {"FA": 3, "WI": 4, "SP": 5}


def parse(text: str, academic_year: str) -> dict[str, list[str]]:
    # The page carries no years in its headers (the year is the ?year= parameter),
    # so academic_year cannot be checked here.
    out: dict[str, set[str]] = {}
    seen = False
    for table in soup_of(text).find_all("table"):
        grid = cell_grid(table)
        if not grid or [h.upper() for h in grid[0]] != _HEADER:
            continue
        seen = True
        for row in grid[1:]:
            if len(row) != len(_HEADER):
                continue
            cid = normalize_id(row[0], "MATH")
            if cid and cid.startswith("MATH "):
                merge(out, cid, {q for q, i in _COLS.items() if row[i]})
    if not seen:
        raise ShapeError("MATH: no table with COURSE/LECT/FALL/WINTER/SPRING header")
    return finish(out, "MATH")
