"""Parse catalog.ucsd.edu course pages into structured facts (no prose is kept)."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from bs4 import BeautifulSoup, Tag

from refresh.ids import normalize_id, parse_units
from refresh.prereq_parse import parse_prereq_clause

CATALOG_BASE = "https://catalog.ucsd.edu/courses/"

_NAME_RE = re.compile(r"^\s*([A-Z]{2,5}\s*\d+[A-Z]{0,2}(?:/[A-Z])?)\s*\.\s*(.*)$", re.S)
_TRAILING_PAREN_RE = re.compile(r"\s*\(([^()]*)\)\s*$")
_PREREQ_LABEL_RE = re.compile(r"Prerequisites?\s*:")
_EDITION_RE = re.compile(r"General Catalog\s+(\d{4}\s*[–—-]\s*\d{2,4})")
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


@dataclass
class CatalogCourse:
    id: str
    department: str
    title: str
    units: float
    units_max: float
    units_text: str
    prereq_groups: list[list[str]] = field(default_factory=list)
    concurrent_ok: bool = False
    conditions: list[str] = field(default_factory=list)
    ambiguities: list[dict] = field(default_factory=list)
    catalog_url: str = ""
    content_hash: str = ""


# Fields a stored record carries that are not part of what was parsed.
_UNHASHED = ("content_hash", "stale")


def course_hash(record: dict) -> str:
    """Hash of a course's parsed record (every field but content_hash and stale).

    Description prose, page markup and nonces are not in the record, so they
    cannot change the hash; the hash is stable across a JSON round trip, so it
    can be recomputed from data/catalog.json.
    """
    fields = {k: v for k, v in record.items() if k not in _UNHASHED}
    blob = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _is_p(el, cls: str) -> bool:
    return isinstance(el, Tag) and el.name == "p" and cls in (el.get("class") or [])


def _name_text(p: Tag) -> str:
    """Course-name text with a trailing `Tag:` strong element (and what follows) removed."""
    p = BeautifulSoup(str(p), "html.parser").p
    for strong in p.find_all("strong"):
        if _squash(strong.get_text()).startswith("Tag:"):
            for sib in list(strong.next_siblings):
                sib.extract()
            strong.extract()
            break
    return _squash(p.get_text())


def _anchors_before(name_p: Tag) -> list[str]:
    ids: list[str] = []
    for sib in name_p.previous_siblings:
        if isinstance(sib, Tag):
            if not _is_p(sib, "anchor-parent"):
                break
            ids = [a["id"] for a in sib.find_all("a", id=True)] + ids
    return ids


def parse_edition(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    p = soup.find("p", class_="course-disclaimer")
    m = _EDITION_RE.search(_squash(p.get_text())) if p else None
    return re.sub(r"\s*([–—-])\s*", r"\1", m.group(1)) if m else None


def parse_course_page(html: str, department: str, page_url: str) -> list[CatalogCourse]:
    soup = BeautifulSoup(html, "html.parser")
    anchor_counts = Counter(a["id"] for a in soup.find_all("a", id=True))
    courses: list[CatalogCourse] = []
    for name_p in soup.find_all("p", class_="course-name"):
        m = _NAME_RE.match(_name_text(name_p))
        if not m:
            continue
        subject = re.match(r"[A-Z]+", m.group(1)).group(0)
        cid = normalize_id(m.group(1), subject)
        if not cid or int(re.search(r"\d+", cid).group(0)) >= 200:
            continue
        rest = m.group(2)
        units, units_max = parse_units(rest)
        paren = _TRAILING_PAREN_RE.search(rest)
        title = _squash(rest[:paren.start()]) if paren else _squash(rest)
        units_text = _squash(paren.group(1)) if paren else ""

        body: list[str] = []
        for sib in name_p.next_siblings:
            if not isinstance(sib, Tag):
                continue
            if _is_p(sib, "course-name") or sib.name in _HEADINGS:
                break
            if _is_p(sib, "anchor-parent"):
                continue
            body.append(_squash(sib.get_text(" ")))
        text = _squash(" ".join(body))
        label = _PREREQ_LABEL_RE.search(text)
        parsed = parse_prereq_clause(text[label.end():] if label else "", subject)
        groups = [g for g in ([o for o in grp if o != cid] for grp in parsed.groups) if g]

        unique = [a for a in _anchors_before(name_p) if anchor_counts[a] == 1]
        course = CatalogCourse(
            id=cid, department=department, title=title, units=units,
            units_max=units_max, units_text=units_text,
            prereq_groups=groups, concurrent_ok=parsed.concurrent_ok,
            conditions=parsed.conditions, ambiguities=parsed.ambiguities,
            catalog_url=f"{page_url}#{unique[0]}" if unique else page_url)
        course.content_hash = course_hash(asdict(course))
        courses.append(course)
    return courses


def build_catalog_snapshot(pages: dict[str, list[CatalogCourse]], scope_ids: list[str],
                           previous: dict | None, fetched_at: str,
                           edition: str | None) -> dict:
    parsed = {c.id: c for cs in pages.values() for c in cs}
    old = (previous or {}).get("courses", {})
    courses: dict[str, dict] = {}
    for cid in scope_ids:
        if cid in parsed:
            courses[cid] = {**asdict(parsed[cid]), "stale": False}
        elif cid in old:
            courses[cid] = {**old[cid], "stale": True}
    scope = set(scope_ids)
    referenced: dict[str, dict] = {}
    for rec in courses.values():
        for group in rec["prereq_groups"]:
            for opt in group:
                if opt not in scope and not opt.startswith("<"):
                    referenced[opt] = {"defined": opt in parsed}
    return {"source": CATALOG_BASE, "fetched_at": fetched_at, "catalog_edition": edition,
            "courses": courses, "referenced": referenced}
