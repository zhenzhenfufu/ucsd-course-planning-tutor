"""Physics tentative offerings: #datatable; headers from <thead> only (not <tfoot>)."""

from __future__ import annotations

from refresh.ids import normalize_id

from ._common import ShapeError, clean, finish, merge, quarter_columns, soup_of

DEPARTMENT = "PHYS"


def parse(text: str, academic_year: str) -> dict[str, list[str]]:
    table = soup_of(text).find("table", id="datatable")
    thead = table.find("thead") if table else None
    if thead is None:
        raise ShapeError("PHYS: table #datatable with <thead> not found")
    headers = [clean(th.get_text()) for th in thead.find_all("th")]
    if not headers or headers[0] != "Course":
        raise ShapeError(f"PHYS: unexpected header {headers!r}")
    cols = quarter_columns(headers, academic_year)
    out: dict[str, set[str]] = {}
    for tr in table.select("tbody tr"):
        tds = [clean(td.get_text(" ")) for td in tr.find_all("td")]
        if len(tds) < len(headers):
            continue
        cid = normalize_id(tds[0], "PHYS")
        if cid and cid.startswith("PHYS "):
            merge(out, cid, {q for q, i in cols.items()
                             if tds[i] and tds[i].lower() != "not offered"})
    return finish(out, "PHYS")
