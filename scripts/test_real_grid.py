#!/usr/bin/env python3
"""Test REAL — Miaw Solver lawan captcha sungguhan di internet.

Tujuan: mengukur sampai mana solver benar-benar jalan, dan di titik mana
berhenti. Setiap tahap dicatat apa adanya — tidak ada klaim tanpa bukti.

Jalankan:
    python scripts/test_real_grid.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Situs nyata yang memakai reCAPTCHA v2. Yang resmi dari Google dipakai sebagai
# baseline; sisanya demo publik milik pengembang captcha (memang disediakan
# untuk menguji integrasi, bukan situs produksi pihak lain).
TARGETS = [
    {
        "nama": "Google official reCAPTCHA v2 demo",
        "url": "https://www.google.com/recaptcha/api2/demo",
        "sitekey": "6LfD3PIbAAAAAJs_eEHvoOl75_83eXSqpPSRFJ_u",
    },
    {
        "nama": "Google reCAPTCHA v2 test-key demo",
        "url": "https://recaptcha-demo.appspot.com/recaptcha-v2-checkbox.php",
        "sitekey": "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI",
    },
]

# hCaptcha demo resmi
HCAPTCHA_TARGET = {
    "nama": "hCaptcha official demo",
    "url": "https://accounts.hcaptcha.com/demo",
    "sitekey": "10000000-ffff-ffff-ffff-000000000001",
}


async def probe(target: dict) -> dict:
    """Buka satu target, catat setiap tahap. Tidak pernah raise — selalu lapor."""
    from playwright.async_api import async_playwright

    hasil = {
        "nama": target["nama"],
        "url": target["url"],
        "tahap": [],
        "token_len": 0,
        "status": "GAGAL",
    }

    def catat(tahap: str, detail: str = "") -> None:
        hasil["tahap"].append(f"{tahap}{': ' + detail if detail else ''}")

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
            # --- tahap 1: halaman terbuka ---
            t0 = time.perf_counter()
            resp = await page.goto(target["url"], wait_until="domcontentloaded", timeout=45_000)
            catat("1. halaman terbuka", f"HTTP {resp.status if resp else '?'} "
                                        f"({int((time.perf_counter()-t0)*1000)} ms)")

            # --- tahap 2: iframe captcha muncul ---
            try:
                anchor = page.frame_locator("iframe[src*='api2/anchor'], iframe[title*='reCAPTCHA']")
                box = anchor.locator("#recaptcha-anchor")
                await box.wait_for(state="attached", timeout=30_000)
                catat("2. widget ter-render", "iframe anchor ditemukan")
            except Exception as e:  # noqa: BLE001
                catat("2. widget ter-render", f"GAGAL — {type(e).__name__}")
                hasil["status"] = "WIDGET TIDAK MUNCUL"
                return hasil

            await page.wait_for_timeout(2000)

            # --- tahap 3: ada pesan error domain? ---
            try:
                body = await anchor.locator("body").inner_text(timeout=6000)
                bersih = " ".join(body.split())[:70]
                if "invalid domain" in body.lower():
                    catat("3. cek pesan", f"DITOLAK — {bersih!r}")
                    hasil["status"] = "DOMAIN DITOLAK"
                    return hasil
                catat("3. cek pesan", f"ok — {bersih!r}")
            except Exception:  # noqa: BLE001
                catat("3. cek pesan", "(tidak bisa dibaca)")

            # --- tahap 4: klik checkbox ---
            try:
                await box.click(timeout=20_000)
                catat("4. checkbox diklik", "ok")
            except Exception as e:  # noqa: BLE001
                catat("4. checkbox diklik", f"GAGAL — {type(e).__name__}")
                hasil["status"] = "KLIK GAGAL"
                return hasil

            await page.wait_for_timeout(4000)

            # --- tahap 5: token keluar? ---
            token = await page.evaluate(
                "() => document.querySelector('#g-recaptcha-response')?.value || "
                "(document.querySelector('textarea[name=\"g-recaptcha-response\"]')?.value || '')"
            )
            if token:
                hasil["token_len"] = len(token)
                catat("5. token", f"KELUAR — {len(token)} char")
                hasil["status"] = "SUKSES (checkbox lolos tanpa tantangan)"
                return hasil

            catat("5. token", "kosong")

            # --- tahap 6: naik ke tantangan gambar? ---
            bframe = page.frame_locator(
                "iframe[src*='api2/bframe'], iframe[title*='challenge']")
            try:
                judul = await bframe.locator(".prompt-text, #rc-imageselect").first.inner_text(timeout=8000)
                catat("6. tantangan", f"GAMBAR muncul — {judul.strip()[:60]!r}")
                hasil["status"] = "BERHENTI DI TANTANGAN GAMBAR (butuh model vision)"
            except Exception:  # noqa: BLE001
                # cek apakah jalur audio tersedia
                try:
                    aud = await bframe.locator("#recaptcha-audio-button").count()
                    if aud:
                        catat("6. tantangan", "tombol AUDIO tersedia (bisa ditempuh engine audio)")
                        hasil["status"] = "TANTANGAN — jalur audio tersedia"
                    else:
                        catat("6. tantangan", "tidak terdeteksi")
                        hasil["status"] = "TIDAK DIKETAHUI"
                except Exception:  # noqa: BLE001
                    catat("6. tantangan", "tidak terdeteksi")
                    hasil["status"] = "TIDAK DIKETAHUI"
            return hasil
        finally:
            await ctx.close()
            await browser.close()


async def main() -> int:
    print("=" * 70)
    print("  TEST REAL — Miaw Solver lawan reCAPTCHA v2 di internet")
    print("=" * 70)
    hasil_semua = []
    for t in TARGETS:
        print(f"\n>>> {t['nama']}")
        print(f"    {t['url']}")
        try:
            h = await probe(t)
        except Exception as e:  # noqa: BLE001
            h = {"nama": t["nama"], "url": t["url"], "status": f"ERROR: {type(e).__name__}: {e}",
                 "token_len": 0, "tahap": []}
        for baris in h["tahap"]:
            print(f"      {baris}")
        print(f"    => {h['status']}")
        hasil_semua.append(h)

    out = Path("test_real_grid_result.json")
    out.write_text(json.dumps(hasil_semua, indent=2, ensure_ascii=False))
    print(f"\n  hasil tersimpan: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
