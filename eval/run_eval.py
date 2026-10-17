"""Measure how often the model's first plan is legal, and whether the
validator repair loop closes the gap.

The number that matters is the pair:

    first-pass legality   how often the model alone gets it right
    post-repair legality  how often the system as a whole does

Reporting only the second would hide the fact that the model needs the checker.
Reporting only the first would understate what the product does.

Usage:
    python eval/run_eval.py                # full run against the API
    python eval/run_eval.py --limit 3      # short run
    python eval/run_eval.py --offline      # no API: validator self-test only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prereq_graph import build            # noqa: E402
from retrieval import get_index           # noqa: E402
from validator import validate            # noqa: E402

CASES = Path(__file__).with_name("cases.json")
RESULTS = Path(__file__).with_name("results.json")

# Hand-built plans with a known verdict, used to check the checker itself.
VALIDATOR_FIXTURES = [
    ("legal-simple", True, [], [
        {"term": "F", "courses": ["DSC 10", "MATH 20A", "CSE 11"]},
        {"term": "W", "courses": ["DSC 20", "MATH 20B", "MATH 18"]}]),
    ("prereq-inverted", False, [], [
        {"term": "F", "courses": ["DSC 100", "MATH 20A", "CSE 11"]},
        {"term": "W", "courses": ["DSC 80", "MATH 20B", "MATH 18"]}]),
    ("same-term-prereq", False, [], [
        {"term": "F", "courses": ["DSC 10", "DSC 20", "DSC 30"]}]),
    ("concurrent-allowed", True, ["MATH 20A"], [
        {"term": "F", "courses": ["PHYS 2A", "MATH 20B", "DSC 10"]}]),
    ("substitute-accepted", True, ["DSC 10", "CSE 15L", "DSC 40B", "MATH 180A"], [
        {"term": "F", "courses": ["CSE 158", "MATH 20A", "CHEM 11"]}]),
    ("under-full-time", False, [], [
        {"term": "F", "courses": ["DSC 10", "MATH 20A"]}]),
    ("over-cap", False, [], [
        {"term": "F", "courses": ["DSC 10", "MATH 20A", "CSE 11", "MATH 18",
                                  "CHEM 11", "BILD 1"]}]),
    ("duplicate", False, [], [
        {"term": "F", "courses": ["DSC 10", "MATH 20A", "CSE 11"]},
        {"term": "W", "courses": ["DSC 10", "MATH 20B", "MATH 18"]}]),
    ("unknown-course", False, [], [
        {"term": "F", "courses": ["DSC 999", "MATH 20A", "CSE 11"]}]),
]


def run_validator_fixtures(cg) -> tuple[int, int, list[str]]:
    passed, failures = 0, []
    for name, expect_legal, completed, plan in VALIDATOR_FIXTURES:
        errors = [v for v in validate(plan, cg, completed) if v.severity == "error"]
        got_legal = not errors
        if got_legal == expect_legal:
            passed += 1
        else:
            failures.append(
                f"{name}: expected {'legal' if expect_legal else 'illegal'}, "
                f"got {'legal' if got_legal else 'illegal'}"
                + (f" ({errors[0].code})" if errors else ""))
    return passed, len(VALIDATOR_FIXTURES), failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--arm", choices=["joint", "iterative", "both"], default="both")
    args = ap.parse_args()

    cg = build()

    print("=" * 66)
    print("VALIDATOR SELF-TEST  (does the checker get known cases right?)")
    print("=" * 66)
    passed, total, failures = run_validator_fixtures(cg)
    for f in failures:
        print(f"  FAIL  {f}")
    print(f"  {passed}/{total} fixtures correct")
    if args.offline:
        return 0 if passed == total else 1

    from planner import plan_iterative, plan_with_repair

    index = get_index(cg)
    cases = json.loads(CASES.read_text())
    if args.limit:
        cases = cases[: args.limit]

    print()
    print("=" * 66)
    print(f"PLANNING EVAL  ({len(cases)} cases, retrieval={index.name}, "
          f"max_rounds={args.max_rounds})")
    print("=" * 66)

    def run_arm(label, fn, rounds):
        rows, codes = [], Counter()
        for i, case in enumerate(cases, 1):
            t0 = time.time()
            res = fn(case["goal"], case.get("completed", []), case.get("terms", 3),
                     cg=cg, index=index, max_rounds=rounds)
            dt = time.time() - t0
            for v in res.violations:
                if v.severity == "error":
                    codes[v.code] += 1
            rows.append({"id": case["id"], "first_pass_legal": res.first_pass_legal,
                         "legal": res.legal, "rounds": res.rounds,
                         "error": res.error, "seconds": round(dt, 1)})
            print(f"  [{i:2}/{len(cases)}] {'PASS' if res.legal else 'FAIL'}  "
                  f"{'1st' if res.first_pass_legal else str(res.rounds) + 'r':4} "
                  f"{dt:5.1f}s  {case['id']}" + (f"  ({res.error})" if res.error else ""))
        n = len(rows)
        fp = sum(r["first_pass_legal"] for r in rows)
        ok = sum(r["legal"] for r in rows)
        mean_rounds = sum(r["rounds"] for r in rows) / n if n else 0
        print()
        print("-" * 66)
        print(f"  {label}")
        print(f"    first-pass legal (model alone) : {fp}/{n}  = {100*fp/n:.0f}%")
        print(f"    after repair loop              : {ok}/{n}  = {100*ok/n:.0f}%")
        print(f"    mean generation calls          : {mean_rounds:.2f}")
        if codes:
            print("    violations caught by checker   : "
                  + ", ".join(f"{c}x {code}" for code, c in codes.most_common()))
        print("-" * 66)
        return {"label": label, "cases": n, "first_pass_legal": fp,
                "post_repair_legal": ok,
                "first_pass_rate": round(fp / n, 4) if n else 0,
                "post_repair_rate": round(ok / n, 4) if n else 0,
                "mean_rounds": round(mean_rounds, 3),
                "violation_codes": dict(codes), "rows": rows}

    arms = []
    if args.arm in ("joint", "both"):
        print("\n### ARM A — plan all terms at once, repair on failure")
        arms.append(run_arm("A: joint planning + validator repair",
                            plan_with_repair, args.max_rounds))
    if args.arm in ("iterative", "both"):
        print("\n### ARM B — plan term by term against a recomputed eligible set")
        arms.append(run_arm("B: per-term planning + validator repair",
                            plan_iterative, 2))

    RESULTS.write_text(json.dumps({
        "validator_fixtures": f"{passed}/{total}",
        "retrieval_backend": index.name,
        "arms": arms,
    }, indent=2))
    print(f"  written: {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
