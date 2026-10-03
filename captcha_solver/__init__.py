"""Miaw Solver — self-hosted CAPTCHA solver, CPU-first.

Public API:
    from captcha_solver import solve_image, solve_text, solve_audio, solve
    from captcha_solver import register_engine          # pasang engine sendiri
"""
from .core import (
    SolverError,
    engines,
    register_engine,
    solve,
    solve_audio,
    solve_image,
    solve_text,
    unregister_engine,
)

__version__ = "1.0.1"
__all__ = [
    "solve_image",
    "solve_text",
    "solve_audio",
    "solve",
    "SolverError",
    "register_engine",
    "unregister_engine",
    "engines",
    "__version__",
]
