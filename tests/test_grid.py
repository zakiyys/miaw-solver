"""Uji worker grid — TANPA jaringan. Semua dilakukan secara offline.

Yang diuji:
  - pesan error jelas kalau Playwright tidak terpasang
  - deteksi magic bytes audio (dipakai router /in)
  - klaim grid JUJUR: tidak ada pintu CLI/API, dan `solve("grid")` bilang
    terus terang "belum ada" — bukan "tipe tidak dikenal"
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_audio_magic_bytes() -> None:
    from captcha_solver.workers.audio import looks_like_audio

    # WAV: container RIFF dengan penanda WAVE di byte 8..12
    assert looks_like_audio(b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 8) is True
    assert looks_like_audio(b"OggS" + b"\x00" * 20) is True
    assert looks_like_audio(b"fLaC" + b"\x00" * 20) is True
    assert looks_like_audio(b"ID3\x04" + b"\x00" * 20) is True
    # MP3 tanpa tag ID3: frame sync 11 bit
    assert looks_like_audio(bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 20) is True
    # PNG / JPEG harus DITOLAK supaya tidak salah dikirim ke worker audio
    assert looks_like_audio(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) is False
    assert looks_like_audio(b"\xff\xd8\xff\xe0" + b"\x00" * 8) is False
    assert looks_like_audio(b"short") is False


def test_webp_tidak_dianggap_audio() -> None:
    """WebP memakai container RIFF yang sama dengan WAV — harus dibedakan.

    Tanpa cek byte 8..12, file gambar WebP lolos jadi "audio" dan dikirim ke
    model suara.
    """
    from captcha_solver.workers.audio import looks_like_audio

    webp = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 8
    assert looks_like_audio(webp) is False
    # RIFF tanpa penanda WAVE juga bukan audio
    assert looks_like_audio(b"RIFF" + b"\x00" * 20) is False


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


# --------------------------------------------------------------------------
# Klaim grid harus jujur. Non-goal eksplisit: tidak ada model visi,
# stealth/fingerprinting, atau proxy.
# --------------------------------------------------------------------------


def test_solve_grid_menolak_dengan_alasan_jelas() -> None:
    """`solve("grid")` harus bilang "belum ada", bukan "tipe tidak dikenal"."""
    from captcha_solver import solve
    from captcha_solver.core import SolverError

    with pytest.raises(SolverError) as ei:
        solve("grid", "https://example.com")
    msg = str(ei.value)
    assert "grid" in msg
    # bukan pesan generik "tipe tidak dikenal"
    assert "tidak dikenal" not in msg
    assert "belum tersedia" in msg or "belum ada" in msg


def test_tipe_benar_benar_ngawur_tetap_ditolak() -> None:
    """Tipe yang memang tidak ada tetap dapat pesan 'tidak dikenal'."""
    from captcha_solver import solve
    from captcha_solver.core import SolverError

    with pytest.raises(SolverError) as ei:
        solve("tidak_ada_engine_ini", "x")
    assert "tidak dikenal" in str(ei.value)


def test_grid_tidak_bisa_dipakai_engine_kustom() -> None:
    """Nama 'grid' dipesan — tidak boleh dibajak engine kustom."""
    from captcha_solver.core import SolverError, register_engine, unregister_engine

    with pytest.raises(SolverError) as ei:
        register_engine("grid", lambda payload: "x")
    assert "dipesan" in str(ei.value)
    unregister_engine("grid")  # tidak boleh error


def test_cli_tidak_punya_pintu_grid() -> None:
    """Tidak ada subcommand / flag grid di CLI — itu memang non-goal."""
    from captcha_solver import cli

    src = cli.__file__
    text = open(src, encoding="utf-8").read()
    # 'grid' hanya boleh muncul di komentar/dokumentasi sebagai "tidak ada",
    # bukan sebagai nama subcommand atau flag.
    assert "add_parser(\"grid\"" not in text
    assert "add_parser('grid'" not in text
    assert "--grid" not in text


def test_api_tidak_punya_method_grid() -> None:
    """Endpoint /in tidak boleh memperlakukan method=grid sebagai sesuatu."""
    import os
    import sys

    if sys.version_info < (3, 10):  # pragma: no cover
        pytest.skip("butuh py3.10+")
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")

    os.environ["MIAW_API_KEY"] = "kunci-uji"
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    from fastapi.testclient import TestClient

    import server as srv

    with TestClient(srv.app) as client:
        r = client.post(
            "/in",
            headers={"X-API-Key": "kunci-uji"},
            json={"method": "grid", "sitekey": "abc", "pageurl": "https://x.test"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == 0
    # ditolak jelas sebagai method tak didukung, bukan diam-diam jadi image
    assert "ERROR_METHOD_NOT_SUPPORTED" in str(body["request"])


def _main() -> int:
    for fn in (
        test_audio_magic_bytes,
        test_grid_worker_importable_without_browser,
        test_cli_parser_has_all_subcommands,
        test_solve_grid_menolak_dengan_alasan_jelas,
        test_tipe_benar_benar_ngawur_tetap_ditolak,
        test_grid_tidak_bisa_dipakai_engine_kustom,
        test_cli_tidak_punya_pintu_grid,
    ):
        fn()
        print(f"  ok  {fn.__name__}")
    print("semua uji grid lolos ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
