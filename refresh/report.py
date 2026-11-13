"""Readable refresh report (Markdown, used as the PR body)."""

from __future__ import annotations

from datetime import date


def _opts(groups):
    return [(i, set(g)) for i, g in enumerate(groups)]


def _course_lines(cid: str, c: dict, old: dict | None) -> list[str]:
    url = c.get("catalog_url", "")
    if old is None:
        return [f"- **{cid}**: new course, {c.get('title', '')} ({c.get('units_max', '?')} units)"]
    out = []
    if old.get("title") != c.get("title"):
        out.append(f"title: {old.get('title')!r} -> {c.get('title')!r}")
    if (old.get("units"), old.get("units_max")) != (c.get("units"), c.get("units_max")):
        out.append(f"units: {old.get('units')}-{old.get('units_max')} -> "
                   f"{c.get('units')}-{c.get('units_max')}")
    og, ng = old.get("prereq_groups", []), c.get("prereq_groups", [])
    for i in range(max(len(og), len(ng))):
        a = set(og[i]) if i < len(og) else None
        b = set(ng[i]) if i < len(ng) else None
        if a == b:
            continue
        if a is None:
            out.append(f"prerequisite group {i + 1} added: {' or '.join(sorted(b))}")
        elif b is None:
            out.append(f"prerequisite group {i + 1} removed: {' or '.join(sorted(a))}")
        else:
            if b - a:
                out.append(f"prerequisite group {i + 1} gains {', '.join(sorted(b - a))}")
            if a - b:
                out.append(f"prerequisite group {i + 1} loses {', '.join(sorted(a - b))}")
    oc, nc = set(old.get("conditions", [])), set(c.get("conditions", []))
    for x in sorted(nc - oc):
        out.append(f"condition added: {x}")
    for x in sorted(oc - nc):
        out.append(f"condition removed: {x}")
    oa = {a["fragment"] for a in old.get("ambiguities", [])}
    for a in c.get("ambiguities", []):
        if a["fragment"] not in oa:
            out.append(f"new ambiguity ({a['kind']}): \"{a['fragment']}\" ([catalog]({url}))")
    if bool(old.get("stale")) != bool(c.get("stale")):
        out.append("now marked stale (gone from the catalog)" if c.get("stale")
                   else "no longer stale")
    if not out:
        return []
    return [f"- **{cid}**: {x}" for x in out]


def diff_catalog(old: dict, new: dict) -> list[str]:
    oc, nc = (old or {}).get("courses", {}), (new or {}).get("courses", {})
    lines = []
    for cid in sorted(nc):
        lines += _course_lines(cid, nc[cid], oc.get(cid))
    for cid in sorted(set(oc) - set(nc)):
        lines.append(f"- **{cid}**: removed from the catalog snapshot")
    return lines


def _quarter_diff(cid: str, label: str, a: list, b: list) -> str | None:
    gained, lost = sorted(set(b) - set(a)), sorted(set(a) - set(b))
    if not gained and not lost:
        return None
    bits = ([f"gained {', '.join(gained)}"] if gained else []) + \
           ([f"lost {', '.join(lost)}"] if lost else [])
    return f"- **{cid}** ({label}): " + "; ".join(bits)


def diff_offerings(old: dict, new: dict) -> list[str]:
    old, new = old or {}, new or {}
    lines = []
    os_, ns = old.get("scheduled", {}), new.get("scheduled", {})
    for t in sorted(set(ns) - set(os_)):
        lines.append(f"- Term {t}: now published by the Class Planner "
                     f"({len(ns[t].get('courses', []))} courses)")
    for t in sorted(set(os_) - set(ns)):
        lines.append(f"- Term {t}: no longer listed by the Class Planner")
    for t in sorted(set(os_) & set(ns)):
        a, b = set(os_[t].get("courses", [])), set(ns[t].get("courses", []))
        for cid in sorted(b - a):
            lines.append(f"- **{cid}** ({t}): now scheduled")
        for cid in sorted(a - b):
            lines.append(f"- **{cid}** ({t}): no longer scheduled")
    ot, nt = old.get("tentative", {}), new.get("tentative", {})
    for ay in sorted(set(ot) | set(nt)):
        for dept in sorted(set(ot.get(ay, {})) | set(nt.get(ay, {}))):
            a = ot.get(ay, {}).get(dept, {}).get("courses", {})
            b = nt.get(ay, {}).get(dept, {}).get("courses", {})
            if dept not in ot.get(ay, {}):
                lines.append(f"- {dept} {ay}: plan appeared ({len(b)} courses)")
                continue
            if dept not in nt.get(ay, {}):
                lines.append(f"- {dept} {ay}: plan vanished")
                continue
            for cid in sorted(set(a) | set(b)):
                if cid not in a:
                    lines.append(f"- **{cid}** ({ay}): added, {', '.join(b[cid])}")
                elif cid not in b:
                    lines.append(f"- **{cid}** ({ay}): dropped from the {dept} plan")
                else:
                    s = _quarter_diff(cid, ay, a[cid], b[cid])
                    if s:
                        lines.append(s)
    return lines


def _next_year(today: date) -> str:
    start = today.year if today.month >= 9 else today.year - 1
    return f"{start + 1}-{str(start + 2)[2:]}"


def render_report(catalog_lines: list[str], offering_lines: list[str], sources: dict,
                  tests_summary: str | None, today: date | None = None,
                  sources_plan: dict | None = None) -> str:
    today = today or date.today()
    out = ["# Data refresh report", "", "## Sources", ""]
    if sources:
        out += ["| Source | Status | Detail |", "|---|---|---|"]
        order = sorted(sources, key=lambda n: (sources[n].get("ok", False), n))
        for n in order:
            s = sources[n]
            status = "ok" if s.get("ok") else "FAILED"
            detail = s.get("error") or s.get("source_url") or ""
            if s.get("ok") and s.get("error"):
                status = "partial"
            out.append(f"| {n} | {status} | {detail.replace('|', '/')} |")
    else:
        out.append("No sources were refreshed.")
    if 3 <= today.month <= 6 and sources_plan is not None:
        ny = _next_year(today)
        have = set(sources_plan.get(ny, {}))
        every = sorted({d for y in sources_plan.values() for d in y})
        missing = [d for d in every if d not in have]
        if missing:
            out += ["", f"No plan found for next academic year ({ny}): {', '.join(missing)}"]
    out += ["", "## Catalog changes", ""] + (catalog_lines or ["No changes."])
    out += ["", "## Offering changes", ""] + (offering_lines or ["No changes."])
    out += ["", "## Tests", "", tests_summary or "Not run."]
    return "\n".join(out) + "\n"
