"""Worker audio — solve captcha suara (reCAPTCHA audio challenge, dsb).

CPU-first: pakai faster-whisper (CTranslate2). Model dimuat malas & sekali saja.

Ukuran model:
    tiny   ~40 MB, paling cepat, akurasi cukup utk digit/kata acak pendek
    base   ~75 MB, default (imbang)
    small  ~250 MB, akurasi lebih baik, lebih lambat

Catatan: captcha audio biasanya berisi digit/kata acak berbahasa Inggris. Model
multibahasa bawaan sudah cukup; kita tidak menerjemahkan, hanya transkripsi.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# Model default bisa di-override lewat env (mis. MIAW_WHISPER_MODEL=base)
DEFAULT_MODEL = os.environ.get("MIAW_WHISPER_MODEL", "base")
# Device: "cpu" (default) atau "cuda" buat varian GPU
DEFAULT_DEVICE = os.environ.get("MIAW_WHISPER_DEVICE", "cpu")
# int8 = paling cepat di CPU; float16 lebih cocok di GPU
DEFAULT_COMPUTE = os.environ.get(
    "MIAW_WHISPER_COMPUTE", "float16" if DEFAULT_DEVICE == "cuda" else "int8"
)

# faster-whisper mengembalikan teks dengan spasi/ tanda baca; captcha biasanya
# alfanumerik polos. Normalisasi ringan, JANGAN buang huruf/angka.
_JUNK = re.compile(r"[^A-Za-z0-9]+")

# Magic bytes format audio yang umum. Dipakai untuk menebak tipe task di /in
# tanpa memaksa klien mengirim `method=audio` — 2captcha punya method itu, tapi
# banyak klien lupa mengisinya.
_AUDIO_MAGIC = (b"RIFF", b"OggS", b"fLaC", b"\x1a\x45\xdf\xa3")  # wav, ogg, flac, matroska


def looks_like_audio(data: bytes) -> bool:
    """Tebak apakah blob ini audio dari magic bytes-nya."""
    if len(data) < 12:
        return False
    return data[:4] in _AUDIO_MAGIC or data[:3] == b"ID3"


class AudioWorker:
    """Transkripsi file audio (path/bytes) menjadi teks jawaban captcha."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE,
    ):
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    def transcribe(self, audio) -> str:
        """Audio -> teks mentah (apa adanya, sudah di-strip)."""
        path = _as_path(audio)
        model = self._load()
        segments, _info = model.transcribe(
            path,
            language="en",          # captcha audio umumnya English
            beam_size=1,            # cepat; captcha cuma beberapa kata
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text for seg in segments).strip()

    def solve(self, audio) -> str:
        """Audio -> jawaban siap-pakai (tanpa spasi/tanda baca)."""
        raw = self.transcribe(audio)
        if not raw:
            raise ValueError("audio tidak menghasilkan teks")
        answer = _JUNK.sub("", raw)
        if not answer:
            raise ValueError("audio tidak menghasilkan teks yang bisa dipakai")
        return answer


def _as_path(audio) -> str:
    """faster-whisper butuh path/stream; bytes ditulis ke file sementara."""
    if isinstance(audio, (bytes, bytearray)):
        import tempfile

        fd, tmp = tempfile.mkstemp(suffix=".wav")
        with os.fdopen(fd, "wb") as fh:
            fh.write(bytes(audio))
        return tmp
    p = Path(audio)
    if not p.is_file():
        raise ValueError(f"file audio tidak ada: {p}")
    return str(p)
