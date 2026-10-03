#!/usr/bin/env python3
"""Bukti jalan: `GridWorker.solve_recaptcha_v2` terhadap test-sitekey resmi Google.

Test-sitekey `6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI` adalah pasangan publik
yang disediakan Google untuk pengujian — widgetnya langsung lolos tanpa tantangan
gambar/audio. Tujuannya membuktikan **jalur kode** kita jalan: widget ter-render,
checkbox ter-klik, token terisi.

Skrip ini sengaja memanggil `GridWorker.solve_recaptcha_v2` yang asli, bukan alur
Playwright tulis-sendiri. Kalau `GridWorker` rusak, skrip ini ikut merah — itu
intinya. Versi lama menyalin ulang alur Playwright, jadi hijau di sini tidak
membuktikan apa pun tentang kode yang benar-benar dipakai.

Ini BUKAN bukti bypass captcha nyata: tantangan sungguhan (gambar/audio) tetap
berhenti di tempat yang sama seperti dijelaskan README.

Pakai:
    python scripts/prove_grid.py
"""
from __future__ import annotations

import asyncio
import sys

TEST_SITEKEY = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"


async def main() -> int:
    from captcha_solver.workers.grid import GridWorker

    worker = GridWorker(headless=True)
    print(f"  sitekey       : {TEST_SITEKEY}")
    print("  memanggil     : GridWorker.solve_recaptcha_v2(pageurl=None, ...)")
    try:
        # pageurl=None -> worker menyajikan halaman pembungkus dari origin lokal
        token = await worker.solve_recaptcha_v2("", TEST_SITEKEY)
    except Exception as e:  # noqa: BLE001
        print(f"  HASIL         : ❌ {type(e).__name__}: {e}")
        return 1

    print(f"  token length  : {len(token)}")
    print(f"  token sample  : {token[:40]!r}")
    if token:
        print("  HASIL         : ✅ jalur grid berfungsi (token didapat lewat GridWorker)")
        return 0
    print("  HASIL         : ❌ token kosong")
    return 1


if __name__ == "__main__":
    print("=== bukti GridWorker.solve_recaptcha_v2: reCAPTCHA v2 test-key ===")
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
