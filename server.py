#!/usr/bin/env python3
"""🚪 Pintu 3 — API server (FastAPI). CPU-first.

Kontrak **kembar 2captcha** biar project lain tinggal ganti base_url:

    2captcha                             miaw-solver (ini)
    ─────────────────────────────────     ──────────────────────────────────────
    POST /in.php  method=post            POST /in   (multipart file)   → {status:1, request:"<id>"}
    POST /in.php  method=base64          POST /in   (json body=b64)    → {status:1, request:"<id>"}
    POST /in.php  method=textcaptcha     POST /in   (textcaptcha=...)  → {status:1, request:"<id>"}
    POST /in.php  method=audio           POST /in   (multipart audio)  → {status:1, request:"<id>"}
    GET  /res.php?action=get&id=         GET  /res?action=get&id=       → {status:1, request:"<answer>"}
    GET  /res.php?action=getbalance      GET  /balance                  → {status:1, request:"0.0"}

Endpoint native (tanpa poll):
    POST /solve        (multipart file=@...)      → solve gambar langsung
    POST /solve/audio  (multipart file=@...)      → solve audio langsung
    POST /solve/text   (form question=...)        → solve tanya-jawab langsung
    GET  /health                                  → status + konfigurasi (tanpa rahasia)
    GET  /stats                                   → hitungan task

Konfigurasi lewat env (lihat .env.example): MIAW_API_KEY, MIAW_RATE_LIMIT,
MIAW_FALLBACK, MIAW_TASK_DB, MIAW_LOG_LEVEL, MIAW_LOG_JSON, MIAW_WORKERS.

Catatan event loop: semua pemanggilan solver dijalankan lewat
``asyncio.to_thread`` supaya solve lambat (audio, fallback 2captcha yang polling
sampai 120 detik) tidak membekukan seluruh server — termasuk ``/health``.
"""
from __future__ import annotations

import asyncio
import base64
import time
import uuid

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from captcha_solver import __version__, solve_audio, solve_image, solve_text
from captcha_solver import fallback as fb
from captcha_solver.config import Config
from captcha_solver.logging_setup import get as get_logger
from captcha_solver.logging_setup import setup as setup_logging
from captcha_solver.store import DONE, ERROR, PENDING, make_store
from captcha_solver.workers.audio import looks_like_audio as _looks_like_audio

CFG = Config.from_env()
setup_logging(CFG.log_level, CFG.log_json)
log = get_logger()

app = FastAPI(title="miaw-solver", version=__version__)

# task store: SQLite kalau MIAW_TASK_DB diset, kalau tidak in-memory.
STORE = make_store(CFG.task_db, ttl=CFG.task_ttl)

# stats
_STATS = {"in": 0, "solve": 0, "ok": 0, "err": 0, "fallback": 0}
_HITS: dict[str, list[float]] = {}


# ---------------------------------------------------------------- middleware

def _api_key_ok(request: Request) -> bool:
    if not CFG.auth_enabled:
        return True
    got = request.headers.get("x-api-key") or request.query_params.get("key") or ""
    return got == CFG.api_key


def _rate_ok(request: Request) -> bool:
    if CFG.rate_limit <= 0:
        return True
    ip = request.client.host if request.client else "?"
    now = time.time()
    hits = [t for t in _HITS.get(ip, []) if now - t < 60]
    if len(hits) >= CFG.rate_limit:
        _HITS[ip] = hits
        return False
    hits.append(now)
    _HITS[ip] = hits
    return True


def _guard(request: Request) -> JSONResponse | None:
    if not _api_key_ok(request):
        log.warning("auth ditolak", extra={"client": request.client.host if request.client else "-"})
        return JSONResponse({"status": 0, "request": "ERROR_WRONG_USER_KEY"}, status_code=401)
    if not _rate_ok(request):
        log.warning("rate limit", extra={"client": request.client.host if request.client else "-"})
        return JSONResponse({"status": 0, "request": "ERROR_TOO_MANY_REQUESTS"}, status_code=429)
    return None


# ------------------------------------------------------------------ worker

async def _process(tid: str, kind: str, payload) -> None:
    """Selesaikan satu tugas di latar belakang, isi hasilnya ke store."""
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


# Jeda poll worker saat antrean kosong. 0.2 s cukup responsif untuk klien yang
# polling tiap ~1-2 detik, tapi tidak membakar CPU saat server sepi.
_POOL_IDLE = 0.2


async def _pool() -> None:
    """Beberapa worker mengambil tugas dari store (biar /in tidak memblokir)."""
    while True:
        task = STORE.claim()
        if not task:
            await asyncio.sleep(_POOL_IDLE)
            continue
        await _process(task["id"], task["kind"], task["payload"])


@app.on_event("startup")
async def _startup() -> None:
    app.state.pool = [asyncio.create_task(_pool()) for _ in range(max(1, CFG.workers))]
    log.info(
        "server siap v%s — workers=%d fallback=%s auth=%s ratelimit=%d store=%s",
        __version__,
        len(app.state.pool),
        CFG.fallback_enabled,
        CFG.auth_enabled,
        CFG.rate_limit,
        "sqlite" if CFG.task_db else "memory",
    )


@app.on_event("shutdown")
async def _shutdown() -> None:
    for t in getattr(app.state, "pool", []):
        t.cancel()


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
        answer, source = await asyncio.to_thread(fb.solve_image_safe, await file.read())
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
        answer = await asyncio.to_thread(solve_audio, await file.read())
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

@app.post("/in")
async def in_endpoint(request: Request) -> JSONResponse:
    """Endpoint kembar 2captcha: terima task, balikin id utk di-poll di /res.

    Tugas diantre; worker latar belakang yang menyelesaikannya, jadi respons
    selalu cepat walau solving-nya butuh detik (audio/grid).
    """
    if (g := _guard(request)) is not None:
        return g
    _STATS["in"] += 1
    ctype = request.headers.get("content-type", "")
    try:
        data = b""
        question = ""
        method = "post"

        if "application/json" in ctype:
            body = await request.json()
            method = str(body.get("method") or "post").lower()
            question = str(body.get("textcaptcha") or body.get("question") or "")
            b64 = body.get("body") or body.get("file") or ""
            if b64:
                data = base64.b64decode(str(b64))
        else:
            form = await request.form()
            method = str(form.get("method") or "post").lower()
            question = str(form.get("textcaptcha") or form.get("question") or "")
            up = form.get("file") or form.get("audio")
            if up is not None and hasattr(up, "read"):
                data = await up.read()

        if method == "textcaptcha" or question:
            tid = STORE.add("text", question)
        elif method == "audio" or (data and _looks_like_audio(data)):
            tid = STORE.add("audio", data)
        elif method in ("post", "base64", "normal", "userrecaptcha") and data:
            tid = STORE.add("image", data)
        else:
            return JSONResponse({"status": 0, "request": "ERROR_WRONG_METHOD"})

        log.info("task masuk", extra={"task_id": tid, "kind": STORE.get(tid)["kind"]})
        return JSONResponse({"status": 1, "request": tid})
    except Exception as e:  # noqa: BLE001
        _STATS["err"] += 1
        log.error("/in gagal", exc_info=True)
        return JSONResponse({"status": 0, "request": f"ERROR: {e}"})


@app.get("/res")
async def res(request: Request, action: str = "get", id: str = Query("")) -> JSONResponse:
    """Poll hasil. Kompatibel 2captcha: CAPCHA_NOT_READY, OK|<answer>, ERROR_*."""
    if CFG.auth_enabled and not _api_key_ok(request):
        return JSONResponse({"status": 0, "request": "ERROR_WRONG_USER_KEY"}, status_code=401)
    if action == "getbalance":
        return JSONResponse({"status": 1, "request": "0.0"})
    if action != "get":
        return JSONResponse({"status": 0, "request": "ERROR_WRONG_ACTION"})

    task = STORE.get(id)
    if task is None:
        return JSONResponse({"status": 0, "request": "CAPCHA_NOT_READY"})
    if task["status"] == ERROR:
        return JSONResponse({"status": 0, "request": f"ERROR: {task['error']}"})
    if task["status"] != DONE:
        return JSONResponse({"status": 0, "request": "CAPCHA_NOT_READY"})
    return JSONResponse({"status": 1, "request": task["answer"]})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=CFG.port)
