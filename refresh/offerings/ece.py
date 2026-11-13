"""ECE tentative course list: hand-edited table keyed on the catalog href fragment."""

from __future__ import annotations

import re

from ._common import ShapeError, clean, finish, merge, quarter_columns, soup_of

DEPARTMENT = "ECE"
_FRAG = re.compile(r"#ece0*(\d+[a-z]{0,2})$", re.I)
_TEXT = re.compile(r"ECE\s*0*(\d+)([A-Z]{0,2})(?![A-Za-z0-9])", re.I)


def _course_id(td) -> str | None:
    for a in td.find_all("a"):
        m = _FRAG.search(a.get("href", ""))
        if m:
            return f"ECE {m.group(1).upper()}"
    first = td.find("p") or td
    m = _TEXT.match(clean(first.get_text(" ")))
    return f"ECE {m.group(1)}{m.group(2).upper()}" if m else None


def parse(text: str, academic_year: str) -> dict[str, list[str]]:
    soup = soup_of(text)
    for style in soup.find_all("style"):  # junk CDATA blocks inside rows
        style.decompose()
    out: dict[str, set[str]] = {}
    seen = False
    for table in soup.find_all("table"):
        first = table.find("tr")
        headers = [clean(c.get_text()) for c in first.find_all(["th", "td"])] if first else []
        if not headers or headers[0].upper() != "COURSE":
            continue
        cols = quarter_columns(headers, academic_year)  # by header position, never data-title
        seen = True
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) < len(headers):
                continue
            cid = _course_id(tds[0])
            if cid:
                merge(out, cid, {q for q, i in cols.items() if clean(tds[i].get_text(" "))})
    if not seen:
        raise ShapeError("ECE: no table with a COURSE header")
    return finish(out, "ECE")
