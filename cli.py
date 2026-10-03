#!/usr/bin/env python3
"""Shim root — biar `python cli.py ...` tetap jalan dari folder repo.

Implementasi sebenarnya ada di captcha_solver/cli.py (dipakai juga oleh
console-script `miaw-solve` setelah `pip install`).
"""
from __future__ import annotations

from captcha_solver.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
