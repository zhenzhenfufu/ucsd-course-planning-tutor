"""Plan generation: the model proposes, deterministic code disposes.

The model is good at reading a student's goal and picking sensible courses. It
is not reliable at holding a 68-node prerequisite DAG in its head — it will
schedule DSC 100 before DSC 80 if the wording nudges it that way.

So the split here is deliberate:

    model  -> which courses, in roughly what order, for this goal
    code   -> is that ordering actually legal

`plan_with_repair` runs the loop: generate, validate, hand the violations back
verbatim, regenerate. The model never decides whether a plan passes; it only
gets told what failed. If it cannot produce a legal plan within `max_rounds`,
the caller is told that, rather than being handed a plausible-looking plan that
does not work.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from prereq_graph import CourseGraph, build
from retrieval import context_for, get_index
from validator import Violation, repair_hint, validate

load_dotenv(Path(__file__).with_name(".env"))

MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]

PLANNER_SYSTEM = """You are a UCSD Data Science academic planner.

Return ONLY a JSON object, no prose and no markdown fence:

{"terms": [{"term": "<name>", "courses": ["DEPT NNN", ...]}, ...]}

Rules:
- Use only course codes that appear in the provided catalog rows.
- Every course must have its prerequisites satisfied in a STRICTLY EARLIER term.
- ELIGIBLE NOW lists everything legal in the FIRST term. The first term may
  contain nothing else. Later terms may add courses whose prerequisites the
  earlier terms have just satisfied.
- Each term must total 12-22 units. Most courses are 4 units.
- Do not repeat a course, and do not repeat one the student has completed.
"""


def eligible_now(cg: CourseGraph, taken: set[str]) -> list[str]:
    """Courses whose prerequisites are already satisfied by `taken`.

    Handing the model this list turns "reason over a 68-node DAG" into "choose
    from these", which is the part it is actually reliable at. The list is
    computed from the graph, so it cannot drift from what the validator will
    later enforce.
    """
    return sorted(
        cid for cid in cg.courses
        if cid not in taken and not cg.missing_groups(cid, taken)
    )


@dataclass
class PlanResult:
    plan: list[dict]
    violations: list[Violation]
    rounds: int                       # generation attempts used (1 = no repair)
    first_pass_legal: bool
    legal: bool
    error: str | None = None
    transcript: list[str] = field(default_factory=list)


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)      # fall back to the first object
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _call(client, contents: list[dict], system: str) -> str:
    last = ""
    for model in MODELS:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=model,
                    config={"system_instruction": system, "temperature": 0.2,
                            "max_output_tokens": 1200,
                            "response_mime_type": "application/json"},
                    contents=contents,
                )
                return resp.text
            except Exception as exc:
                last = str(exc)
                if ("429" in last or "RESOURCE_EXHAUSTED" in last) and attempt == 0:
                    time.sleep(10)
                    continue
                break
    raise RuntimeError(f"all models failed: {last}")


def plan_with_repair(goal: str, completed: list[str], n_terms: int = 3,
                     cg: CourseGraph | None = None, index=None,
                     max_rounds: int = 3, k: int = 12) -> PlanResult:
    from google import genai

    cg = cg or build()
    index = index or get_index(cg)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return PlanResult([], [], 0, False, False, error="GEMINI_API_KEY not set")

    client = genai.Client(api_key=key)
    done = {c.strip().upper() for c in completed}
    ctx = context_for(goal, index, k=k, extra=completed, cg=cg, hops=1)
    eligible = eligible_now(cg, done)
    prompt = (
        f"[CATALOG ROWS]\n{ctx}\n\n"
        f"[COMPLETED]: {', '.join(sorted(done)) if done else 'none'}\n"
        f"[ELIGIBLE NOW — legal in the first term]: {', '.join(eligible)}\n"
        f"[TERMS TO PLAN]: {n_terms}\n"
        f"[GOAL]: {goal}"
    )

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    transcript: list[str] = []
    first_pass_legal = False
    plan: list[dict] = []
    violations: list[Violation] = []

    for round_no in range(1, max_rounds + 1):
        try:
            raw = _call(client, contents, PLANNER_SYSTEM)
        except RuntimeError as exc:
            return PlanResult(plan, violations, round_no, first_pass_legal,
                              False, error=str(exc), transcript=transcript)
        transcript.append(raw)
        data = _extract_json(raw)
        if not data or "terms" not in data:
            violations = [Violation("MALFORMED_OUTPUT", "error", None, None,
                                    "Model did not return the required JSON shape.")]
            plan = []
        else:
            plan = data["terms"]
            violations = validate(plan, cg, completed)

        legal = not any(v.severity == "error" for v in violations)
        if round_no == 1:
            first_pass_legal = legal
        if legal:
            return PlanResult(plan, violations, round_no, first_pass_legal,
                              True, transcript=transcript)

        # Repeat the eligible set with the violations: telling the model only
        # what is wrong leaves it guessing at what is allowed instead.
        hint = (repair_hint(violations)
                + f"\n\nLegal in the first term: {', '.join(eligible)}")
        contents.append({"role": "model", "parts": [{"text": raw}]})
        contents.append({"role": "user", "parts": [{"text": hint}]})

    return PlanResult(plan, violations, max_rounds, first_pass_legal, False,
                      transcript=transcript)


TERM_SYSTEM = """You are picking ONE quarter of courses for a UCSD Data Science student.

Return ONLY: {"courses": ["DEPT NNN", ...]}

Rules:
- Choose ONLY from the ELIGIBLE list. Any other code is invalid.
- Total 12-22 units. Most courses are 4 units, so 3-5 courses.
- Prefer courses that move the student toward the stated goal, and that unlock
  the most later courses.
"""


def plan_iterative(goal: str, completed: list[str], n_terms: int = 3,
                   cg: CourseGraph | None = None, index=None,
                   max_rounds: int = 2, k: int = 12) -> PlanResult:
    """Plan one term at a time against a freshly computed eligible set.

    Planning all terms at once asks the model to satisfy a global constraint:
    every course must sit after everything it depends on, across the whole
    plan. It is not reliable at that. Planning term by term removes the
    problem instead of restating it — at each step the eligible set is
    recomputed from the DAG, so a course the student cannot legally take yet
    is never offered, and the term is validated before the next one starts.
    """
    from google import genai

    cg = cg or build()
    index = index or get_index(cg)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return PlanResult([], [], 0, False, False, error="GEMINI_API_KEY not set")

    client = genai.Client(api_key=key)
    taken = {c.strip().upper() for c in completed}
    terms: list[dict] = []
    transcript: list[str] = []
    rounds_used = 0
    per_term_first_pass: list[bool] = []

    for t in range(1, n_terms + 1):
        eligible = eligible_now(cg, taken)
        if not eligible:
            break
        rows = "\n".join(
            f"- {index.docs[c]}" for c in eligible if c in index.docs
        )
        base = (
            f"[GOAL]: {goal}\n"
            f"[COMPLETED SO FAR]: {', '.join(sorted(taken)) or 'none'}\n"
            f"[TERM]: {t} of {n_terms}\n"
            f"[ELIGIBLE]: {', '.join(eligible)}\n\n"
            f"[DETAILS]\n{rows}"
        )
        contents = [{"role": "user", "parts": [{"text": base}]}]
        chosen: list[str] = []

        for attempt in range(1, max_rounds + 1):
            rounds_used += 1
            try:
                raw = _call(client, contents, TERM_SYSTEM)
            except RuntimeError as exc:
                return PlanResult(terms, validate(terms, cg, completed),
                                  rounds_used, False, False, error=str(exc),
                                  transcript=transcript)
            transcript.append(raw)
            data = _extract_json(raw) or {}
            chosen = [str(c).strip().upper() for c in data.get("courses", [])]
            trial = terms + [{"term": f"Term {t}", "courses": chosen}]
            errs = [v for v in validate(trial, cg, completed) if v.severity == "error"]
            if attempt == 1:
                per_term_first_pass.append(not errs)
            if not errs:
                break
            contents.append({"role": "model", "parts": [{"text": raw}]})
            contents.append({"role": "user", "parts": [{"text":
                repair_hint([v for v in validate(trial, cg, completed)])
                + f"\n\nChoose only from: {', '.join(eligible)}"}]})

        terms.append({"term": f"Term {t}", "courses": chosen})
        taken |= set(chosen)

    violations = validate(terms, cg, completed)
    legal = not any(v.severity == "error" for v in violations)
    return PlanResult(terms, violations, rounds_used,
                      all(per_term_first_pass) if per_term_first_pass else False,
                      legal, transcript=transcript)
