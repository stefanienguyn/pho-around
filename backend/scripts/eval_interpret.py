"""Measure how well a model reads real requests. Run on demand, never in CI.

The pytest gate tests the machinery around the model with the model replaced.
This tests the model itself, which means real calls, real quota, and answers
that vary between runs — three good reasons to keep it out of the gate.

It exists to settle one question with evidence instead of intuition: a Lite
model has 25x the free daily allowance, but is it still right about
**negation**? "no coffee" becoming "at least 1 coffee" passes every validator
we have and is exactly backwards, so that is the case the set is built around.

Usage (from app/backend)::

    PYTHONPATH=. .venv/bin/python scripts/eval_interpret.py            # default model
    PYTHONPATH=. .venv/bin/python scripts/eval_interpret.py --model gemini-3.7-flash
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# Each case: what a person types, and the constraints that must come back.
# Compared as an unordered set of (type, category-or-id, count) — the order the
# model lists them in carries no meaning.
#
# Vietnamese is not a bonus here. The UI chrome is English but the places are
# Vietnamese and so are the users; a model that only reads English is no use.
CASES: list[tuple[str, set[tuple]]] = [
    # --- negation: the case this whole set exists for ---
    ("no shopping please", {("exclude_category", "shopping", None)}),
    ("không cà phê", {("exclude_category", "coffee", None)}),
    ("I don't want dessert", {("exclude_category", "dessert", None)}),
    ("không đi mua sắm nhé", {("exclude_category", "shopping", None)}),
    # --- the same word, opposite polarity: the pair that catches a lazy reader ---
    ("I want coffee", {("min_category", "coffee", 1)}),
    ("no coffee", {("exclude_category", "coffee", None)}),
    # --- counts ---
    ("at least two coffee stops", {("min_category", "coffee", 2)}),
    ("tối đa 3 chỗ thôi", {("max_stops", None, 3)}),
    ("no more than one dessert", {("max_category", "dessert", 1)}),
    # --- combinations ---
    (
        "cà phê, không shopping, tối đa 3 chỗ",
        {
            ("min_category", "coffee", 1),
            ("exclude_category", "shopping", None),
            ("max_stops", None, 3),
        },
    ),
    # --- nothing expressible: must not invent constraints ---
    ("hello", set()),
    ("somewhere nice for the afternoon", set()),
]


def _key(constraint: dict) -> tuple:
    """Reduce a constraint to what we actually assert on."""
    return (
        constraint.get("type"),
        constraint.get("category"),
        constraint.get("count"),
    )


def main() -> int:
    """Run every case and report a pass rate. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="override GEMINI_MODEL for this run")
    args = parser.parse_args()
    if args.model:
        os.environ["GEMINI_MODEL"] = args.model

    import api
    import interpret
    from pho_engine.models import CATEGORIES

    # Cost is quota, not money, and quota is the scarce thing — so say what
    # this will spend before spending it.
    print(f"model  : {interpret.MODEL}")
    print(f"cases  : {len(CASES)}  (= {len(CASES)} requests of the daily allowance)")
    if not interpret.is_configured():
        print("\nNo GEMINI_API_KEY — nothing to run.")
        return 1
    print()

    passed = 0
    for message, expected in CASES:
        try:
            raw, _reply = interpret.interpret(
                message, places=api._PLACES, categories=list(CATEGORIES)
            )
        except interpret.InterpretFailed as exc:
            print(f"  ERROR  {message!r}: {exc}")
            continue

        valid, dropped = api.validate_constraints(raw)
        got = {_key(c.model_dump()) for c in valid}
        ok = got == expected
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {message}")
        if not ok:
            print(f"        expected {sorted(expected)}")
            print(f"        got      {sorted(got)}")
        if dropped:
            print(f"        ({dropped} dropped as unusable)")

    print(f"\n{passed}/{len(CASES)} passed")
    # The negation cases are the ones that matter; a miss there is a wrong
    # plan, not a slightly worse one.
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
