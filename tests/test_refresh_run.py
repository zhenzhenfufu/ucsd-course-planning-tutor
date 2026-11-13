"""refresh.run catalog part, with a fake session serving invented fixtures."""

import json
from pathlib import Path

from refresh.http import FetchResult
from refresh.run import main

FIX = Path(__file__).parent / "fixtures"
SCOPE = {"by_arrangement": [], "courses": {
    "DSC 30": {"department": "DSC", "keywords": ["a"]},
    "CSE 8A": {"department": "CSE", "keywords": ["b"]}}}


class FakeSession:
    def __init__(self, pages):
        self.pages, self.urls = pages, []

    def get(self, url):
        self.urls.append(url)
        subject = url.rsplit("/", 1)[1].removesuffix(".html")
        return FetchResult(url, 200, self.pages[subject], False, {})


def _setup(tmp_path):
    (tmp_path / "scope.json").write_text(json.dumps(SCOPE))
    return tmp_path


def test_catalog_run_writes_snapshot(tmp_path):
    d = _setup(tmp_path)
    s = FakeSession({"DSC": (FIX / "catalog_dsc.html").read_text(),
                     "CSE": (FIX / "catalog_cse.html").read_text()})
    assert main(["--only", "catalog", "--data-dir", str(d)], session=s) == 0
    snap = json.loads((d / "catalog.json").read_text())
    assert set(snap["courses"]) == {"DSC 30", "CSE 8A"}
    assert sorted(s.urls) == ["https://catalog.ucsd.edu/courses/CSE.html",
                              "https://catalog.ucsd.edu/courses/DSC.html"]


def test_catalog_shape_failure_keeps_previous(tmp_path):
    d = _setup(tmp_path)
    (d / "catalog.json").write_text('{"previous": true}')
    s = FakeSession({"DSC": "<html><p>redesigned</p></html>",
                     "CSE": (FIX / "catalog_cse.html").read_text()})
    assert main(["--only", "catalog", "--data-dir", str(d)], session=s) == 1
    assert json.loads((d / "catalog.json").read_text()) == {"previous": True}
