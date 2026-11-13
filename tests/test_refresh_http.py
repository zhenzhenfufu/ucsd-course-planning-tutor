"""Tests for the polite HTTP client. A fake transport stands in for the network."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from refresh.http import (  # noqa: E402
    UA,
    FetchError,
    PathNotAllowed,
    PoliteSession,
    RobotsDisallowed,
    SSORedirect,
)

HOST = "catalog.ucsd.edu"


class FakeResponse:
    def __init__(self, status=200, text="", headers=None, json_data=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}
        self._json = json_data

    def json(self):
        return self._json


class FakeTransport:
    """Records calls and returns scripted responses keyed by URL (lists are consumed in order)."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def request(self, method, url, headers=None, json=None, allow_redirects=False, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}),
                           "json": json, "allow_redirects": allow_redirects, "timeout": timeout})
        scripted = self.routes.get(url, FakeResponse(404))
        if isinstance(scripted, list):
            scripted = scripted.pop(0) if len(scripted) > 1 else scripted[0]
        if isinstance(scripted, Exception):
            raise scripted
        return scripted


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


@pytest.fixture
def clock():
    return Clock()


def make(routes, clock, **kw):
    t = FakeTransport(routes)
    s = PoliteSession(transport=t, clock=clock, sleep=clock.sleep, **kw)
    return s, t


def test_sends_user_agent(clock):
    s, t = make({f"https://{HOST}/page": FakeResponse(text="hi")}, clock)
    r = s.get(f"https://{HOST}/page")
    assert r.text == "hi" and r.status == 200 and not r.not_modified
    assert all(c["headers"]["User-Agent"] == UA for c in t.calls)
    assert all(c["allow_redirects"] is False and c["timeout"] == 30 for c in t.calls)


def test_spaces_requests_per_host(clock):
    s, _ = make({f"https://{HOST}/a": FakeResponse(text="a"),
                 f"https://{HOST}/b": FakeResponse(text="b")}, clock)
    s.get(f"https://{HOST}/a")
    s.get(f"https://{HOST}/b")
    assert clock.sleeps
    assert all(x == pytest.approx(1.0) for x in clock.sleeps)


def test_stops_on_sso_redirect(clock):
    s, _ = make({f"https://{HOST}/page": FakeResponse(
        302, headers={"Location": "https://a5.ucsd.edu/tritON/login"})}, clock)
    with pytest.raises(SSORedirect):
        s.get(f"https://{HOST}/page")


@pytest.mark.parametrize("location", [
    "https://A5.UCSD.EDU/tritON/login",
    "https://a5.ucsd.edu:443/tritON/login",
    "https://A5.ucsd.edu:443/login",
    "//a5.ucsd.edu:443/login",
])
def test_stops_on_sso_redirect_any_case_or_port(clock, location):
    s, t = make({f"https://{HOST}/page": FakeResponse(302, headers={"Location": location})}, clock)
    with pytest.raises(SSORedirect):
        s.get(f"https://{HOST}/page")
    assert not any("a5.ucsd.edu" in c["url"].lower() for c in t.calls)


def test_host_case_and_port_share_robots_and_throttle(clock):
    s, t = make({f"https://{HOST}/a": FakeResponse(text="a"),
                 f"https://CATALOG.UCSD.EDU:443/b": FakeResponse(text="b")}, clock)
    s.get(f"https://{HOST}/a")
    s.get("https://CATALOG.UCSD.EDU:443/b")
    assert [c["url"] for c in t.calls if c["url"].endswith("/robots.txt")] == [
        f"https://{HOST}/robots.txt"]
    assert len(clock.sleeps) == 2  # robots->a, a->b: one host, one interval


def test_path_allowlist_ignores_host_case_and_port(clock):
    allowed = {"classplanner.apps.ucsd.edu": ("/api/v1/public/",)}
    ok = "https://ClassPlanner.apps.ucsd.edu:443/api/v1/public/x"
    s, t = make({ok: FakeResponse(text="ok")}, clock, allowed_prefixes=allowed)
    assert s.get(ok).text == "ok"
    with pytest.raises(PathNotAllowed):
        s.get("https://CLASSPLANNER.apps.ucsd.edu:443/api/v1/planner/x")


def test_follows_relative_redirect_and_caps_at_five(clock):
    routes = {f"https://{HOST}/old": FakeResponse(301, headers={"Location": "/new"}),
              f"https://{HOST}/new": FakeResponse(text="moved")}
    s, _ = make(routes, clock)
    assert s.get(f"https://{HOST}/old").text == "moved"
    loop = {f"https://{HOST}/loop": FakeResponse(302, headers={"Location": "/loop"})}
    s2, _ = make(loop, clock)
    with pytest.raises(FetchError):
        s2.get(f"https://{HOST}/loop")


def test_robots_wildcard_disallow(clock):
    s, t = make({f"https://{HOST}/robots.txt": FakeResponse(text="User-agent: *\nDisallow: *.pdf\n"),
                 f"https://{HOST}/x.pdf": FakeResponse(text="pdf")}, clock)
    with pytest.raises(RobotsDisallowed):
        s.get(f"https://{HOST}/x.pdf")
    assert all(c["url"] != f"https://{HOST}/x.pdf" for c in t.calls)


def test_robots_redirect_means_no_rules(clock):
    s, t = make({f"https://{HOST}/robots.txt": FakeResponse(
                     307, headers={"Location": "https://a5.ucsd.edu/login"}),
                 f"https://{HOST}/page": FakeResponse(text="ok")}, clock)
    assert s.get(f"https://{HOST}/page").text == "ok"
    s.get(f"https://{HOST}/page")
    assert sum(c["url"].endswith("/robots.txt") for c in t.calls) == 1


def test_conditional_get_uses_cache(clock, tmp_path):
    url = f"https://{HOST}/page"
    routes = {url: [FakeResponse(text="body", headers={"ETag": '"v1"', "Last-Modified": "Mon"}),
                    FakeResponse(304)]}
    s, t = make(routes, clock, cache_dir=tmp_path)
    first = s.get(url)
    assert not first.not_modified
    second = s.get(url)
    page_calls = [c for c in t.calls if c["url"] == url]
    assert page_calls[1]["headers"]["If-None-Match"] == '"v1"'
    assert page_calls[1]["headers"]["If-Modified-Since"] == "Mon"
    assert second.text == "body" and second.not_modified


def test_path_allowlist(clock):
    allowed = {"classplanner.apps.ucsd.edu": ("/api/v1/public/",)}
    s, t = make({"https://classplanner.apps.ucsd.edu/api/v1/public/x": FakeResponse(text="ok")},
                clock, allowed_prefixes=allowed)
    assert s.get("https://classplanner.apps.ucsd.edu/api/v1/public/x").text == "ok"
    with pytest.raises(PathNotAllowed):
        s.get("https://classplanner.apps.ucsd.edu/api/v1/planner/x")
    with pytest.raises(PathNotAllowed):
        s.get("https://other.ucsd.edu/api/v1/public/x")
    assert all("planner/x" not in c["url"] for c in t.calls)


def test_retries_5xx_with_backoff_then_fails(clock):
    url = f"https://{HOST}/flaky"
    s, t = make({url: [FakeResponse(503), FakeResponse(500), FakeResponse(200, text="ok")]}, clock)
    assert s.get(url).text == "ok"
    assert 2 in clock.sleeps and 4 in clock.sleeps
    s2, t2 = make({url: FakeResponse(503)}, Clock())
    with pytest.raises(FetchError):
        s2.get(url)
    assert sum(c["url"] == url for c in t2.calls) == 3


def test_post_json_returns_parsed_body(clock):
    url = "https://classplanner.apps.ucsd.edu/api/v1/public/search"
    s, t = make({url: FakeResponse(json_data={"courses": []})}, clock)
    assert s.post_json(url, {"term": "FA26"}) == {"courses": []}
    call = [c for c in t.calls if c["url"] == url][0]
    assert call["method"] == "POST" and call["json"] == {"term": "FA26"}


def test_redirect_into_disallowed_path_is_blocked(clock):
    allowed = {"classplanner.apps.ucsd.edu": ("/api/v1/public/",)}
    base = "https://classplanner.apps.ucsd.edu"
    routes = {f"{base}/api/v1/public/x": FakeResponse(302, headers={"Location": "/api/v1/planner/x"}),
              f"{base}/api/v1/planner/x": FakeResponse(text="private")}
    s, t = make(routes, clock, allowed_prefixes=allowed)
    with pytest.raises(PathNotAllowed):
        s.get(f"{base}/api/v1/public/x")
    assert all("planner/x" not in c["url"] for c in t.calls)


def test_redirect_to_robots_disallowed_url_is_blocked(clock):
    routes = {f"https://{HOST}/robots.txt": FakeResponse(text="User-agent: *\nDisallow: /private\n"),
              f"https://{HOST}/page": FakeResponse(302, headers={"Location": "/private/a"}),
              f"https://{HOST}/private/a": FakeResponse(text="no")}
    s, t = make(routes, clock)
    with pytest.raises(RobotsDisallowed):
        s.get(f"https://{HOST}/page")
    assert all(c["url"] != f"https://{HOST}/private/a" for c in t.calls)


def _cookie_probe(session):
    """Run two GETs through `session` against a server that sets a cookie; return what was sent."""
    import http.client
    from types import SimpleNamespace

    import requests
    from requests.adapters import BaseAdapter

    seen = []

    class Adapter(BaseAdapter):
        def send(self, request, **kw):
            seen.append(request.headers.get("Cookie"))
            msg = http.client.HTTPMessage()
            msg["Set-Cookie"] = "sid=secret; Path=/"
            resp = requests.Response()
            resp.status_code = 200
            resp.url = request.url
            resp._content = b"ok"
            # extract_cookies_to_jar only parses Set-Cookie when raw carries an _original_response
            resp.raw = SimpleNamespace(_original_response=SimpleNamespace(msg=msg))
            return resp

        def close(self):
            pass

    session.mount("https://", Adapter())
    session.request("GET", "https://catalog.ucsd.edu/a")
    session.request("GET", "https://catalog.ucsd.edu/b")
    return seen


def test_cookie_probe_discriminates_bare_session():
    """Sanity: the probe really does replay cookies on a plain requests.Session."""
    import requests

    assert _cookie_probe(requests.Session()) == [None, "sid=secret"]


def test_default_session_keeps_no_cookies_and_ignores_env():
    from refresh.http import _default_session

    session = _default_session()
    assert session.trust_env is False
    assert _cookie_probe(session) == [None, None]
    assert len(session.cookies) == 0
