"""Uji extension point: register_engine / unregister_engine / solve()."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from captcha_solver import SolverError, solve  # noqa: E402
from captcha_solver.core import (  # noqa: E402
    engines,
    register_engine,
    unregister_engine,
)


@pytest.fixture(autouse=True)
def _cleanup():
    """Jangan biarkan engine uji bocor ke test lain."""
    yield
    for name in ("roman", "boom", "notstr", "temp"):
        unregister_engine(name)


def test_custom_engine_is_reachable_via_solve() -> None:
    register_engine("roman", lambda q: "14")
    assert "roman" in engines()
    assert solve("roman", "XIV") == "14"


def test_name_is_normalised() -> None:
    register_engine("  RoMan  ", lambda q: "9")
    assert solve("roman", "IX") == "9"


def test_duplicate_registration_rejected_unless_override() -> None:
    register_engine("roman", lambda q: "1")
    with pytest.raises(SolverError, match="sudah terdaftar"):
        register_engine("roman", lambda q: "2")
    register_engine("roman", lambda q: "2", override=True)
    assert solve("roman", "x") == "2"


def test_builtin_engines_cannot_be_overridden() -> None:
    """Mencegah registrasi diam-diam merusak perilaku bawaan."""
    for name in ("image", "text", "audio", "grid"):
        with pytest.raises(SolverError, match="bawaan"):
            register_engine(name, lambda q: "hijack")


def test_invalid_name_rejected() -> None:
    for bad in ("", "   ", "has space", "semi;colon", "dot.name"):
        with pytest.raises(SolverError, match="tidak valid"):
            register_engine(bad, lambda q: "x")


def test_non_callable_rejected() -> None:
    with pytest.raises(SolverError, match="callable"):
        register_engine("roman", "not-a-function")  # type: ignore[arg-type]


def test_engine_exception_wrapped_as_solvererror() -> None:
    def boom(_):
        raise ValueError("inner detail")

    register_engine("boom", boom)
    with pytest.raises(SolverError, match="boom"):
        solve("boom", "x")


def test_engine_must_return_str() -> None:
    register_engine("notstr", lambda q: 42)  # type: ignore[arg-type]
    with pytest.raises(SolverError, match="bukan str"):
        solve("notstr", "x")


def test_solver_error_from_engine_propagates_unwrapped() -> None:
    def clean(_):
        raise SolverError("pesan asli")

    register_engine("temp", clean)
    with pytest.raises(SolverError, match="pesan asli"):
        solve("temp", "x")


def test_unregister_removes_engine() -> None:
    register_engine("roman", lambda q: "1")
    unregister_engine("roman")
    assert "roman" not in engines()
    with pytest.raises(SolverError, match="tidak dikenal"):
        solve("roman", "x")


def test_unknown_kind_still_errors() -> None:
    with pytest.raises(SolverError, match="tidak dikenal"):
        solve("nope", "x")
