#!/usr/bin/env python3
"""Plugging your own solver into the core.

The core dispatches by *payload shape*, so as long as your callable takes the
payload and returns a string (or raises ``SolverError``), it drops straight in.

Run from the repo root:

    python examples/custom_engine.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from captcha_solver import SolverError, solve_text  # noqa: E402
from captcha_solver.core import register_engine  # noqa: E402


# --- 1. a trivial custom engine -------------------------------------------

def roman_engine(question: str) -> str:
    """Answers questions of the form 'roman: XIV' -> '14'."""
    text = question.strip().lower()
    if not text.startswith("roman:"):
        raise SolverError("not a roman question")
    numerals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    prev = 0
    for ch in reversed(text.split(":", 1)[1].strip()):
        if ch not in numerals:
            raise SolverError(f"bad numeral: {ch!r}")
        val = numerals[ch]
        total += -val if val < prev else val
        prev = max(prev, val)
    return str(total)


# --- 2. register it under a name ------------------------------------------

register_engine("roman", roman_engine)


# --- 3. compose an engine with a fallback chain ---------------------------

def chain(*engines):
    """Try each engine in order; return the first answer that works."""
    def _run(question):
        errors = []
        for e in engines:
            try:
                return e(question)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{e.__name__}: {exc}")
        raise SolverError("all engines failed: " + "; ".join(errors))
    return _run


if __name__ == "__main__":
    print("roman     :", roman_engine("roman: XIV"))          # -> 14
    print("roman     :", roman_engine("roman: MCMXCIV"))      # -> 1994

    # roman first, fall back to the built-in text engine
    hybrid = chain(roman_engine, solve_text)
    print("hybrid    :", hybrid("roman: IX"))                 # -> 9
    print("hybrid    :", hybrid("7 x 6"))                     # -> 42 (fallback)
