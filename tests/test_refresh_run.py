"""refresh.run catalog part, with a fake session serving invented fixtures."""

import json
from pathlib import Path

import pytest

from refresh.http import FetchResult
from refresh.run import main

FIX = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_REPORT = REPO_ROOT / "refresh_report.md"


def _report_state():
    return ROOT_REPORT.stat().st_mtime_ns if ROOT_REPORT.exists() else None


@pytest.fixture(autouse=True, scope="module")
def _repo_root_report_untouched():
    """CI runs refresh.run and then these tests in the repo root; a test that
    rewrote ./refresh_report.md would replace the real report in the PR body."""
    before = _report_state()
    yield
    assert _report_state() == before, "a test wrote refresh_report.md in the repo root"


@pytest.fixture(autouse=True)
def _cwd_is_tmp(tmp_path, monkeypatch):
    """Belt and braces: even a call without --report writes into tmp_path."""
    monkeypatch.chdir(tmp_path)
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
    assert main(["--only", "catalog", "--data-dir", str(d),
                 "--report", str(d / "r.md")], session=s) == 0
    snap = json.loads((d / "catalog.json").read_text())
    assert set(snap["courses"]) == {"DSC 30", "CSE 8A"}
    assert sorted(s.urls) == ["https://catalog.ucsd.edu/courses/CSE.html",
                              "https://catalog.ucsd.edu/courses/DSC.html"]


def test_catalog_shape_failure_keeps_previous(tmp_path):
    d = _setup(tmp_path)
    (d / "catalog.json").write_text('{"previous": true}')
    s = FakeSession({"DSC": "<html><p>redesigned</p></html>",
                     "CSE": (FIX / "catalog_cse.html").read_text()})
    assert main(["--only", "catalog", "--data-dir", str(d),
                 "--report", str(d / "r.md")], session=s) == 1
    assert json.loads((d / "catalog.json").read_text()) == {"previous": True}


# ---- offerings + classplanner ----------------------------------------------

COGS_URL = "https://docs.google.com/spreadsheets/d/e/X/pub?gid=866922720&single=true&output=csv"
SOURCES = {"2026-27": {
    "DSC": {"url": "https://dsc.example/o", "kind": "html", "url_verified": True},
    "CSE": {"url": "https://cse.example/o.csv", "kind": "csv", "url_verified": True},
    "COGS": {"url": COGS_URL, "kind": "csv", "url_verified": True}}}
SCOPE2 = {"by_arrangement": [], "courses": {
    "DSC 10": {"department": "DSC", "keywords": ["a"]},
    "DSC 30": {"department": "DSC", "keywords": ["a"]},
    "CSE 8A": {"department": "CSE", "keywords": ["b"]}}}
TERMS = {"terms": [
    {"term_code": "WI27", "last_full_refresh_at": "2026-11-01T00:00:00Z", "configured": True},
    {"term_code": "SP27", "last_full_refresh_at": None, "configured": False}]}


class FakeSession2:
    def __init__(self, pages, fail_subject=None):
        self.pages, self.fail_subject = pages, fail_subject
        self.urls, self.posts = [], []

    def get(self, url):
        self.urls.append(url)
        if url.endswith("/terms"):
            return FetchResult(url, 200, json.dumps(TERMS), False, {})
        return FetchResult(url, 200, self.pages[url], False, {})

    def post_json(self, url, payload):
        self.posts.append(payload)
        subj = payload["subject_code"][0]
        if subj == self.fail_subject:
            from refresh.http import FetchError
            raise FetchError("boom")
        ids = {"DSC": ["DSC 10"], "CSE": [], "": []}[subj]
        return {"total": len(ids), "courses": [{"module_code": i} for i in ids]}


def _setup2(tmp_path):
    (tmp_path / "scope.json").write_text(json.dumps(SCOPE2))
    (tmp_path / "sources.json").write_text(json.dumps(SOURCES))
    return tmp_path


def _pages(cse=None):
    return {"https://dsc.example/o": (FIX / "offer_dsc.html").read_text(),
            "https://cse.example/o.csv": cse if cse is not None else (FIX / "offer_cse.csv").read_text(),
            COGS_URL: (FIX / "offer_cogs.csv").read_text()}


def test_failed_adapter_keeps_previous_block(tmp_path):
    d = _setup2(tmp_path)
    prev = {"source_url": "old", "courses": {"CSE 8A": ["FA"]}}
    (d / "offerings.json").write_text(json.dumps({"tentative": {"2026-27": {"CSE": prev}}}))
    s = FakeSession2(_pages(cse="<html>not a sheet</html>"))
    assert main(["--only", "offerings", "--data-dir", str(d),
                 "--report", str(d / "r.md")], session=s) == 0
    out = json.loads((d / "offerings.json").read_text())
    assert out["tentative"]["2026-27"]["CSE"] == prev
    assert out["sources"]["cse"]["ok"] is False and out["sources"]["cse"]["error"]
    assert out["sources"]["dsc"]["ok"] is True
    assert "DSC 40A" in out["tentative"]["2026-27"]["DSC"]["courses"]


def test_unconfigured_term_skipped(tmp_path):
    d = _setup2(tmp_path)
    s = FakeSession2(_pages())
    assert main(["--only", "classplanner", "--data-dir", str(d),
                 "--report", str(d / "r.md")], session=s) == 0
    out = json.loads((d / "offerings.json").read_text())
    assert set(out["scheduled"]) == {"WI27"}
    assert out["scheduled"]["WI27"]["subjects"] == {"CSE": 0, "DSC": 1}
    assert out["scheduled"]["WI27"]["courses"] == ["DSC 10"]
    assert out["sources"]["classplanner"]["ok"] is True
    assert all(p["term_code"] == "WI27" for p in s.posts)


def test_subject_failure_is_omitted_and_partial(tmp_path):
    d = _setup2(tmp_path)
    s = FakeSession2(_pages(), fail_subject="CSE")
    assert main(["--only", "classplanner", "--data-dir", str(d),
                 "--report", str(d / "r.md")], session=s) == 0
    out = json.loads((d / "offerings.json").read_text())
    assert out["scheduled"]["WI27"]["subjects"] == {"DSC": 1}
    assert "partial" in out["sources"]["classplanner"]["error"]


def test_cogs_wrong_gid_refused_without_fetch(tmp_path):
    d = _setup2(tmp_path)
    bad = json.loads(json.dumps(SOURCES))
    bad["2026-27"]["COGS"]["url"] = COGS_URL.replace("866922720", "1")
    (d / "sources.json").write_text(json.dumps(bad))
    s = FakeSession2(_pages())
    assert main(["--only", "offerings", "--data-dir", str(d),
                 "--report", str(d / "r.md")], session=s) == 0
    out = json.loads((d / "offerings.json").read_text())
    assert out["sources"]["cogs"]["ok"] is False
    assert not any("gid=1" in u for u in s.urls)


def test_all_sources_failed_exits_1(tmp_path):
    d = _setup2(tmp_path)

    class Dead:
        def get(self, url):
            raise RuntimeError("down")

        post_json = get
    assert main(["--only", "offerings", "classplanner", "--data-dir", str(d),
                 "--report", str(d / "r.md")], session=Dead()) == 1
    out = json.loads((d / "offerings.json").read_text())
    assert out["sources"]["classplanner"]["ok"] is False
    assert "RuntimeError" in out["sources"]["classplanner"]["error"]


def test_default_selects_all_sources(tmp_path, capsys):
    import refresh.run as run

    class Dead:
        def get(self, url):
            raise RuntimeError("down")

        post_json = get

    d = _setup(tmp_path)
    (d / "sources.json").write_text(json.dumps(SOURCES))
    assert run.main(["--data-dir", str(d), "--report", str(d / "r.md")], session=Dead()) == 1
    err = capsys.readouterr().err
    for name in ("catalog", "offerings", "classplanner"):
        assert name in err


def test_main_writes_report_only_where_told(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    d = _setup(tmp_path / "data")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    s = FakeSession({"DSC": (FIX / "catalog_dsc.html").read_text(),
                     "CSE": (FIX / "catalog_cse.html").read_text()})
    report = tmp_path / "out" / "report.md"
    report.parent.mkdir()
    assert main(["--only", "catalog", "--data-dir", str(d), "--report", str(report)],
                session=s) == 0
    assert report.read_text().strip()
    assert list(cwd.iterdir()) == []
