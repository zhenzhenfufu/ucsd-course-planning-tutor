"""Shared helpers for the department tentative-plan adapters. Pure functions, no I/O."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

QUARTERS = ("FA", "WI", "SP")  # academic-year order, not alphabetical


class ShapeError(Exception):
    """The page or sheet does not have the structure the adapter expects."""


_AY_RE = re.compile(r"^(\d{4})-(\d{2}|\d{4})$")
_TERM_RE = re.compile(
    r"^(fall|winter|spring|summer|fa|wi|sp|su|w)\s*(\d{4}|\d{2})?(?![A-Za-z])", re.I)
_CODES = {"fall": "FA", "fa": "FA", "winter": "WI", "wi": "WI", "w": "WI",
          "spring": "SP", "sp": "SP", "summer": "SU", "su": "SU"}


def start_year(academic_year: str) -> int:
    m = _AY_RE.match(academic_year or "")
    if not m:
        raise ShapeError(f"bad academic year {academic_year!r}")
    return int(m.group(1))


def term_of(label: str, academic_year: str) -> str | None:
    """'FA'/'WI'/'SP' for a quarter label, 'SU' for summer, None if not a term label.

    Raises ShapeError when a fall/winter/spring label carries a year that does not
    belong to the academic year (Fall = start year, Winter/Spring = start year + 1).
    """
    m = _TERM_RE.match((label or "").replace("\xa0", " ").strip())
    if not m:
        return None
    code = _CODES[m.group(1).lower()]
    if code != "SU" and m.group(2):
        want = start_year(academic_year) + (0 if code == "FA" else 1)
        year = m.group(2)
        ok = int(year) == want if len(year) == 4 else int(year) == want % 100
        if not ok:
            raise ShapeError(f"{label!r} does not belong to academic year {academic_year}")
    return code


def quarter_columns(headers: list[str], academic_year: str) -> dict[str, int]:
    """Map FA/WI/SP to column index; every one of the three must be present."""
    cols: dict[str, int] = {}
    for i, h in enumerate(headers):
        code = term_of(h, academic_year)
        if code in QUARTERS and code not in cols:
            cols[code] = i
    missing = [q for q in QUARTERS if q not in cols]
    if missing:
        raise ShapeError(f"missing quarter columns {missing} in header {headers!r}")
    return cols


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def ordered(found: set[str]) -> list[str]:
    return [q for q in QUARTERS if q in found]


def soup_of(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, "html.parser")


def cell_grid(table: Tag) -> list[list[str]]:
    """Logical grid of a table's rows, repeating rowspan/colspan cells into every slot."""
    grid: list[list[str]] = []
    pending: dict[int, tuple[int, str]] = {}  # column -> (rows left, text)
    for tr in table.find_all("tr"):
        row: list[str] = []
        col = 0

        def fill():
            nonlocal col
            while col in pending:
                left, txt = pending[col]
                row.append(txt)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col] = (left - 1, txt)
                col += 1

        for cell in tr.find_all(["td", "th"], recursive=False):
            fill()
            txt = clean(cell.get_text(" "))
            span = max(int(cell.get("colspan", 1) or 1), 1)
            rows = max(int(cell.get("rowspan", 1) or 1), 1)
            for _ in range(span):
                row.append(txt)
                if rows > 1:
                    pending[col] = (rows - 1, txt)
                col += 1
        fill()
        grid.append(row)
    return grid


def merge(out: dict[str, set[str]], cid: str, quarters: set[str]) -> None:
    out.setdefault(cid, set()).update(quarters)


def finish(out: dict[str, set[str]], what: str) -> dict[str, list[str]]:
    if not out:
        raise ShapeError(f"{what}: no courses found")
    return {cid: ordered(q) for cid, q in out.items()}
