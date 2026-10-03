"""Fallback ke 2captcha kalau solver lokal gagal / di bawah ambang keyakinan.

Prinsip: lokal DULU (gratis), 2captcha hanya jaring pengaman terakhir.
Aktif hanya kalau TWOCAPTCHA_API_KEY ada DAN `MIAW_FALLBACK=1` (default: mati,
biar tes & CI tidak diam-diam menghabiskan kuota).

API 2captcha yang dipakai (identik dgn yang ditiru server Miaw):
    1. POST https://2captcha.com/in.php   -> {status:1, request:"<task_id>"}
    2. GET  https://2captcha.com/res.php?action=get&id=<id>  (poll ~5s)
    3. GET  https://2captcha.com/res.php?action=getbalance
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
import urllib.request

IN_URL = "https://2captcha.com/in.php"
RES_URL = "https://2captcha.com/res.php"


class FallbackError(Exception):
    """Fallback gagal (tidak dikonfigurasi, saldo habis, timeout, dll)."""


def _key() -> str:
    k = os.environ.get("TWOCAPTCHA_API_KEY", "").strip()
    if not k:
        raise FallbackError("TWOCAPTCHA_API_KEY tidak diset — fallback nonaktif")
    return k


def enabled() -> bool:
    """Fallback menyala kalau diizinkan eksplisit dan kunci tersedia."""
    if os.environ.get("MIAW_FALLBACK", "0").lower() not in ("1", "true", "yes", "on"):
        return False
    return bool(os.environ.get("TWOCAPTCHA_API_KEY", "").strip())


def _post(url: str, fields: dict[str, str], timeout: int = 60) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("utf-8", "replace").strip()
    if not text:
        raise FallbackError("balasan 2captcha kosong")
    if text.startswith("{"):
        return json.loads(text)
    # format lama: "OK|<token>" atau "ERROR_XXX"
    if text.startswith("OK|"):
        return {"status": 1, "request": text[3:]}
    raise FallbackError(f"2captcha: {text}")


def solve_image_2captcha(image: bytes, *, poll_timeout: int = 120) -> str:
    """Kirim gambar ke 2captcha, tunggu jawaban. Blokir sampai selesai."""
    key = _key()
    b64 = base64.b64encode(image).decode()
    r = _post(IN_URL, {"key": key, "method": "base64", "body": b64, "json": "1"})
    if r.get("status") != 1:
        raise FallbackError(f"2captcha in.php gagal: {r.get('request')}")
    task_id = r["request"]

    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        time.sleep(5)
        params = urllib.parse.urlencode(
            {"key": key, "action": "get", "id": task_id, "json": "1"}
        )
        with urllib.request.urlopen(f"{RES_URL}?{params}", timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8", "replace"))
        if out.get("status") == 1:
            return str(out.get("request", ""))
        if out.get("request") != "CAPCHA_NOT_READY":
            raise FallbackError(f"2captcha res.php: {out.get('request')}")
    raise FallbackError("2captcha timeout menunggu jawaban")


def balance() -> str:
    """Saldo akun 2captcha (dolar, string)."""
    key = _key()
    params = urllib.parse.urlencode({"key": key, "action": "getbalance", "json": "1"})
    with urllib.request.urlopen(f"{RES_URL}?{params}", timeout=30) as resp:
        out = json.loads(resp.read().decode("utf-8", "replace"))
    if out.get("status") != 1:
        raise FallbackError(f"2captcha balance: {out.get('request')}")
    return str(out.get("request", ""))


def solve_image_safe(image: bytes) -> tuple[str, str]:
    """Local-first: coba lokal, kalau gagal baru 2captcha.

    Balikin (jawaban, sumber) dengan sumber in {"local", "2captcha"}.
    """
    from .core import SolverError, solve_image

    try:
        ans = solve_image(image)
        if ans.strip():
            return ans, "local"
    except SolverError:
        pass
    if not enabled():
        raise FallbackError("solver lokal gagal dan fallback 2captcha nonaktif")
    return solve_image_2captcha(image), "2captcha"
