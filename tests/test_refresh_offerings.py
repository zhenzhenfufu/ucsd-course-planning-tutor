"""Department tentative-plan adapters, run against small invented fixtures."""

from pathlib import Path

import pytest

from refresh.offerings import ADAPTERS, ShapeError
from refresh.offerings import cogs, cse, dsc, ece, math, phys

FIX = Path(__file__).parent / "fixtures"
AY = "2026-27"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_adapters_registry():
    assert set(ADAPTERS) == {"DSC", "CSE", "MATH", "COGS", "PHYS", "ECE"}
    assert all(m.DEPARTMENT == k for k, m in ADAPTERS.items())


def test_dsc_happy_path():
    got = dsc.parse(load("offer_dsc.html"), AY)
    assert got["DSC 40A"] == ["FA", "WI", "SP"]
    assert got["DSC 95"] == ["FA", "SP"]  # sorted by quarter order; "(1 IWC)" stripped
    assert got["DSC 100"] == ["WI"]  # summer ignored
    assert got["DSC 190"] == ["WI"]


def test_dsc_drops_graduate_rows():
    got = dsc.parse(load("offer_dsc.html"), AY)
    assert "DSC 291" not in got and "DSC 599" not in got and "DSC 250" not in got
    assert all(int(k.split()[1].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) < 200 for k in got)


def test_dsc_rejects_wrong_year_and_missing_table():
    with pytest.raises(ShapeError):
        dsc.parse(load("offer_dsc.html"), "2027-28")
    with pytest.raises(ShapeError):
        dsc.parse("<html><body>nothing</body></html>", AY)


def test_cse_happy_path():
    got = cse.parse(load("offer_cse.csv"), AY)
    assert got["CSE 8A"] == ["FA", "WI", "SP"]
    assert got["CSE 11"] == ["FA"]
    assert got["CSE 100R"] == ["WI"]
    assert got["CSE 4GS"] == []


def test_cogs_collapses_sections():
    got = cogs.parse(load("offer_cogs.csv"), AY)
    assert got["COGS 9"] == ["FA", "WI"]
    assert got["COGS 18"] == ["FA", "WI", "SP"]
    assert got["COGS 108"] == ["FA", "WI", "SP"]
    assert got["COGS 188"] == ["FA"]
    assert not any("A00" in k or "B00" in k for k in got)


def test_csv_adapter_rejects_html():
    page = load("offer_html_instead_of_csv.txt")
    for mod in (cse, cogs):
        with pytest.raises(ShapeError):
            mod.parse(page, AY)
    with pytest.raises(ShapeError):
        cse.parse("", AY)


def test_csv_adapters_reject_other_tab_and_wrong_year():
    with pytest.raises(ShapeError):
        cogs.parse("Instructor,Fall 2026,Winter 2027,Spring 2027\nX,1,2,3\n", AY)
    with pytest.raises(ShapeError):
        cse.parse(load("offer_cse.csv"), "2025-26")


def test_math_rowspan():
    got = math.parse(load("offer_math.html"), AY)
    # three sections under one rowspan cell: quarters are OR-ed across them
    assert got["MATH 20A"] == ["FA", "WI"]
    assert got["MATH 181B"] == ["FA", "SP"]
    assert got["MATH 31AH"] == ["FA", "SP"]  # "MATH 31 AH" normalizes
    assert got["MATH 173A"] == ["FA"]  # nbsp cell is blank


def test_math_requires_table():
    with pytest.raises(ShapeError):
        math.parse("<html><table><tr><th>X</th></tr></table></html>", AY)


def test_phys_headers_from_thead_only():
    got = phys.parse(load("offer_phys.html"), AY)
    assert got["PHYS 2A"] == ["FA", "WI", "SP"]
    assert got["PHYS 1AL"] == ["FA"]  # malformed cell still counts; "Not offered" does not
    assert got["PHYS 4A"] == ["WI"]  # STAFF = offered
    assert got["PHYS 4B"] == ["SP"]


def test_phys_year_mismatch_in_thead():
    with pytest.raises(ShapeError):
        phys.parse(load("offer_phys.html"), "2027-28")


def test_ece_happy_path():
    got = ece.parse(load("offer_ece.html"), AY)
    assert got["ECE 5"] == ["FA", "WI"]  # zero padding stripped, summer column ignored
    assert got["ECE 17"] == ["FA", "SP"]  # junk <style> ignored
    assert got["ECE 111"] == ["WI"]  # no href fragment: text fallback


def test_ece_uses_href_fragment():
    got = ece.parse(load("offer_ece.html"), AY)
    assert "ECE 10 8" not in got
    assert got["ECE 108"] == ["FA", "SP"]


def test_ece_wrong_year_header():
    with pytest.raises(ShapeError):
        ece.parse(load("offer_ece.html"), "2025-26")


# ---- content_hash covers the parsed course->quarters mapping -----------------

def test_offerings_hash_is_order_insensitive_and_content_sensitive():
    from refresh.run import courses_hash
    a = courses_hash({"DSC 10": ["FA", "WI"], "DSC 20": []})
    assert a == courses_hash({"DSC 20": [], "DSC 10": ["WI", "FA"]})
    assert a != courses_hash({"DSC 10": ["FA"], "DSC 20": []})


def test_committed_offerings_hashes_match_courses():
    import json as _json
    from pathlib import Path as _P

    from refresh.run import courses_hash
    data = _json.loads((_P(__file__).resolve().parent.parent / "data" / "offerings.json")
                       .read_text(encoding="utf-8"))
    bad = [(ay, d) for ay, depts in data["tentative"].items() for d, b in depts.items()
           if b.get("content_hash") != courses_hash(b["courses"])]
    assert bad == []
