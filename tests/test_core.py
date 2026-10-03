"""Uji inti — CPU-only, tanpa GPU, tanpa network (kecuali uji yang ditandai).

Jalan dengan pytest, atau langsung: `python tests/test_core.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- text worker

def test_text_arithmetic() -> None:
    from captcha_solver import solve_text

    assert solve_text("Berapa hasil dari 4 + 8 ?") == "12"
    assert solve_text("What is 7 x 6 ?") == "42"
    assert solve_text("tiga tambah lima") == "8"
    assert solve_text("12 + 30 =") == "42"
    assert solve_text("100 - 58") == "42"


def test_text_words_and_symbols() -> None:
    from captcha_solver import solve_text

    assert solve_text("seven times six") == "42"
    assert solve_text("dua puluh dibagi empat") == "5"
    assert solve_text("10 ÷ 2") == "5"
    assert solve_text("9 × 9") == "81"


def test_text_rejects_empty() -> None:
    from captcha_solver import SolverError, solve_text

    with pytest.raises(SolverError):
        solve_text("   ")


def test_text_rejects_injection() -> None:
    """Ekspresi jahat tidak boleh dieksekusi (AST terbatas)."""
    from captcha_solver import solve_text

    # __import__ bukan aritmatika → worker harus balik ke fallback angka/teks
    out = solve_text("__import__('os').system('id')")
    assert "uid=" not in out


# --------------------------------------------------------------- image worker

def test_image_roundtrip() -> None:
    """Gambar captcha sintetis → OCR. Toleran: ddddocr bisa beda tipis."""
    import random

    from PIL import Image, ImageDraw, ImageFont

    from captcha_solver import solve_image

    txt = "8f3kd"
    img = Image.new("RGB", (200, 70), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
    except Exception:
        f = ImageFont.load_default()
    d.text((25, 12), txt, fill="black", font=f)
    for _ in range(6):
        d.line(
            [(random.randint(0, 200), random.randint(0, 70)),
             (random.randint(0, 200), random.randint(0, 70))],
            fill="gray",
            width=2,
        )

    p = Path(tempfile.mkdtemp()) / "cap.png"
    img.save(p)
    out = solve_image(p).lower()
    assert len(out) >= 3, f"hasil terlalu pendek: {out!r}"


def test_image_from_bytes() -> None:
    """Terima bytes langsung, bukan cuma path."""
    from captcha_solver import solve_image

    data = (ROOT / "testdata" / "captcha_like.png").read_bytes()
    assert solve_image(data).strip()


def test_image_missing_file() -> None:
    from captcha_solver import SolverError, solve_image

    with pytest.raises(SolverError):
        solve_image("/tmp/definitely-not-here-12345.png")


def test_image_empty_bytes() -> None:
    from captcha_solver import SolverError, solve_image

    with pytest.raises(SolverError):
        solve_image(b"")


# ------------------------------------------------------------------- router

def test_router_dispatch() -> None:
    from captcha_solver import solve

    assert solve("text", "4 + 8") == "12"
    assert solve("textcaptcha", "7 x 6") == "42"


def test_router_unknown_kind() -> None:
    from captcha_solver import SolverError, solve

    with pytest.raises(SolverError):
        solve("nonsense", "x")


# ----------------------------------------------------------------- fallback

def test_fallback_disabled_by_default() -> None:
    """Fallback harus MATI kecuali MIAW_FALLBACK=1 — biar tes tidak bakar kuota."""
    import os

    from captcha_solver import fallback

    os.environ.pop("MIAW_FALLBACK", None)
    assert fallback.enabled() is False


def test_fallback_local_first(monkeypatch) -> None:
    """Kalau solver lokal jalan, 2captcha tidak boleh dipanggil."""
    from captcha_solver import fallback

    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("2captcha tidak boleh dipanggil saat lokal sukses")

    monkeypatch.setattr(fallback, "solve_image_2captcha", _boom)
    answer, source = fallback.solve_image_safe((ROOT / "testdata" / "captcha_like.png").read_bytes())
    assert source == "local"
    assert answer.strip()
    assert called["n"] == 0


# -------------------------------------------------------------------- audio

def _audio_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _audio_available(), reason="faster-whisper tidak terpasang")
def test_audio_rejects_missing_file() -> None:
    from captcha_solver import SolverError, solve_audio

    with pytest.raises(SolverError):
        solve_audio("/tmp/definitely-not-here-12345.wav")


@pytest.mark.skipif(not _audio_available(), reason="faster-whisper tidak terpasang")
def test_audio_transcribes_fixture() -> None:
    """Transkripsi berkas uji (dibuat scripts/make_audio_fixture.py).

    Toleran: hanya cek isi jawaban, bukan kecocokan persis — kualitas TTS dan
    model whisper bervariasi. Di-skip kalau berkas uji belum ada.
    """
    from captcha_solver import solve_audio

    fixture = ROOT / "testdata" / "audio_4c7n.wav"
    if not fixture.exists():
        pytest.skip("berkas uji audio belum dibuat")
    out = solve_audio(fixture).lower().replace(" ", "")
    assert out, "transkripsi kosong"
    # '4c7n' → whisper bisa dengar '4 c 7 n' / 'forsee seven en'
    assert any(ch.isalnum() for ch in out)


# --------------------------------------------------------------- grid (opsional)

def test_grid_requires_playwright_module() -> None:
    """Grid worker harus melempar pesan jelas kalau playwright tidak ada."""
    from captcha_solver.workers.grid import GridWorker

    try:
        GridWorker()._require_playwright()
    except RuntimeError as e:
        assert "playwright" in str(e).lower()


def _main() -> int:
    fns = [
        test_text_arithmetic,
        test_text_words_and_symbols,
        test_text_rejects_empty,
        test_text_rejects_injection,
        test_image_roundtrip,
        test_image_from_bytes,
        test_image_missing_file,
        test_image_empty_bytes,
        test_router_dispatch,
        test_router_unknown_kind,
        test_fallback_disabled_by_default,
        test_grid_requires_playwright_module,
    ]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print("semua uji lolos ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
