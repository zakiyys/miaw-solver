#!/usr/bin/env python3
"""All four engines through the library API.

Run from the repo root:

    python examples/python_library.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from captcha_solver import solve_audio, solve_image, solve_text  # noqa: E402

TESTDATA = Path(__file__).resolve().parent.parent / "testdata"


def main() -> None:
    # 1. distorted image -> text
    png = (TESTDATA / "captcha_like.png").read_bytes()
    print(f"image : {solve_image(png)!r}")

    # 2. text / arithmetic question
    for q in ("4+8", "7x6", "tiga tambah lima", "twenty divided by four"):
        print(f"text  : {q!r} -> {solve_text(q)!r}")

    # 3. spoken digits
    wav = (TESTDATA / "audio_4c7n.wav").read_bytes()
    print(f"audio : {solve_audio(wav)!r}")

    # 4. grid (needs network + Chromium; commented out by default)
    # import asyncio
    # from captcha_solver.workers.grid import GridWorker
    #
    # async def grid():
    #     w = GridWorker(headless=True)
    #     token = await w.solve_recaptcha_v2(
    #         pageurl="https://example.com",
    #         sitekey="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI",
    #     )
    #     print(f"grid  : token of {len(token)} chars")
    #
    # asyncio.run(grid())


if __name__ == "__main__":
    main()
