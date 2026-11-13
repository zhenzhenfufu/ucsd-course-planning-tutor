"""HDSI (DSC) course offerings: TablePress #tablepress-4, one row per (course, quarter)."""

from __future__ import annotations

import re

from refresh.ids import expand_ids

from ._common import ShapeError, clean, finish, merge, soup_of, term_of

DEPARTMENT = "DSC"
_NUM = re.compile(r"^DSC (\d+)")


def parse(text: str, academic_year: str) -> dict[str, list[str]]:
    table = soup_of(text).find("table", id="tablepress-4")
    if table is None:
        raise ShapeError("DSC: table #tablepress-4 not found")
    head = [clean(th.get_text()) for th in table.select("thead th")]
    if head[:1] != ["Course #"] or head[-1:] != ["Quarter"]:
        raise ShapeError(f"DSC: unexpected header {head!r}")
    out: dict[str, set[str]] = {}
    for tr in table.select("tbody tr"):
        tds = [clean(td.get_text(" ")) for td in tr.find_all("td")]
        if len(tds) < 3:
            continue
        # "DSC-095 (1 IWC)" -> annotation dropped; "DSC-190/291" -> two courses.
        raw = re.sub(r"\([^)]*\)|\*", "", tds[0])
        ids = [i for i in expand_ids(raw, "DSC")
               if i.startswith("DSC ") and int(_NUM.match(i).group(1)) < 200]
        label = tds[-1]
        code = term_of(label, academic_year) if label else None
        if label and code is None:
            raise ShapeError(f"DSC: unrecognised quarter {label!r}")
        for cid in ids:
            merge(out, cid, {code} if code in ("FA", "WI", "SP") else set())
    return finish(out, "DSC")
