#!/usr/bin/env python3
"""Test REAL jalur LENGKAP: reCAPTCHA v2 → tantangan gambar → tombol AUDIO → transkripsi.

Ini uji paling berharga karena menyatukan dua engine kita (grid + audio) di
hadapannya captcha Google yang sungguhan, bukan test-key.

Alur:
  1. buka demo resmi Google
  2. klik checkbox
  3. tunggu tantangan gambar muncul
  4. klik tombol audio (headphone)
  5. unduh berkas audio dari Google
  6. transkripsi pakai AudioWorker kita
  7. isi jawaban + klik verify
  8. cek token

Jalankan:
    python scripts/test_real_recaptcha_audio.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TARGET = "https://www.google.com/recaptcha/api2/demo"
OUT_AUDIO = Path("/tmp/recaptcha_challenge.mp3")


async def main() -> int:
    from playwright.async_api import async_playwright

    hasil: dict = {"target": TARGET, "tahap": [], "jawaban": None, "status": "GAGAL"}

    def catat(t: str, d: str = "") -> None:
        hasil["tahap"].append(f"{t}{': ' + d if d else ''}")
        print(f"      {t}{': ' + d if d else ''}", flush=True)

    print("=" * 70)
    print("  TEST REAL — jalur audio reCAPTCHA v2 (grid + audio engine)")
    print("=" * 70)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(
            locale="en-US", viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await ctx.new_page()
        try:
            await page.goto(TARGET, wait_until="domcontentloaded", timeout=45_000)
            catat("1. halaman", "terbuka")

            anchor = page.frame_locator("iframe[src*='api2/anchor']")
            box = anchor.locator("#recaptcha-anchor")
            await box.wait_for(state="attached", timeout=30_000)
            await page.wait_for_timeout(2000)
            await box.click(timeout=20_000)
            catat("2. checkbox", "diklik")
            await page.wait_for_timeout(5000)

            bframe = page.frame_locator("iframe[src*='api2/bframe']")

            # --- tantangan gambar muncul? ---
            try:
                prompt = await bframe.locator(".prompt-text").first.inner_text(timeout=10_000)
                catat("3. tantangan gambar", repr(" ".join(prompt.split())[:60]))
            except Exception as e:  # noqa: BLE001
                catat("3. tantangan gambar", f"tidak muncul ({type(e).__name__})")

            # --- klik tombol audio ---
            try:
                tombol = bframe.locator("#recaptcha-audio-button")
                await tombol.wait_for(state="visible", timeout=15_000)
                await tombol.click(timeout=15_000)
                catat("4. tombol audio", "diklik")
            except Exception as e:  # noqa: BLE001
                catat("4. tombol audio", f"GAGAL — {type(e).__name__}")
                hasil["status"] = "TOMBOL AUDIO TIDAK ADA"
                return await selesai(hasil, ctx, browser)

            await page.wait_for_timeout(4000)

            # --- unduh audio ---
            audio_url = None
            try:
                src = await bframe.locator("#audio-source").get_attribute("src", timeout=15_000)
                audio_url = src
                catat("5. url audio", (src or "")[:80])
            except Exception as e:  # noqa: BLE001
                catat("5. url audio", f"tidak ketemu ({type(e).__name__})")

            if not audio_url:
                # mungkin diblokir — cek pesan
                try:
                    pesan = await bframe.locator(".rc-audiochallenge-error-message, "
                                                 ".rc-doscaptcha-header-text").first.inner_text(timeout=6000)
                    catat("5b. pesan Google", repr(" ".join(pesan.split())[:120]))
                except Exception:  # noqa: BLE001
                    pass
                hasil["status"] = "AUDIO TIDAK TERSEDIA (kemungkinan IP diblokir)"
                return await selesai(hasil, ctx, browser)

            # --- unduh lewat browser (pakai cookie/sesi yang sama) ---
            try:
                data = await page.evaluate(
                    """async (url) => {
                        const r = await fetch(url);
                        if (!r.ok) return {err: 'HTTP ' + r.status};
                        const b = await r.arrayBuffer();
                        return {b64: btoa(String.fromCharCode(...new Uint8Array(b)))};
                    }""",
                    audio_url,
                )
                if data.get("err"):
                    catat("6. unduh audio", data["err"])
                    hasil["status"] = f"UNDUH GAGAL: {data['err']}"
                    return await selesai(hasil, ctx, browser)
                import base64
                blob = base64.b64decode(data["b64"])
                OUT_AUDIO.write_bytes(blob)
                catat("6. unduh audio", f"{len(blob)} byte -> {OUT_AUDIO}")
            except Exception as e:  # noqa: BLE001
                catat("6. unduh audio", f"GAGAL — {type(e).__name__}: {e}")
                hasil["status"] = "UNDUH GAGAL"
                return await selesai(hasil, ctx, browser)

            # --- transkripsi pakai engine kita ---
            t0 = time.perf_counter()
            try:
                from captcha_solver.workers.audio import AudioWorker
                w = AudioWorker()
                jawaban = w.solve(str(OUT_AUDIO))
                ms = int((time.perf_counter() - t0) * 1000)
                hasil["jawaban"] = jawaban
                catat("7. transkripsi", f"{jawaban!r} ({ms} ms)")
            except Exception as e:  # noqa: BLE001
                catat("7. transkripsi", f"GAGAL — {type(e).__name__}: {e}")
                hasil["status"] = "TRANSKRIPSI GAGAL"
                return await selesai(hasil, ctx, browser)

            # --- isi jawaban + verify ---
            try:
                await bframe.locator("#audio-response").fill(jawaban, timeout=10_000)
                catat("8. isi jawaban", "ok")
                await bframe.locator("#recaptcha-verify-button").click(timeout=10_000)
                catat("9. verify", "diklik")
            except Exception as e:  # noqa: BLE001
                catat("8-9. isi+verify", f"GAGAL — {type(e).__name__}")
                hasil["status"] = "GAGAL ISI/VERIFY"
                return await selesai(hasil, ctx, browser)

            await page.wait_for_timeout(6000)

            # --- cek token ---
            token = await page.evaluate(
                "() => document.querySelector('#g-recaptcha-response')?.value || ''"
            )
            if token:
                hasil["status"] = f"SUKSES TOTAL — token {len(token)} char"
                catat("10. token", f"KELUAR — {len(token)} char ✅")
            else:
                # cek pesan error dari Google
                try:
                    err = await bframe.locator(".rc-audiochallenge-error-message").first.inner_text(timeout=6000)
                    catat("10. token", f"kosong — Google bilang: {err.strip()[:100]!r}")
                    hasil["status"] = f"DITOLAK: {err.strip()[:80]}"
                except Exception:  # noqa: BLE001
                    catat("10. token", "kosong (tanpa pesan)")
                    hasil["status"] = "TOKEN KOSONG — jawaban kemungkinan salah"
            return await selesai(hasil, ctx, browser)
        except Exception as e:  # noqa: BLE001
            catat("ERROR", f"{type(e).__name__}: {e}")
            hasil["status"] = f"ERROR: {type(e).__name__}"
            return await selesai(hasil, ctx, browser)


async def selesai(hasil: dict, ctx, browser) -> int:
    print(f"\n  => {hasil['status']}")
    Path("test_real_audio_result.json").write_text(
        json.dumps(hasil, indent=2, ensure_ascii=False))
    await ctx.close()
    await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
