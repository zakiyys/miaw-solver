"""Worker grid captcha — reCAPTCHA v2 & hCaptcha via browser otomatis.

Dua jalur:

1. **Audio challenge (reCAPTCHA v2)** — cara paling andal tanpa model visi:
   buka widget, klik checkbox, pindah ke tantangan audio, unduh berkas audio,
   transkripsi pakai worker audio (faster-whisper), isi jawaban, submit.
   Ini yang dipakai `solve_recaptcha_v2()`.

2. **Grid image (hCaptcha)** — butuh model visi untuk memilih ubin. Belum
   diimplementasikan di v0.3; kalau dipanggil, lempar SolverError yang jelas
   supaya pemanggil bisa jatuh ke fallback 2captcha.

Playwright + Chromium bersifat OPSIONAL: modul ini hanya diimpor saat dipakai,
jadi `import captcha_solver` tetap ringan dan CI tetap jalan tanpa browser.

CATATAN PENTING (temuan uji, 3 Okt 2026):
    reCAPTCHA menolak origin `about:blank` — kalau widget di-render lewat
    `page.set_content()`, yang muncul adalah "ERROR for site owner: Invalid
    domain for site key", bukan checkbox. Widget HARUS di-serve dari origin
    http(s) asli. Karena itu halaman pembungkus disajikan oleh server HTTP mini
    lokal (`_WidgetServer`), bukan `set_content()`.
"""
from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Selector reCAPTCHA v2 (diverifikasi 3 Okt 2026)
_SEL_ANCHOR_IFRAME = "iframe[src*='api2/anchor']"
_SEL_BFIFRAME = "iframe[src*='api2/bframe']"
_SEL_CHECKBOX = "#recaptcha-anchor"
_SEL_AUDIO_BUTTON = "#recaptcha-audio-button"
_SEL_AUDIO_SOURCE = "#audio-source"
_SEL_AUDIO_RESPONSE = "#audio-response"
_SEL_VERIFY = "#recaptcha-verify-button"

_AUDIO_BLOCKED_MARKERS = ("try again later", "automated queries")
_WRAPPER = (
    "<!doctype html><html><head><meta charset='utf-8'></head>"
    "<body style='margin:20px'>"
    "<script src='https://www.google.com/recaptcha/api.js?hl=en'></script>"
    "<div class='g-recaptcha' data-sitekey='{sitekey}'></div>"
    "</body></html>"
)


class _WidgetServer:
    """Server HTTP mini — memberi widget origin asli (wajib untuk reCAPTCHA)."""

    def __init__(self, sitekey: str):
        body = _WRAPPER.format(sitekey=sitekey).encode()

        class _H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # senyap
                pass

        self._srv = HTTPServer(("127.0.0.1", 0), _H)
        self.port = self._srv.server_address[1]
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._t.start()

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}/"

    def close(self) -> None:
        self._srv.shutdown()


class GridWorker:
    """Solver grid berbasis browser. Berat — pakai hanya kalau memang perlu."""

    def __init__(self, headless: bool = True, timeout_ms: int = 45_000):
        self._headless = headless
        self._timeout = timeout_ms

    # ---------- util ----------

    @staticmethod
    def _require_playwright():
        try:
            from playwright.async_api import async_playwright  # noqa: F401
        except ImportError as e:  # pragma: no cover - bergantung lingkungan
            raise RuntimeError(
                "playwright belum terpasang. Jalankan: "
                "pip install 'miaw-solver[grid]' && playwright install chromium"
            ) from e

    async def _launch(self, pw):
        browser = await pw.chromium.launch(
            headless=self._headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = await browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        return browser, ctx

    async def _fetch_audio_bytes(self, page) -> bytes:
        """Unduh berkas audio tantangan lewat request context browser.

        Audio disajikan dari URL berumur pendek yang perlu cookie/sesi yang sama,
        jadi harus diambil dari konteks halaman — bukan HTTP polos.
        """
        src = await page.get_attribute(_SEL_AUDIO_SOURCE, "src")
        if not src:
            raise RuntimeError("sumber audio tidak ditemukan di DOM")
        resp = await page.request.get(src, timeout=self._timeout)
        if not resp.ok:
            raise RuntimeError(f"gagal unduh audio: HTTP {resp.status}")
        return await resp.body()

    async def _poll_token(self, page, timeout_ms: int) -> str:
        """Tunggu `#g-recaptcha-response` terisi, maksimal `timeout_ms`.

        Polling pendek, bukan sekali baca: token bisa terisi beberapa ratus ms
        setelah checkbox diklik. Mengembalikan "" kalau tetap kosong.
        """
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while True:
            token = await page.evaluate(
                "() => document.querySelector('#g-recaptcha-response')?.value || ''"
            )
            if token:
                return token
            if asyncio.get_running_loop().time() >= deadline:
                return ""
            await page.wait_for_timeout(250)

    async def solve_recaptcha_v2(self, pageurl: str, sitekey: str) -> str:
        """Selesaikan reCAPTCHA v2 lewat jalur tantangan audio.

        `pageurl` dipakai sebagai referer halaman nyata (kalau situs target punya
        domain terdaftar di sitekey). Kalau kosong, halaman pembungkus lokal dipakai.
        """
        self._require_playwright()
        from playwright.async_api import async_playwright

        from .audio import AudioWorker

        audio_worker = AudioWorker()
        server = None

        async with async_playwright() as pw:
            browser, ctx = await self._launch(pw)
            try:
                page = await ctx.new_page()
                target = pageurl if (pageurl or "").startswith("http") else None
                if not target:
                    server = _WidgetServer(sitekey)
                    target = server.url
                await page.goto(target, wait_until="domcontentloaded")

                anchor = page.frame_locator(_SEL_ANCHOR_IFRAME)
                box = anchor.locator(_SEL_CHECKBOX)
                await box.wait_for(state="attached", timeout=self._timeout)
                await page.wait_for_timeout(1200)

                # Widget bisa menampilkan error domain alih-alih checkbox
                try:
                    body = await anchor.locator("body").inner_text(timeout=8000)
                except Exception:  # noqa: BLE001
                    body = ""
                if "invalid domain" in body.lower():
                    raise RuntimeError(
                        "sitekey menolak origin ini ('Invalid domain for site key'). "
                        "Pakai pageurl yang terdaftar di sitekey tersebut."
                    )

                await box.click(timeout=self._timeout)

                # Widget yang langsung lolos (mis. test-sitekey resmi Google)
                # mengisi token tanpa tantangan apa pun. Cek dulu sebentar —
                # kalau tidak, kode ini membuang penuh waktu tunggu tombol audio
                # yang tidak akan pernah muncul.
                token = await self._poll_token(page, 3000)
                if token:
                    return token

                bframe = page.frame_locator(_SEL_BFIFRAME)
                await bframe.locator(_SEL_AUDIO_BUTTON).click(timeout=self._timeout)
                audio_bytes = await self._fetch_audio_bytes(page)

                try:
                    hint = await bframe.locator("#recaptcha-audio-download-link").inner_text()
                except Exception:  # noqa: BLE001
                    hint = ""
                for marker in _AUDIO_BLOCKED_MARKERS:
                    if marker in hint.lower():
                        raise RuntimeError(f"tantangan audio diblokir: {marker}")

                answer = audio_worker.solve(audio_bytes)
                await bframe.locator(_SEL_AUDIO_RESPONSE).fill(answer)
                await bframe.locator(_SEL_VERIFY).click(timeout=self._timeout)

                token = await self._poll_token(page, 2500)
                if not token:
                    raise RuntimeError("reCAPTCHA tidak memberi token (tantangan gagal)")
                return token
            finally:
                await ctx.close()
                await browser.close()
                if server is not None:
                    server.close()

    async def solve_hcaptcha(self, pageurl: str, sitekey: str) -> str:
        """hCaptcha — belum didukung (butuh model visi untuk ubin)."""
        raise RuntimeError(
            "hCaptcha grid belum didukung di v0.3; pakai fallback 2captcha "
            "(MIAW_FALLBACK=1)"
        )


def solve_recaptcha_v2(
    pageurl: str, sitekey: str, *, headless: bool | None = None
) -> str:
    """Pembungkus sinkron — biar bisa dipanggil dari CLI/library biasa.

    `headless=None` (default) mengambil `MIAW_GRID_HEADLESS` lewat `Config`.
    """
    if headless is None:
        from ..config import CFG

        headless = CFG.grid_headless
    return asyncio.run(GridWorker(headless=headless).solve_recaptcha_v2(pageurl, sitekey))
