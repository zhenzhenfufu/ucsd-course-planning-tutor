"""Read which courses are offered in a term from the Class Planner public API.

Only /api/v1/public/* is touched. Only course IDs are kept: no sections,
seats, instructors or meeting times.
"""

from __future__ import annotations

import json

from .http import PoliteSession
from .ids import normalize_id

BASE = "https://classplanner.apps.ucsd.edu"
ALLOWED = {"classplanner.apps.ucsd.edu": ("/api/v1/public/",)}
PAGE_SIZE = 48
TERM_KEYS = ("term_code", "last_full_refresh_at", "configured")


class SchemaError(Exception):
    pass


def fetch_terms(session: PoliteSession) -> list[dict]:
    res = session.get(f"{BASE}/api/v1/public/catalog/terms")
    if res.status != 200:
        raise SchemaError(f"terms returned HTTP {res.status}")
    try:
        terms = json.loads(res.text)["terms"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SchemaError(f"unexpected terms response: {exc!r}") from exc
    if not isinstance(terms, list):
        raise SchemaError("terms is not a list")
    for t in terms:
        if not isinstance(t, dict) or any(k not in t for k in TERM_KEYS):
            raise SchemaError(f"term missing one of {TERM_KEYS}")
    return terms


def fetch_term_courses(session: PoliteSession, term_code: str, subject: str) -> set[str]:
    url = f"{BASE}/api/v1/public/catalog/courses/search"
    ids: set[str] = set()
    offset = 0
    while True:
        page = session.post_json(url, {"term_code": term_code, "subject_code": [subject],
                                       "limit": PAGE_SIZE, "offset": offset})
        if not isinstance(page, dict) or not isinstance(page.get("total"), int) \
                or not isinstance(page.get("courses"), list):
            raise SchemaError("search response lacks total/courses")
        courses = page["courses"]
        for c in courses:
            raw = c.get("module_code") if isinstance(c, dict) else None
            cid = normalize_id(raw, subject) if isinstance(raw, str) else None
            if cid is None:
                raise SchemaError(f"unparseable course code {raw!r}")
            ids.add(cid)
        offset += len(courses)
        if not courses or offset >= page["total"]:
            return ids
