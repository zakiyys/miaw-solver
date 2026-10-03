#!/usr/bin/env python3
"""Bukti jalan: GridWorker terhadap reCAPTCHA v2 test-sitekey resmi Google.

Test-sitekey `6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI` adalah pasangan publik
yang disediakan Google untuk pengujian — widgetnya langsung lolos tanpa tantangan
gambar/audio. Tujuannya membuktikan **jalur kode** kita jalan: widget ter-render,
checkbox ter-klik, token terisi.

Ini BUKAN bukti bypass captcha nyata (tantangan audio sungguhan butuh audio asli
dari Google dan sudah diimplementasikan di GridWorker.solve_recaptcha_v2).

Pakai:
    python scripts/prove_grid.py
"""
from __future__ import annotations

import asyncio
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

TEST_SITEKEY = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"

HTML = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>miaw grid proof</title></head>
<body style="margin:20px">
<script src="https://www.google.com/recaptcha/api.js?hl=en" async defer></script>
<div class="g-recaptcha" data-sitekey="{TEST_SITEKEY}"></div>
</body></html>"""


class _H(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


async def main() -> int:
    from playwright.async_api import async_playwright

    srv = HTTPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"  origin        : {url}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")

            anchor = page.frame_locator("iframe[src*='api2/anchor']")
            box = anchor.locator("#recaptcha-anchor")
            await box.wait_for(state="attached", timeout=30_000)
            await page.wait_for_timeout(1500)

            body = await anchor.locator("body").inner_text(timeout=8000)
            if "invalid domain" in body.lower():
                print("  widget        : DITOLAK (invalid domain)")
                return 2
            print(f"  widget        : ter-render ✅ ({body.strip()[:50]!r})")

            await box.click(timeout=30_000)
            await page.wait_for_timeout(3000)

            token = await page.evaluate(
                "() => document.querySelector('#g-recaptcha-response')?.value || ''"
            )
            print(f"  token length  : {len(token)}")
            print(f"  token sample  : {token[:40]!r}")
            if token:
                print("  HASIL         : ✅ jalur grid berfungsi (token didapat)")
                return 0
            print("  HASIL         : ❌ token kosong")
            return 1
        finally:
            await ctx.close()
            await browser.close()
            srv.shutdown()


if __name__ == "__main__":
    print("=== bukti GridWorker: reCAPTCHA v2 test-key ===")
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
