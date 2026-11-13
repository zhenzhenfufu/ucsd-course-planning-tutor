"""Refresh entry point: python -m refresh.run [--only catalog ...]."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from refresh.catalog import (CATALOG_BASE, build_catalog_snapshot, parse_course_page,
                             parse_edition)
from refresh import classplanner
from refresh.http import FetchError, PoliteSession
from refresh.offerings import ADAPTERS

SOURCES = ("catalog", "offerings", "classplanner")


class ShapeError(Exception):
    """A source answered, but not with the structure we parse."""


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def refresh_catalog(session: PoliteSession, data_dir: Path) -> None:
    scope = json.loads((data_dir / "scope.json").read_text(encoding="utf-8"))
    scope_ids = list(scope["courses"])
    subjects = sorted({c["department"] for c in scope["courses"].values()})
    pages, edition = {}, None
    for subject in subjects:
        url = f"{CATALOG_BASE}{subject}.html"
        res = session.get(url)
        if res.status != 200 and not res.not_modified:
            raise ShapeError(f"{url} returned {res.status}")
        if "course-name" not in res.text:
            raise ShapeError(f"{url} has no p.course-name entries")
        courses = parse_course_page(res.text, subject, url)
        if not courses:
            raise ShapeError(f"{url} parsed zero courses")
        pages[subject] = courses
        edition = edition or parse_edition(res.text)
    previous = _read_json(data_dir / "catalog.json")
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap = build_catalog_snapshot(pages, scope_ids, previous, fetched_at, edition)
    _write_json(data_dir / "catalog.json", snap)
    print(f"catalog: {len(snap['courses'])} courses from {len(pages)} subjects", file=sys.stderr)


COGS_GID = "gid=866922720"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _record(out: dict, name: str, ok: bool, source_url: str | None, error: str | None) -> None:
    out.setdefault("sources", {})[name] = {"ok": ok, "fetched_at": _now(),
                                           "source_url": source_url, "error": error}


def refresh_offerings(session, data_dir: Path, out: dict) -> bool:
    """Fetch every department's tentative plan. Returns True if any department succeeded."""
    sources = json.loads((data_dir / "sources.json").read_text(encoding="utf-8"))
    any_ok = False
    departments = sorted({d for year in sources.values() for d in year})
    for dept in departments:
        key, errors, urls, new_blocks = dept.lower(), [], [], {}
        for year, depts in sorted(sources.items()):
            entry = depts.get(dept)
            if entry is None:
                continue
            url = entry["url"]
            urls.append(url)
            try:
                if dept == "COGS" and COGS_GID not in url:
                    raise ShapeError(f"COGS url lacks {COGS_GID}; refusing to fetch")
                res = session.get(url)
                if res.status != 200 and not res.not_modified:
                    raise ShapeError(f"{url} returned {res.status}")
                courses = ADAPTERS[dept].parse(res.text, year)
                new_blocks[year] = {"source_url": url, "fetched_at": _now(),
                                    "content_hash": hashlib.sha256(res.text.encode("utf-8")).hexdigest(),
                                    "status": "tentative", "courses": courses}
            except Exception as exc:  # noqa: BLE001 - any failure keeps the previous block
                errors.append(f"{year}: {_err(exc)}")
        for year, block in new_blocks.items():
            out.setdefault("tentative", {}).setdefault(year, {})[dept] = block
        _record(out, key, not errors, urls[0] if urls else None, "; ".join(errors) or None)
        any_ok = any_ok or not errors
        n = sum(len(b["courses"]) for b in new_blocks.values())
        print(f"offerings {dept}: {'ok' if not errors else 'FAILED ' + '; '.join(errors)} ({n} courses)",
              file=sys.stderr)
    return any_ok


def refresh_classplanner(session, data_dir: Path, out: dict) -> bool:
    scope = json.loads((data_dir / "scope.json").read_text(encoding="utf-8"))
    subjects = sorted({cid.split(" ", 1)[0] for cid in scope["courses"]})
    url = f"{classplanner.BASE}/api/v1/public/catalog/terms"
    try:
        terms = classplanner.fetch_terms(session)
        scheduled, problems = {}, []
        for term in terms:
            if not term["configured"]:
                continue
            code, counts, courses = term["term_code"], {}, set()
            for subj in subjects:
                try:
                    ids = classplanner.fetch_term_courses(session, code, subj)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{code} {subj}: {_err(exc)}")
                    continue
                counts[subj] = len(ids)
                courses |= ids
            if not counts:  # nothing usable for this term: keep what we had
                prev = (out.get("scheduled") or {}).get(code)
                if prev is not None:
                    scheduled[code] = prev
                continue
            scheduled[code] = {"last_full_refresh_at": term["last_full_refresh_at"],
                               "fetched_at": _now(), "subjects": counts,
                               "courses": sorted(courses)}
        out["scheduled"] = scheduled
        error = ("partial: " + "; ".join(problems)) if problems else None
        _record(out, "classplanner", True, url, error)
        print(f"classplanner: {len(scheduled)} terms" + (f" ({error})" if error else ""),
              file=sys.stderr)
        return True
    except Exception as exc:  # noqa: BLE001
        _record(out, "classplanner", False, url, _err(exc))
        print(f"classplanner: FAILED, keeping previous data ({_err(exc)})", file=sys.stderr)
        return False


def main(argv: list[str] | None = None, session: PoliteSession | None = None) -> int:
    ap = argparse.ArgumentParser(prog="refresh.run")
    ap.add_argument("--only", nargs="+", choices=SOURCES, default=None)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--report", default="refresh_report.md")  # written by a later task
    args = ap.parse_args(argv)
    data_dir = Path(args.data_dir)
    dept_session = session or PoliteSession()
    cp_session = session or PoliteSession(allowed_prefixes=classplanner.ALLOWED)
    failures = 0
    selected = args.only or ("catalog",)
    offerings_path = data_dir / "offerings.json"
    out = _read_json(offerings_path) or {}
    touched = False
    for name in selected:
        try:
            if name == "catalog":
                refresh_catalog(dept_session, data_dir)
            elif name == "offerings":
                touched = True
                failures += not refresh_offerings(dept_session, data_dir, out)
            elif name == "classplanner":
                touched = True
                failures += not refresh_classplanner(cp_session, data_dir, out)
        except Exception as e:  # noqa: BLE001 - one source must not stop the others
            failures += 1
            print(f"{name}: FAILED, keeping previous data ({_err(e)})", file=sys.stderr)
    if touched:
        out["generated_at"] = _now()
        out.setdefault("scheduled", {})
        out.setdefault("tentative", {})
        _write_json(offerings_path, out)
    return 1 if failures == len(selected) else 0


if __name__ == "__main__":
    sys.exit(main())
