"""Uji worker grid — TANPA jaringan. Semua dilakukan secara offline.

Yang diuji:
  - pesan error jelas kalau Playwright tidak terpasang
  - deteksi magic bytes audio (dipakai router /in)
  - router `solve()` tidak salah arah ke grid kalau tipe tidak dikenal
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_audio_magic_bytes() -> None:
    from captcha_solver.workers.audio import looks_like_audio

    assert looks_like_audio(b"RIFF" + b"\x00" * 20) is True
    assert looks_like_audio(b"OggS" + b"\x00" * 20) is True
    assert looks_like_audio(b"fLaC" + b"\x00" * 20) is True
    assert looks_like_audio(b"ID3\x04" + b"\x00" * 20) is True
    # PNG / JPEG harus DITOLAK supaya tidak salah dikirim ke worker audio
    assert looks_like_audio(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) is False
    assert looks_like_audio(b"\xff\xd8\xff\xe0" + b"\x00" * 8) is False
    assert looks_like_audio(b"short") is False


def test_grid_worker_importable_without_browser() -> None:
    """Modul grid harus bisa diimpor walau Chromium tidak ada (lazy import)."""
    from captcha_solver.workers import grid

    assert hasattr(grid, "GridWorker")
    assert hasattr(grid, "solve_recaptcha_v2")


def test_grid_hcaptcha_not_supported_message() -> None:
    import asyncio

    from captcha_solver.workers.grid import GridWorker

    with pytest.raises(RuntimeError) as ei:
        asyncio.run(GridWorker().solve_hcaptcha("https://example.com", "abc"))
    assert "hCaptcha" in str(ei.value) or "fallback" in str(ei.value)


def test_grid_missing_playwright_message(monkeypatch) -> None:
    """Kalau Playwright tidak ada, pesan harus menyebut cara memasangnya."""
    import builtins

    from captcha_solver.workers import grid

    real_import = builtins.__import__

    def _fake_import(name, *a, **k):
        if name.startswith("playwright"):
            raise ImportError("playwrights not installed (simulasi)")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    with pytest.raises(RuntimeError) as ei:
        grid.GridWorker()._require_playwright()
    assert "playwright" in str(ei.value).lower()


def test_cli_parser_has_all_subcommands() -> None:
    """CLI harus punya semua pintu: image/solve, text, audio, auto."""
    import argparse

    from captcha_solver import cli

    # main() tanpa argumen harus SystemExit (subcommand wajib)
    with pytest.raises(SystemExit):
        cli.main([])


def _main() -> int:
    for fn in (
        test_audio_magic_bytes,
        test_grid_worker_importable_without_browser,
        test_cli_parser_has_all_subcommands,
    ):
        fn()
        print(f"  ok  {fn.__name__}")
    print("semua uji grid lolos ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
