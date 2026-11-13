"""Course ID and unit parsing for catalog text. Pure functions, no I/O."""

from __future__ import annotations

import re

# [SUBJECT[ -]] number [optional letter suffix, possibly after a space]
_ID_RE = re.compile(
    r"(?<![A-Za-z0-9])(?<!\d\.)(?:([A-Z]{2,5})[\s-]*)?0*(\d{1,3})(?:\s?([A-Z]{1,2}))?(?![A-Za-z0-9])(?!\.\d)"
)
# "/R" marker and "-B" style sequence continuations after an ID.
_SLASH_RE = re.compile(r"/[A-Z](?![A-Za-z0-9])")
_SEQ_RE = re.compile(r"-([A-Z])(?![A-Za-z0-9])")
# A bare number only continues a course list straight after a connective, and
# never when it reads as a grade, year, unit count or decimal.
_GAP_RE = re.compile(r"^[\s,/&(]*(?:(?:and|or)\s*)?$", re.I)
_NOT_COURSE_TAIL_RE = re.compile(
    r"\s*(?:units?|credits?|grades?|gpa|years?|quarters?|or\s+better)\b", re.I)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def scan_ids(text: str, subject: str | None = None) -> tuple[list[str], str | None]:
    """Return (ordered unique IDs, last subject seen) so callers can keep carrying it."""
    ids: list[str] = []
    pos = 0
    prev_end = 0
    while True:
        m = _ID_RE.search(text, pos)
        if not m:
            break
        subj, num, suffix = m.group(1), m.group(2), m.group(3) or ""
        end = m.end()
        if suffix == "OR":  # an upper-case "OR" connective, not a suffix
            suffix, end = "", m.end(2)
        if subj:
            subject = subj
        elif not (subject and _GAP_RE.match(text[prev_end:m.start()])
                  and not _NOT_COURSE_TAIL_RE.match(text, end)):
            pos = end
            continue
        found = [f"{subject} {num}{suffix}"]
        if len(suffix) == 1:
            while True:
                tail = text[end:]
                slash = _SLASH_RE.match(tail)
                seq = _SEQ_RE.match(tail[slash.end():] if slash else tail)
                if not seq:
                    if slash:
                        end += slash.end()
                    break
                end += (slash.end() if slash else 0) + seq.end()
                found.append(f"{subject} {num}{seq.group(1)}")
        else:
            slash = _SLASH_RE.match(text[end:])
            if slash:
                end += slash.end()
        for f in found:
            if f not in ids:
                ids.append(f)
        pos = prev_end = end
    return ids, subject


def expand_ids(text: str, subject: str | None = None) -> list[str]:
    return scan_ids(text, subject)[0]


def normalize_id(raw: str, subject: str | None = None) -> str | None:
    ids = expand_ids(raw, subject)
    return ids[0] if ids else None


def parse_units(text: str) -> tuple[float, float]:
    """Min and max units from the last parenthesised group; (0, 0) if none."""
    groups = re.findall(r"\(([^()]*)\)", text or "")
    nums = [float(n) for n in _NUM_RE.findall(groups[-1])] if groups else []
    return (min(nums), max(nums)) if nums else (0.0, 0.0)
