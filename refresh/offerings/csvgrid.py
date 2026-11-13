"""Shared reader for the two published-Google-Sheet CSV sources (CSE, COGS)."""

from __future__ import annotations

import csv
import io

from ._common import ShapeError, clean, quarter_columns


def read(text: str, first_header: tuple[str, ...], academic_year: str):
    """Return (header, rows, quarter column map); rows exclude the header.

    Anything that is not a CSV whose header starts with one of first_header and has
    Fall/Winter/Spring columns for this academic year (an HTML page, another tab)
    raises ShapeError.
    """
    text = (text or "").lstrip("﻿")
    if text.lstrip()[:1] == "<":
        raise ShapeError("expected CSV, got markup")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or not rows[0] or clean(rows[0][0]) not in first_header:
        raise ShapeError(f"unexpected CSV header {rows[0][:3] if rows else None!r}")
    header = [clean(h) for h in rows[0]]
    return header, rows[1:], quarter_columns(header, academic_year)
