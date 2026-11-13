"""The only HTTP client refresh code may use.

Polite by construction: fixed User-Agent, one request per interval per host,
robots.txt honored, conditional GETs, no cookies, and it refuses to follow a
redirect into UCSD single sign-on.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from protego import Protego

UA = "ucsd-course-planning-tutor (student project)"
SSO_HOST = "a5.ucsd.edu"
TIMEOUT = 30
MAX_REDIRECTS = 5
BACKOFFS = (2, 4)


class FetchError(Exception):
    pass


class SSORedirect(FetchError):
    pass


class RobotsDisallowed(FetchError):
    pass


class PathNotAllowed(FetchError):
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    not_modified: bool
    headers: dict[str, str]


class PoliteSession:
    def __init__(self, transport=None, min_interval: float = 1.0, clock=time.monotonic,
                 sleep=time.sleep, cache_dir: Path | None = None,
                 allowed_prefixes: dict[str, tuple[str, ...]] | None = None):
        self.transport = transport if transport is not None else requests.Session()
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.allowed_prefixes = allowed_prefixes
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, Protego | None] = {}

    # -- public API ---------------------------------------------------------

    def get(self, url: str) -> FetchResult:
        self._check_allowed(url)
        self._check_robots(url)
        headers = {"User-Agent": UA}
        cached = self._load_cache(url)
        if cached:
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]
        resp = self._send("GET", url, headers)
        out_headers = dict(resp.headers)
        if resp.status_code == 304 and cached:
            return FetchResult(url, 304, cached["text"], True, out_headers)
        if resp.status_code == 200:
            self._store_cache(url, resp.headers, resp.text)
        return FetchResult(url, resp.status_code, resp.text, False, out_headers)

    def post_json(self, url: str, payload: dict) -> dict:
        self._check_allowed(url)
        self._check_robots(url)
        resp = self._send("POST", url, {"User-Agent": UA}, payload)
        if resp.status_code >= 400:
            raise FetchError(f"POST {url} returned {resp.status_code}")
        return resp.json()

    # -- internals ----------------------------------------------------------

    def _check_allowed(self, url: str) -> None:
        if self.allowed_prefixes is None:
            return
        parts = urlsplit(url)
        prefixes = self.allowed_prefixes.get(parts.netloc, ())
        if not any(parts.path.startswith(p) for p in prefixes):
            raise PathNotAllowed(url)

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            robots_url = f"https://{host}/robots.txt"
            rules = None
            try:
                resp = self._throttled("GET", robots_url, {"User-Agent": UA}, None)
                if resp.status_code == 200:
                    rules = Protego.parse(resp.text)
            except (requests.ConnectionError, requests.Timeout):
                rules = None
            self._robots[host] = rules
        rules = self._robots[host]
        if rules is not None and not rules.can_fetch(url, UA):
            raise RobotsDisallowed(url)

    def _throttled(self, method, url, headers, payload):
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self.min_interval - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        try:
            return self.transport.request(method, url, headers=headers, json=payload,
                                          allow_redirects=False, timeout=TIMEOUT)
        finally:
            self._last_request[host] = self.clock()

    def _send(self, method, url, headers, payload=None):
        """Send with manual redirects (max 5, never into SSO) and retries on 5xx/connection errors."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            resp = self._with_retries(method, current, headers, payload)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "")
                target = urljoin(current, location)
                if urlsplit(target).netloc == SSO_HOST:
                    raise SSORedirect(f"{current} redirected to {SSO_HOST}")
                current = target
                continue
            return resp
        raise FetchError(f"too many redirects from {url}")

    def _with_retries(self, method, url, headers, payload):
        for attempt in range(len(BACKOFFS) + 1):
            try:
                resp = self._throttled(method, url, headers, payload)
                if resp.status_code < 500:
                    return resp
                error = FetchError(f"{url} returned {resp.status_code}")
            except (requests.ConnectionError, requests.Timeout) as exc:
                error = FetchError(f"{url} failed: {exc}")
            if attempt == len(BACKOFFS):
                raise error
            self.sleep(BACKOFFS[attempt])

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def _load_cache(self, url: str) -> dict | None:
        path = self._cache_path(url)
        if path and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        return None

    def _store_cache(self, url: str, headers, text: str) -> None:
        path = self._cache_path(url)
        etag, modified = headers.get("ETag"), headers.get("Last-Modified")
        if not path or not (etag or modified):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"etag": etag, "last_modified": modified, "text": text}),
                        encoding="utf-8")
