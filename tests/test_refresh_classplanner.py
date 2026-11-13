"""Class Planner client tests, with a fake session."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from refresh.classplanner import ALLOWED, BASE, SchemaError, fetch_term_courses, fetch_terms  # noqa: E402
from refresh.http import FetchError, FetchResult  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


class FakeSession:
    def __init__(self, get_result=None, pages=()):
        self.get_result = get_result
        self.pages = list(pages)
        self.posts = []

    def get(self, url):
        self.url = url
        return self.get_result

    def post_json(self, url, payload):
        self.posts.append((url, payload))
        page = self.pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return page


def ok(text, status=200):
    return FetchResult("u", status, text, False, {})


def test_allowed_is_public_only():
    assert ALLOWED == {"classplanner.apps.ucsd.edu": ("/api/v1/public/",)}


def test_fetch_terms_parsed():
    s = FakeSession(ok((FIX / "cp_terms.json").read_text()))
    terms = fetch_terms(s)
    assert s.url == BASE + "/api/v1/public/catalog/terms"
    assert [t["term_code"] for t in terms] == ["WI99", "SP99"]
    assert terms[1]["configured"] is False


def test_fetch_terms_missing_key_or_status():
    bad = json.dumps({"terms": [{"term_code": "WI99"}]})
    with pytest.raises(SchemaError):
        fetch_terms(FakeSession(ok(bad)))
    with pytest.raises(SchemaError):
        fetch_terms(FakeSession(ok("{}", 401)))
    with pytest.raises(SchemaError):
        fetch_terms(FakeSession(ok("not json")))


def test_courses_normalized_and_payload():
    s = FakeSession(pages=[load("cp_search_dsc.json")])
    assert fetch_term_courses(s, "WI99", "DSC") == {"DSC 80", "DSC 40A", "DSC 100"}
    url, payload = s.posts[0]
    assert url == BASE + "/api/v1/public/catalog/courses/search"
    assert payload == {"term_code": "WI99", "subject_code": ["DSC"], "limit": 48, "offset": 0}


def test_bare_number_uses_subject():
    page = {"total": 1, "offset": 0, "courses": [{"module_code": "080"}]}
    assert fetch_term_courses(FakeSession(pages=[page]), "WI99", "DSC") == {"DSC 80"}


def test_paging_two_pages():
    p1 = {"total": 3, "offset": 0, "courses": [{"module_code": "DSC-001"}, {"module_code": "DSC-010"}]}
    p2 = {"total": 3, "offset": 2, "courses": [{"module_code": "DSC-020"}]}
    s = FakeSession(pages=[p1, p2])
    assert fetch_term_courses(s, "WI99", "DSC") == {"DSC 1", "DSC 10", "DSC 20"}
    assert [p["offset"] for _, p in s.posts] == [0, 2]


def test_zero_results_is_empty_set():
    page = {"total": 0, "offset": 0, "courses": []}
    assert fetch_term_courses(FakeSession(pages=[page]), "WI99", "ZZZ") == set()


def test_missing_total_raises():
    with pytest.raises(SchemaError):
        fetch_term_courses(FakeSession(pages=[{"courses": []}]), "WI99", "DSC")


def test_http_error_propagates_not_empty():
    with pytest.raises(FetchError):
        fetch_term_courses(FakeSession(pages=[FetchError("401")]), "WI99", "DSC")
