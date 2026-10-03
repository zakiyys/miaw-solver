#!/usr/bin/env python3
"""🚪 CLI — Miaw Solver (implementasi di dalam package, biar `pip install` jalan).

Pakai:
    miaw-solve image gambar.png
    miaw-solve text "Berapa 4 + 8 ?"
    miaw-solve audio rekaman.wav
    cat gambar.png | miaw-solve image -        # '-' artinya baca stdin
    miaw-solve auto image gambar.png           # router eksplisit per tipe
    miaw-solve --version

`image` juga menerima alias lama `solve` supaya skrip lama tetap jalan.
"""
from __future__ import annotations

import argparse
import sys

from . import SolverError, __version__, solve, solve_audio, solve_image, solve_text

_HANDLERS = {
    "image": solve_image,
    "text": solve_text,
    "audio": solve_audio,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="miaw-solve", description="Solve CAPTCHA lokal (CPU-first).")
    p.add_argument("--version", action="version", version=f"miaw-solve {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("image", aliases=["solve"], help="solve captcha gambar")
    pi.add_argument("file", help="path gambar, atau '-' utk stdin")

    pt = sub.add_parser("text", help="solve captcha tanya-jawab")
    pt.add_argument("question", help='mis. "Berapa 4 + 8 ?"')

    pa = sub.add_parser("audio", help="solve captcha suara")
    pa.add_argument("file", help="path audio (wav/mp3/ogg), atau '-' utk stdin")

    ps = sub.add_parser("auto", help="router generik: tebak tipe dari isi")
    ps.add_argument("kind", choices=["image", "text", "audio"])
    ps.add_argument("payload")

    a = p.parse_args(argv)
    try:
        if a.cmd in ("image", "solve"):
            data = sys.stdin.buffer.read() if a.file == "-" else a.file
            print(solve_image(data))
        elif a.cmd == "text":
            print(solve_text(a.question))
        elif a.cmd == "audio":
            data = sys.stdin.buffer.read() if a.file == "-" else a.file
            print(solve_audio(data))
        else:  # auto
            print(solve(a.kind, a.payload))
    except SolverError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
