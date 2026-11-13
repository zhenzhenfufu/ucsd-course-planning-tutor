"""Catalog page parser and snapshot builder (fixtures use invented text)."""

import json
from pathlib import Path

from refresh.catalog import (CATALOG_BASE, build_catalog_snapshot, parse_course_page,
                             parse_edition)

FIX = Path(__file__).parent / "fixtures"
DSC_URL = CATALOG_BASE + "DSC.html"
DSC_HTML = (FIX / "catalog_dsc.html").read_text()
CSE_HTML = (FIX / "catalog_cse.html").read_text()


def _dsc():
    return {c.id: c for c in parse_course_page(DSC_HTML, "DSC", DSC_URL)}


def test_description_without_class_is_not_shifted():
    c = _dsc()
    assert c["DSC 40B"].prereq_groups == [["DSC 20"], ["DSC 40A"]]
    assert c["DSC 40B"].conditions == ["major restriction"]
    assert c["DSC 80"].prereq_groups == [["DSC 30"], ["DSC 40B"], ["DSC 152", "ECON 120A"]]
    assert c["DSC 40A"].prereq_groups == [["DSC 30"], ["MATH 20C", "MATH 31BH"]]


def test_r_suffix_is_normalized():
    assert "DSC 40B" in _dsc() and "DSC 40B/R" not in _dsc()


def test_duplicate_anchor_links_to_page_only():
    c = _dsc()
    assert c["DSC 40B"].catalog_url == DSC_URL
    assert c["DSC 30"].catalog_url == DSC_URL + "#dsc30"
    assert c["DSC 40A"].catalog_url == DSC_URL + "#dsc40a"


def test_tag_is_stripped_from_title():
    c = {x.id: x for x in parse_course_page(CSE_HTML, "CSE", CATALOG_BASE + "CSE.html")}
    assert c["CSE 8A"].title == "Fixture Coding One"
    assert c["CSE 8A"].units == 4


def test_graduate_courses_are_skipped():
    assert "DSC 200" not in _dsc()
    assert "DSC 190" in _dsc()
    assert (_dsc()["DSC 190"].units, _dsc()["DSC 190"].units_max) == (2, 4)


def test_edition_and_hash():
    assert parse_edition(DSC_HTML) == "2099–00"
    assert parse_edition("<p>none</p>") is None
    h = _dsc()["DSC 30"].content_hash
    assert h.startswith("sha256:") and len(h) == 71


def test_snapshot_keeps_stale_course_and_lists_referenced():
    pages = {"DSC": parse_course_page(DSC_HTML, "DSC", DSC_URL)}
    old = {"id": "DSC 99", "department": "DSC", "title": "Old", "units": 4, "units_max": 4,
           "units_text": "4", "prereq_groups": [], "concurrent_ok": False, "conditions": [],
           "ambiguities": [], "catalog_url": "u", "content_hash": "sha256:x", "stale": False}
    snap = build_catalog_snapshot(
        pages, ["DSC 30", "DSC 40A", "DSC 40B", "DSC 80", "DSC 99"],
        {"courses": {"DSC 99": old}}, "2026-11-12T00:00:00Z", "2099–00")
    assert snap["courses"]["DSC 99"]["stale"] is True
    assert snap["courses"]["DSC 99"]["title"] == "Old"
    assert snap["courses"]["DSC 80"]["stale"] is False
    assert "DSC 190" not in snap["courses"]
    assert snap["referenced"]["DSC 152"] == {"defined": False}
    assert snap["referenced"]["MATH 20C"] == {"defined": False}
    assert "DSC 30" not in snap["referenced"]
    assert snap["source"] == CATALOG_BASE and snap["catalog_edition"] == "2099–00"


def test_referenced_defined_when_on_a_parsed_page():
    pages = {"DSC": parse_course_page(DSC_HTML, "DSC", DSC_URL),
             "CSE": parse_course_page(CSE_HTML, "CSE", CATALOG_BASE + "CSE.html")}
    snap = build_catalog_snapshot(pages, ["DSC 80", "CSE 12"], None, "t", None)
    assert snap["referenced"]["CSE 8A"] == {"defined": True}
    assert snap["referenced"]["CSE 11"] == {"defined": False}


def test_no_description_text_is_stored():
    pages = {"DSC": parse_course_page(DSC_HTML, "DSC", DSC_URL)}
    snap = build_catalog_snapshot(pages, list(_dsc()), None, "t", None)
    blob = json.dumps(snap)
    for word in ("Zorblax", "Flumox", "Snarfle", "Plonk", "wibble", "Restricted to students"):
        assert word not in blob


def test_own_id_is_dropped_from_prereq_groups():
    html = ('<p class="course-name">DSC 77. Invented Title (4)</p>'
            '<p class="course-descriptions">Zzz. <strong>Prerequisites:</strong> '
            'DSC 10 and (DSC 77 or DSC 20). DSC 77. </p>'
            '<p class="course-name">DSC 78. Other Invented (4)</p>'
            '<p class="course-descriptions"><strong>Prerequisites:</strong> DSC 78.</p>')
    c = {x.id: x for x in parse_course_page(html, "DSC", DSC_URL)}
    assert c["DSC 77"].prereq_groups == [["DSC 10"], ["DSC 20"]]
    assert c["DSC 78"].prereq_groups == []


def test_referenced_never_lists_abstract_tokens():
    html = ('<p class="course-name">DSC 77. Invented Title (4)</p>'
            '<p class="course-descriptions"><strong>Prerequisites:</strong> '
            'A probability course and DSC 10.</p>')
    pages = {"DSC": parse_course_page(html, "DSC", DSC_URL)}
    snap = build_catalog_snapshot(pages, ["DSC 77"], None, "t", None)
    assert snap["courses"]["DSC 77"]["prereq_groups"] == [["<probability>"], ["DSC 10"]]
    assert list(snap["referenced"]) == ["DSC 10"]


# ---- content_hash covers the parsed record, not the page text ----------------

def test_hash_ignores_description_prose_and_markup():
    from refresh.catalog import course_hash
    noisy = (DSC_HTML.replace("Zorblax quuxes the wibble frames.", "Rewritten blurb, new words.")
             .replace("<body>", "<body><!-- build 8f3a nonce=xyz --><div class='ad'>ad</div>"))
    a, b = _dsc()["DSC 30"], {c.id: c for c in parse_course_page(noisy, "DSC", DSC_URL)}["DSC 30"]
    assert a.content_hash == b.content_hash
    from dataclasses import asdict
    assert a.content_hash == course_hash(asdict(a))


def test_hash_changes_when_parsed_record_changes():
    changed = DSC_HTML.replace("DSC 30 and DSC 40B/R and", "DSC 30 and DSC 40A/R and")
    old = _dsc()["DSC 80"].content_hash
    new = {c.id: c for c in parse_course_page(changed, "DSC", DSC_URL)}["DSC 80"].content_hash
    assert old != new


def test_hash_survives_snapshot_round_trip():
    from refresh.catalog import course_hash
    pages = {"DSC": parse_course_page(DSC_HTML, "DSC", DSC_URL)}
    snap = build_catalog_snapshot(pages, ["DSC 30", "DSC 80"], None, "t", "e")
    back = json.loads(json.dumps(snap, indent=2, ensure_ascii=False))
    for rec in back["courses"].values():
        assert course_hash(rec) == rec["content_hash"]


def test_committed_catalog_hashes_match_records():
    from refresh.catalog import course_hash
    snap = json.loads((Path(__file__).resolve().parent.parent / "data" / "catalog.json")
                      .read_text(encoding="utf-8"))
    bad = [cid for cid, rec in snap["courses"].items() if course_hash(rec) != rec["content_hash"]]
    assert bad == []
