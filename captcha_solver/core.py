"""INTI — otak captcha solver. Semua pintu (CLI/Library/API) manggil ke sini.

CPU-first: model dimuat malas (lazy) supaya `import captcha_solver` tetap ringan.

Thread-safety: pemuatan model dilindungi lock per-worker (double-checked locking).
Server memanggil solver lewat `asyncio.to_thread`, jadi dua request bersamaan bisa
masuk ke `_load_*` pada saat yang sama; tanpa lock, model dimuat dua kali
(boros RAM + dua ONNX session).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Union

BytesLike = Union[bytes, bytearray, str, Path]


class SolverError(Exception):
    """Gagal solve captcha (file rusak, tipe tak didukung, dll)."""


# ---- lazy singletons: model dimuat sekali, saat pertama dipakai ----
_ocr = None
_text = None
_audio = None

_ocr_lock = threading.Lock()
_text_lock = threading.Lock()
_audio_lock = threading.Lock()


def _load_ocr():
    global _ocr
    if _ocr is None:                      # jalur cepat: sudah dimuat, tanpa lock
        with _ocr_lock:
            if _ocr is None:              # cek ulang di dalam lock
                from .workers.ocr import OcrWorker
                _ocr = OcrWorker()
    return _ocr


def _load_text():
    global _text
    if _text is None:
        with _text_lock:
            if _text is None:
                from .workers.text import TextWorker
                _text = TextWorker()
    return _text


def _load_audio():
    global _audio
    if _audio is None:
        with _audio_lock:
            if _audio is None:
                from .workers.audio import AudioWorker
                _audio = AudioWorker()
    return _audio


def _as_bytes(blob: BytesLike) -> bytes:
    if isinstance(blob, (bytes, bytearray)):
        return bytes(blob)
    p = Path(blob)
    if not p.is_file():
        raise SolverError(f"file tidak ada: {p}")
    return p.read_bytes()


def solve_image(image: BytesLike) -> str:
    """Solve captcha gambar (teks terdistorsi). Balikin teks jawaban.

    >>> solve_image("testdata/sample.png")   # doctest: +SKIP
    '8f3kd'
    """
    data = _as_bytes(image)
    if not data:
        raise SolverError("gambar kosong")
    try:
        return _load_ocr().solve(data)
    except SolverError:
        raise
    except Exception as e:  # noqa: BLE001 — permukaan library harus rapi
        raise SolverError(f"OCR gagal: {e}") from e


def solve_text(question: str) -> str:
    """Solve captcha tanya-jawab ("Berapa 4 + 8 ?"). Balikin jawaban.

    >>> solve_text("Berapa hasil dari 4 + 8 ?")   # doctest: +SKIP
    '12'
    """
    if not question or not question.strip():
        raise SolverError("pertanyaan kosong")
    return _load_text().solve(question)


def solve_audio(audio: BytesLike) -> str:
    """Solve captcha suara (transkripsi). Balikin jawaban alfanumerik.

    >>> solve_audio("testdata/audio.wav")   # doctest: +SKIP
    '4c7n8'
    """
    if not isinstance(audio, (bytes, bytearray)):
        p = Path(audio)
        if not p.is_file():
            raise SolverError(f"file audio tidak ada: {p}")
        audio = p.read_bytes()
    if not audio:
        raise SolverError("audio kosong")
    try:
        return _load_audio().solve(audio)
    except SolverError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SolverError(f"audio gagal: {e}") from e


def solve(kind: str, payload) -> str:
    """Router tipe -> worker. `kind` in {"image", "text", "audio"}.

    Tipe lain yang sudah didaftarkan lewat `register_engine()` juga jalan.
    """
    kind = (kind or "").strip().lower()
    if kind in ("image", "img", "post", "base64", "normal"):
        return solve_image(payload)
    if kind in ("text", "textcaptcha", "question"):
        return solve_text(payload)
    if kind in ("audio", "sound", "voice"):
        return solve_audio(payload)
    if kind in _ENGINES:
        return _run_engine(kind, payload)
    raise SolverError(f"tipe captcha tidak dikenal: {kind!r}")


# --------------------------------------------------------------------------
# Extension point — pasang engine sendiri tanpa mengubah core.
#
#     from captcha_solver.core import register_engine
#     register_engine("roman", lambda q: str(roman_to_int(q)))
#     solve("roman", "XIV")     # -> "14"
#
# Engine wajib: menerima satu payload, mengembalikan str, dan melempar
# SolverError (atau exception apa pun — akan dibungkus) kalau gagal.
# --------------------------------------------------------------------------

_ENGINES: dict[str, Callable[[object], str]] = {}


def register_engine(name: str, fn: "Callable[[object], str]", *, override: bool = False) -> None:
    """Daftarkan engine kustom di bawah `name`.

    Args:
        name: pengenal huruf kecil; dipakai oleh `solve(name, payload)`.
        fn: callable `(payload) -> str`.
        override: izinkan menimpa engine bawaan/terdaftar (default: tolak,
            supaya registrasi diam-diam tidak merusak perilaku bawaan).

    Raises:
        SolverError: nama tidak valid, atau sudah terpakai tanpa `override`.
    """
    key = (name or "").strip().lower()
    if not key or not key.replace("_", "").replace("-", "").isalnum():
        raise SolverError(f"nama engine tidak valid: {name!r}")
    if not callable(fn):
        raise SolverError("engine harus callable")
    if key in _BUILTIN:
        raise SolverError(f"{key!r} adalah engine bawaan dan tidak bisa ditimpa")
    if key in _ENGINES and not override:
        raise SolverError(f"engine {key!r} sudah terdaftar (pakai override=True untuk menimpa)")
    _ENGINES[key] = fn


def unregister_engine(name: str) -> None:
    """Hapus engine kustom. Tidak berpengaruh pada engine bawaan."""
    _ENGINES.pop((name or "").strip().lower(), None)


def engines() -> list[str]:
    """Daftar nama engine kustom (bawaan tidak termasuk)."""
    return sorted(_ENGINES)


def _run_engine(name: str, payload) -> str:
    try:
        out = _ENGINES[name](payload)
    except SolverError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SolverError(f"engine {name!r} gagal: {e}") from e
    if not isinstance(out, str):
        raise SolverError(f"engine {name!r} mengembalikan {type(out).__name__}, bukan str")
    return out


_BUILTIN = {"image", "img", "post", "base64", "normal",
            "text", "textcaptcha", "question",
            "audio", "sound", "voice", "grid"}
