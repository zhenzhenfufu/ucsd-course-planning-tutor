"""Parse a catalog prerequisite clause into AND-of-OR groups. Pure functions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from refresh.ids import scan_ids

# Requirements the catalog phrases in prose, and the courses it names as
# acceptable ways to satisfy them.
ABSTRACT_SATISFIERS: dict[str, list[str]] = {
    "<probability>": ["MATH 180A", "MATH 183", "CSE 103", "ECE 109"],
    "<programming>": ["DSC 20", "DSC 30", "CSE 11", "CSE 12", "DSC 10"],
    "<upper-division standing>": [],   # standing, not a course
    "<instructor approval>": [],       # administrative
    "<qualifying elective>": [],       # depends on the student's track
    "<high school chemistry>": [],     # external
}

ABSTRACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"probability(\s+course)?", re.I), "<probability>"),
    (re.compile(r"programming(\s+(course|background))?", re.I), "<programming>"),
    (re.compile(r"upper-division standing", re.I), "<upper-division standing>"),
    (re.compile(r"instructor approval", re.I), "<instructor approval>"),
    (re.compile(r"qualifying elective", re.I), "<qualifying elective>"),
    (re.compile(r"high school chemistry", re.I), "<high school chemistry>"),
]

# Sentences that restrict who may enrol rather than naming courses.
CONDITION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"upper[- ]division standing", re.I), "upper-division standing"),
    (re.compile(r"restricted to .*\bmajors?\b|within the .*\bmajors?\b|\bmajors? only\b",
                re.I), "major restriction"),
    (re.compile(r"consent of (?:the )?instructor|instructor(?:'s)? (?:consent|permission)",
                re.I), "instructor consent"),
    (re.compile(r"(?:approval|consent) of (?:the )?department|department(?:al)? "
                r"(?:approval|consent)", re.I), "department approval"),
    (re.compile(r"\bGPA\b|grade point average", re.I), "gpa"),
    (re.compile(r"\d+\s+units\b|units completed", re.I), "units completed"),
]

_CONCURRENT_RE = re.compile(r"[,;]?\s*(?:which\s+)?(?:(?:may|can)\s+)?(?:be\s+)?(?:taken\s+)?"
                            r"concurrent(?:ly)?\b[^.;]*", re.I)
_NONE_RE = re.compile(r"^(?:none|no prerequisites?)\W*$", re.I)
_PREFIX_RE = re.compile(r"^\s*(?:required\s+)?prerequisites?\s*:\s*", re.I)
_AND_RE = re.compile(r",\s*and\s+|,\s*|\s+and\s+", re.I)
_OR_RE = re.compile(r"\s+or\s+", re.I)
_MAX_FRAGMENT_WORDS = 10


@dataclass
class ParsedPrereq:
    groups: list[list[str]] = field(default_factory=list)
    concurrent_ok: bool = False
    conditions: list[str] = field(default_factory=list)
    ambiguities: list[dict] = field(default_factory=list)


def _split_depth0(text: str, sep: re.Pattern) -> list[str]:
    """Split on `sep` only where parenthesis depth is 0."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            m = sep.match(text, i)
            if m and m.end() > i:
                parts.append(text[start:i])
                start = i = m.end()
                continue
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _strip_outer_parens(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for i, ch in enumerate(text):
            depth += (ch == "(") - (ch == ")")
            if depth == 0 and i < len(text) - 1:
                return text  # the first paren closes early: not a wrapper
        text = text[1:-1].strip()
    return text


def _fragment(text: str) -> str:
    return " ".join(text.split()[:_MAX_FRAGMENT_WORDS])


def parse_prereq_clause(text: str, subject: str) -> ParsedPrereq:
    out = ParsedPrereq()
    requirement: list[str] = []
    for sent in re.split(r"(?<=[.;])\s+", text or ""):
        sent = _PREFIX_RE.sub("", sent).strip()
        if not sent or _NONE_RE.match(sent.rstrip(".; ")):
            continue
        hits = [tok for pat, tok in CONDITION_PATTERNS if pat.search(sent)]
        if hits:
            out.conditions.extend(t for t in hits if t not in out.conditions)
            continue
        if _CONCURRENT_RE.search(sent):
            out.concurrent_ok = True
            sent = _CONCURRENT_RE.sub("", sent)
        sent = sent.strip(" .;,")
        if sent:
            requirement.append(sent)

    carried = subject
    for sent in requirement:
        for part in _split_depth0(sent, _AND_RE):
            options: list[str] = []
            for opt in _split_depth0(_strip_outer_parens(part), _OR_RE):
                opt = _strip_outer_parens(opt)
                ids, carried = scan_ids(opt, carried)
                token = None if ids else next(
                    (t for pat, t in ABSTRACT_PATTERNS if pat.search(opt)), None)
                if ids:
                    options.extend(i for i in ids if i not in options)
                    if re.search(r"\([^)]*\sand\s", opt, re.I):
                        out.ambiguities.append(
                            {"kind": "nested-and", "fragment": _fragment(opt)})
                elif token:
                    if token not in options:
                        options.append(token)
                else:
                    out.ambiguities.append(
                        {"kind": "unresolved", "fragment": _fragment(opt)})
            if options:
                out.groups.append(options)
    return out
