#!/usr/bin/env python3
"""Bikin berkas audio uji dari teks (buat menguji worker audio Miaw Solver).

Pakai edge-tts kalau ada (kualitas bagus, butuh internet), kalau tidak jatuh ke
espeak-ng. Hasil default: WAV mono 16 kHz — format yang enak buat faster-whisper.

Pakai:
    python scripts/make_audio_fixture.py "4 c 7 n" testdata/audio_4c7n.wav
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _edge_tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401

        return True
    except ImportError:
        return False


def synth_edge(text: str, out: Path, voice: str = "en-US-AriaNeural") -> None:
    """TTS via edge-tts (mp3) lalu transcode ke wav 16k mono via ffmpeg."""
    import asyncio

    import edge_tts

    with tempfile.TemporaryDirectory() as td:
        mp3 = Path(td) / "raw.mp3"

        async def _go():
            com = edge_tts.Communicate(text, voice)
            await com.save(str(mp3))

        asyncio.run(_go())
        if not mp3.exists() or mp3.stat().st_size == 0:
            raise RuntimeError("edge-tts tidak menghasilkan audio")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
             "-ac", "1", "-ar", "16000", str(out)],
            check=True,
        )


def synth_espeak(text: str, out: Path) -> None:
    tmp = out.with_suffix(".tmp.wav")
    subprocess.run(["espeak-ng", "-w", str(tmp), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
         "-ac", "1", "-ar", "16000", str(out)],
        check=True,
    )
    tmp.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    text, out = argv[1], Path(argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)

    if _edge_tts_available():
        print(f"edge-tts -> {out}")
        synth_edge(text, out)
    elif shutil.which("espeak-ng"):
        print(f"espeak-ng -> {out}")
        synth_espeak(text, out)
    else:
        print("error: butuh edge-tts atau espeak-ng", file=sys.stderr)
        return 1
    print(f"ok: {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
