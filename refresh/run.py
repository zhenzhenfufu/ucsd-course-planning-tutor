"""Refresh entry point: python -m refresh.run [--only catalog ...]."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from refresh.catalog import (CATALOG_BASE, build_catalog_snapshot, parse_course_page,
                             parse_edition)
from refresh.http import FetchError, PoliteSession

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


def main(argv: list[str] | None = None, session: PoliteSession | None = None) -> int:
    ap = argparse.ArgumentParser(prog="refresh.run")
    ap.add_argument("--only", nargs="+", choices=SOURCES, default=None)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--report", default="refresh_report.md")  # written by a later task
    args = ap.parse_args(argv)
    data_dir = Path(args.data_dir)
    session = session or PoliteSession()
    failures = 0
    for name in args.only or ("catalog",):
        try:
            if name == "catalog":
                refresh_catalog(session, data_dir)
            else:
                print(f"{name}: not implemented yet", file=sys.stderr)
        except (ShapeError, FetchError) as e:
            failures += 1
            print(f"{name}: FAILED, keeping previous data ({e})", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
