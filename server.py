#!/usr/bin/env python3
"""🚪 Pintu 3 — API server (FastAPI). CPU-first.

Kontrak **kembar 2captcha** biar project lain tinggal ganti base_url:

    2captcha                             miaw-solver (ini)
    ─────────────────────────────────     ──────────────────────────────────────
    POST /in.php  method=post            POST /in.php | /in  (multipart file)
    POST /in.php  method=base64          POST /in.php | /in  (json body=b64)
    POST /in.php  method=textcaptcha     POST /in.php | /in  (textcaptcha=...)
    POST /in.php  method=audio           POST /in.php | /in  (multipart audio)
    GET  /res.php?action=get&id=         GET  /res.php | /res?action=get&id=
    GET  /res.php?action=getbalance      GET  /balance

Format respons (lihat `_reply`):
    - Path `.php`   → teks polos 2captcha: ``OK|<id>``, ``OK|<jawaban>``,
      ``CAPCHA_NOT_READY``, ``ERROR_*``. Tambahkan ``json=1`` untuk JSON.
    - Path /in, /res → selalu JSON ``{"status":1,"request":"..."}`` (tidak breaking).

Kunci API diterima dari header ``X-API-Key``, query ``?key=``, atau field ``key``
di form/JSON body (2captcha menaruh key di body). Dibandingkan dengan
``hmac.compare_digest``.

Endpoint native (tanpa poll):
    POST /solve        (multipart file=@...)      → solve gambar langsung
    POST /solve/audio  (multipart file=@...)      → solve audio langsung
    POST /solve/text   (form question=...)        → solve tanya-jawab langsung
    GET  /health                                  → status + konfigurasi (tanpa rahasia)
    GET  /stats                                   → hitungan task

Konfigurasi lewat env (lihat .env.example): MIAW_API_KEY, MIAW_RATE_LIMIT,
MIAW_FALLBACK, MIAW_TASK_DB, MIAW_LOG_LEVEL, MIAW_LOG_JSON, MIAW_WORKERS,
MIAW_MAX_UPLOAD_MB.

Catatan event loop: semua pemanggilan solver dijalankan lewat
``asyncio.to_thread`` supaya solve lambat (audio, fallback 2captcha yang polling
sampai 120 detik) tidak membekukan seluruh server — termasuk ``/health``.
"""
from __future__ import annotations

import asyncio
import base64
import hmac
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from captcha_solver import __version__, solve_audio, solve_text
from captcha_solver import fallback as fb
from captcha_solver.config import Config
from captcha_solver.logging_setup import get as get_logger
from captcha_solver.logging_setup import setup as setup_logging
from captcha_solver.store import DONE, ERROR, PENDING, make_store
from captcha_solver.workers.audio import looks_like_audio as _looks_like_audio

CFG = Config.from_env()
setup_logging(CFG.log_level, CFG.log_json)
log = get_logger()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Nyalakan worker saat start, matikan saat shutdown."""
    app.state.pool = [asyncio.create_task(_pool()) for _ in range(max(1, CFG.workers))]
    log.info(
        "server siap v%s — workers=%d fallback=%s auth=%s ratelimit=%d store=%s",
        __version__, len(app.state.pool), CFG.fallback_enabled, CFG.auth_enabled,
        CFG.rate_limit, "sqlite" if CFG.task_db else "memory",
    )
    try:
        yield
    finally:
        for t in app.state.pool:
            t.cancel()


app = FastAPI(title="miaw-solver", version=__version__, lifespan=_lifespan)

# task store: SQLite kalau MIAW_TASK_DB diset, kalau tidak in-memory.
STORE = make_store(CFG.task_db, ttl=CFG.task_ttl)

# stats
_STATS = {"in": 0, "solve": 0, "ok": 0, "err": 0, "fallback": 0}
_HITS: dict[str, list[float]] = {}
_HITS_SWEEP_AT = 1024          # ambang pembersihan global (lihat _rate_ok)

# Metode 2captcha yang butuh model visi / solver pihak ketiga. Kita tolak dengan
# jelas daripada diam-diam memperlakukannya sebagai captcha gambar.
_UNSUPPORTED_METHODS = frozenset({
    "userrecaptcha", "recaptcha", "hcaptcha", "turnstile",
    "geetest", "funcaptcha", "coordinates", "grid", "lemin",
})

# Jeda poll worker saat antrean kosong. 0.2 s cukup responsif untuk klien yang
# polling tiap ~1-2 detik, tapi tidak membakar CPU saat server sepi.
_POOL_IDLE = 0.2


# --------------------------------------------------------------- rendering

def _is_php(request: Request) -> bool:
    """True kalau request lewat path bergaya 2captcha (`/in.php`, `/res.php`)."""
    return request.url.path.endswith(".php")


def _wants_json(request: Request) -> bool:
    return request.query_params.get("json", "").lower() in ("1", "true", "yes", "on")


def _reply(request: Request, *, ok: bool, value: str, http: int = 200) -> Response:
    """Render balasan sesuai konvensi path.

    Path `.php` mengikuti 2captcha (teks polos) kecuali `json=1`; path `/in` dan
    `/res` selalu JSON supaya klien lama tidak rusak.
    """
    if _is_php(request) and not _wants_json(request):
        return PlainTextResponse(f"OK|{value}" if ok else value, status_code=http)
    return JSONResponse({"status": 1 if ok else 0, "request": value}, status_code=http)


# ---------------------------------------------------------------- middleware

def _api_key_ok(request: Request, body_key: str | None = None) -> bool:
    """Terima key dari header, query, atau body (urutan itu)."""
    if not CFG.auth_enabled:
        return True
    got = (
        request.headers.get("x-api-key")
        or request.query_params.get("key")
        or body_key
        or ""
    )
    # compare_digest: bandingkan waktu tetap, hindari bocor lewat timing.
    return hmac.compare_digest(got, CFG.api_key)


def _rate_ok(request: Request) -> bool:
    if CFG.rate_limit <= 0:
        return True
    ip = request.client.host if request.client else "?"
    now = time.time()
    hits = [t for t in _HITS.get(ip, []) if now - t < 60]

    # IP tanpa hit aktif tidak perlu disimpan — kalau dibiarkan, _HITS tumbuh
    # tanpa batas seiring banyaknya IP yang pernah lewat.
    if not hits:
        _HITS.pop(ip, None)

    if len(hits) >= CFG.rate_limit:
        _HITS[ip] = hits
        return False
    hits.append(now)
    _HITS[ip] = hits

    # Bersihkan sisa IP yang sudah kedaluwarsa kalau tabelnya membengkak.
    if len(_HITS) > _HITS_SWEEP_AT:
        for k in [k for k, v in _HITS.items() if not [t for t in v if now - t < 60]]:
            _HITS.pop(k, None)
    return True


def _guard(request: Request, *, body_key: str | None = None,
           rate: bool = True) -> Response | None:
    if not _api_key_ok(request, body_key):
        log.warning("auth ditolak", extra={"client": request.client.host if request.client else "-"})
        return _reply(request, ok=False, value="ERROR_WRONG_USER_KEY", http=401)
    if rate and not _rate_ok(request):
        log.warning("rate limit", extra={"client": request.client.host if request.client else "-"})
        return _reply(request, ok=False, value="ERROR_TOO_MANY_REQUESTS", http=429)
    return None


# ------------------------------------------------------------------ unggahan

def _limit_bytes() -> int:
    """Batas ukuran unggahan dalam byte (0 = tanpa batas)."""
    return max(0, CFG.max_upload_mb) * 1024 * 1024


def _too_big(data: bytes) -> bool:
    limit = _limit_bytes()
    return bool(limit) and len(data) > limit


async def _read_capped(up: UploadFile) -> bytes:
    """Baca unggahan tapi jangan pernah lebih dari limit+1 byte.

    Sengaja dibatasi saat baca: tanpa ini, unggahan raksasa masuk ke RAM dulu
    baru ditolak.
    """
    limit = _limit_bytes()
    return await up.read(limit + 1) if limit else await up.read()


# ------------------------------------------------------------------ worker

async def _process(tid: str, kind: str, payload) -> None:
    """Selesaikan satu tugas di latar belakang, isi hasilnya ke store.

    Solver dijalankan di thread terpisah (`asyncio.to_thread`) supaya tugas
    lambat tidak memblokir event loop.
    """
    t0 = time.perf_counter()
    try:
        if kind == "text":
            answer, source = await asyncio.to_thread(solve_text, payload), "local"
        elif kind == "audio":
            answer, source = await asyncio.to_thread(solve_audio, payload), "local"
        else:
            answer, source = await asyncio.to_thread(fb.solve_image_safe, payload)
        STORE.finish(tid, answer=answer)
        _STATS["ok"] += 1
        if source == "2captcha":
            _STATS["fallback"] += 1
        ms = int((time.perf_counter() - t0) * 1000)
        log.info("selesai", extra={"task_id": tid, "kind": kind, "source": source, "ms": ms})
    except Exception as e:  # noqa: BLE001
        STORE.finish(tid, error=str(e))
        _STATS["err"] += 1
        log.error("gagal", extra={"task_id": tid, "kind": kind}, exc_info=True)


async def _pool() -> None:
    """Beberapa worker mengambil tugas dari store (biar /in tidak memblokir)."""
    while True:
        task = STORE.claim()
        if not task:
            # 0.2 s: cukup responsif, tapi tidak membakar CPU saat sepi.
            await asyncio.sleep(_POOL_IDLE)
            continue
        await _process(task["id"], task["kind"], task["payload"])


# ------------------------------------------------------------------ meta

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "config": CFG.redacted(),
            "engines": ["ddddocr", "rule-text", "faster-whisper"]}


@app.get("/stats")
def stats() -> dict:
    return {"status": 1, "request": dict(_STATS), "tasks": STORE.stats()}


@app.get("/balance")
def balance() -> dict:
    """Selalu 0 — lokal, gratis."""
    return {"status": 1, "request": "0.0"}


# -------------------------------------------------------------- native doors

@app.post("/solve")
async def solve(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """Endpoint native: langsung balikin jawaban, tanpa poll."""
    if (g := _guard(request)) is not None:
        return g
    _STATS["solve"] += 1
    t0 = time.perf_counter()
    try:
        data = await _read_capped(file)
        if _too_big(data):
            _STATS["err"] += 1
            return JSONResponse({"status": 0, "request": "ERROR_TOO_BIG_CAPTCHA_FILESIZE"})
        answer, source = await asyncio.to_thread(fb.solve_image_safe, data)
        if source == "2captcha":
            _STATS["fallback"] += 1
        _STATS["ok"] += 1
        log.info("solve gambar", extra={"source": source,
                                        "ms": int((time.perf_counter() - t0) * 1000)})
        return JSONResponse({"status": 1, "request": answer, "source": source})
    except Exception as e:  # noqa: BLE001
        _STATS["err"] += 1
        log.error("solve gambar gagal", exc_info=True)
        return JSONResponse({"status": 0, "request": f"ERROR: {e}"})


@app.post("/solve/audio")
async def solve_audio_door(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    if (g := _guard(request)) is not None:
        return g
    _STATS["solve"] += 1
    t0 = time.perf_counter()
    try:
        data = await _read_capped(file)
        if _too_big(data):
            _STATS["err"] += 1
            return JSONResponse({"status": 0, "request": "ERROR_TOO_BIG_CAPTCHA_FILESIZE"})
        answer = await asyncio.to_thread(solve_audio, data)
        _STATS["ok"] += 1
        log.info("solve audio", extra={"source": "local",
                                       "ms": int((time.perf_counter() - t0) * 1000)})
        return JSONResponse({"status": 1, "request": answer, "source": "local"})
    except Exception as e:  # noqa: BLE001
        _STATS["err"] += 1
        log.error("solve audio gagal", exc_info=True)
        return JSONResponse({"status": 0, "request": f"ERROR: {e}"})


@app.post("/solve/text")
async def solve_text_door(request: Request, question: str = Form(...)) -> JSONResponse:
    if (g := _guard(request)) is not None:
        return g
    _STATS["solve"] += 1
    try:
        answer = await asyncio.to_thread(solve_text, question)
        _STATS["ok"] += 1
        return JSONResponse({"status": 1, "request": answer, "source": "local"})
    except Exception as e:  # noqa: BLE001
        _STATS["err"] += 1
        return JSONResponse({"status": 0, "request": f"ERROR: {e}"})


# ----------------------------------------------------------- 2captcha mirror

async def _parse_in_body(request: Request) -> tuple[bytes, str, str, str]:
    """Baca body `/in` apa pun bentuknya.

    Returns:
        (data, question, method, key) — `data` kosong untuk textcaptcha.
    """
    ctype = request.headers.get("content-type", "")
    data = b""
    question = ""
    method = "post"
    key = ""

    if "application/json" in ctype:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 — body rusak = body kosong
            body = {}
        if not isinstance(body, dict):
            body = {}
        method = str(body.get("method") or "post").lower()
        question = str(body.get("textcaptcha") or body.get("question") or "")
        key = str(body.get("key") or "")
        b64 = body.get("body") or body.get("file") or ""
        if b64:
            data = base64.b64decode(str(b64))
    else:
        form = await request.form()
        method = str(form.get("method") or "post").lower()
        question = str(form.get("textcaptcha") or form.get("question") or "")
        key = str(form.get("key") or "")
        up = form.get("file") or form.get("audio")
        if up is not None and hasattr(up, "read"):
            data = await _read_capped(up)

    return data, question, method, key


@app.post("/in")
@app.post("/in.php")
async def in_endpoint(request: Request) -> Response:
    """Endpoint kembar 2captcha: terima task, balikin id utk di-poll di /res.

    Tugas diantre; worker latar belakang yang menyelesaikannya, jadi respons
    selalu cepat walau solving-nya butuh detik (audio/grid).

    Body di-parse lebih dulu karena 2captcha mengirim `key` di dalam body.
    """
    _STATS["in"] += 1
    try:
        data, question, method, key = await _parse_in_body(request)
    except Exception:  # noqa: BLE001
        _STATS["err"] += 1
        log.error("/in body gagal dibaca", exc_info=True)
        return _reply(request, ok=False, value="ERROR_BAD_REQUEST")

    if (g := _guard(request, body_key=key)) is not None:
        return g

    if method in _UNSUPPORTED_METHODS:
        _STATS["err"] += 1
        log.info("metode tidak didukung", extra={"method": method})
        return _reply(request, ok=False, value="ERROR_METHOD_NOT_SUPPORTED")

    if _too_big(data):
        _STATS["err"] += 1
        return _reply(request, ok=False, value="ERROR_TOO_BIG_CAPTCHA_FILESIZE")

    try:
        if method == "textcaptcha" or question:
            tid = STORE.add("text", question)
        elif method == "audio" or (data and _looks_like_audio(data)):
            tid = STORE.add("audio", data)
        elif method in ("post", "base64", "normal") and data:
            tid = STORE.add("image", data)
        else:
            return _reply(request, ok=False, value="ERROR_WRONG_METHOD")

        log.info("task masuk", extra={"task_id": tid, "kind": STORE.get(tid)["kind"]})
        return _reply(request, ok=True, value=tid)
    except Exception as e:  # noqa: BLE001
        _STATS["err"] += 1
        log.error("/in gagal", exc_info=True)
        return _reply(request, ok=False, value=f"ERROR: {e}")


@app.get("/res")
@app.get("/res.php")
async def res(request: Request, action: str = "get", id: str = Query("")) -> Response:
    """Poll hasil. Kompatibel 2captcha: CAPCHA_NOT_READY, OK|<answer>, ERROR_*.

    Tanpa rate limit: klien 2captcha memang polling berkali-kali sampai selesai.
    """
    if (g := _guard(request, rate=False)) is not None:
        return g
    if action == "getbalance":
        return _reply(request, ok=True, value="0.0")
    if action != "get":
        return _reply(request, ok=False, value="ERROR_WRONG_ACTION")

    task = STORE.get(id)
    if task is None:
        # Id ngawur / kedaluwarsa: bilang terus terang, jangan CAPCHA_NOT_READY
        # — klien yang polling akan menunggu selamanya.
        return _reply(request, ok=False, value="ERROR_WRONG_CAPTCHA_ID")
    if task["status"] == ERROR:
        log.warning("task gagal", extra={"task_id": id})
        return _reply(request, ok=False, value="ERROR_CAPTCHA_UNSOLVABLE")
    if task["status"] != DONE:
        return _reply(request, ok=False, value="CAPCHA_NOT_READY")
    return _reply(request, ok=True, value=task["answer"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=CFG.port)
