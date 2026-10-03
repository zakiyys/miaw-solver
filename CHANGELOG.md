# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] — 2026-10-03

Audit fixes. No new capability — this release is about the server not lying to
its clients, and the text engine not guessing.

### Fixed
- **Server blocked the entire event loop.** `_process`, `/solve`, `/solve/audio`
  and `/solve/text` called the solver synchronously inside coroutines, so one
  slow solve (audio, or a 2captcha fallback polling up to 120 s) froze `/health`
  too, and `MIAW_WORKERS` bought no parallelism. All solver calls now go through
  `asyncio.to_thread`; model loading is guarded by `threading.Lock` so two
  threads can't load the same model twice. Measured: `/health` answers in
  **4.2 ms** (limit 300 ms) while a 2 s solve is running; two slow tasks with
  `MIAW_WORKERS=2` finish in **2.26 s** (limit 3 s; the blocking version took
  4.20 s).
- **`/in.php` and `/res.php` returned 404.** A stock 2captcha client could not
  talk to the server at all. Both routes now exist and share the handler.
- **API key in the request body was rejected with 401.** The body is now parsed
  before auth; the key is accepted from `X-API-Key`, the `key` query parameter,
  or a `key` field in form/JSON body, and compared with `hmac.compare_digest`.
- **Unknown or expired task id answered `CAPCHA_NOT_READY`,** which makes a
  polling client wait forever. It now answers `ERROR_WRONG_CAPTCHA_ID`.
- **Audio worker leaked a temp file per solve** — `_as_path` wrote a named temp
  file and never removed it (finally-block deletion, on a path with concurrent
  workers, is the classic race). The worker now hands `io.BytesIO` straight to
  the model, so no temp file exists.
- **`looks_like_audio` treated WebP as audio.** WebP uses the same `RIFF`
  container as WAV, so a WebP image passed the magic-byte check and was shipped
  to the speech model. WAV now requires `bytes[8:12] == b"WAVE"`, and bare MP3
  (no ID3 tag, frame sync `0xFF` + `(b[1] & 0xE0) == 0xE0`) is detected too.
- **`scripts/prove_grid.py` reimplemented the Playwright flow** instead of
  calling the real worker, so the proof could pass while the shipped code was
  broken. It now calls `GridWorker.solve_recaptcha_v2`.
- **Dead config.** `Config.grid_headless` existed but was never read — it is now
  actually passed to `solve_recaptcha_v2`; the unused `pageurl` parameter on
  `_launch` is gone.
- **Docker: Chromium was installed as root with the container running as
  `miaw`,** so the browser could not be found at runtime.
  `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` is now set before `playwright
  install` and the directory is made readable by `miaw`.
- **Docker: `HEALTHCHECK` called `python`,** which does not exist in the Ubuntu
  and CUDA base images. Switched to `python3`.
- **Docker: GPU variant lacked cuDNN.** The base image was
  `nvidia/cuda:12.4.1-runtime-ubuntu22.04`, which ships no cuDNN, so
  `ctranslate2` (faster-whisper) would fail to import. Switched to the matching
  `cudnn-runtime` variant.

### Changed
- **`/res.php` behaviour change (breaking for lenient clients).** `.php` paths
  now follow the 2captcha wire format by default: plain text (`OK|<id>`,
  `OK|<answer>`, `CAPCHA_NOT_READY`, `ERROR_...`), with JSON only when `json=1`
  is passed. `/in` and `/res` keep returning JSON unconditionally, so existing
  callers of the native endpoints are unaffected. Clients that relied on
  `/res.php` returning JSON must add `json=1` or parse the text.
- **Text engine no longer guesses (behaviour change).** Previously the first
  number that happened to appear was returned (`"Enter the digits 4 7 1"` →
  `4`), and when no number was present the question itself was echoed back as
  the answer. Now a question with no recognisable arithmetic expression raises,
  which `core.solve_text` wraps as `SolverError`. Digit run-together is also no
  longer summed: `"Enter the digits 4 7 1"` used to become `12`. Word-numbers
  are only merged when they came *from* word conversion, so `"4 7 1"` stays
  three digits while `"one hundred twenty five"` still becomes `125`. A
  side effect: `"forty two"` (a number with no operator) is now an error rather
  than `42` — a captcha showing a digit string wants it retyped, not added up.
  This is the README's "silence beats a confident wrong answer" principle.
- **`x` only means multiply between digits.** A global `str.replace("x", "*")`
  corrupted any word containing an `x` (`box`, `six`); the substitution is now
  anchored between digits. `ast.Pow` was dropped from the operator table — it
  was unreachable, and `9**9**9` would be a CPU bomb if it ever became
  reachable.
- **Unknown engine name errors were misleading.** `solve("grid")` said "unknown
  type" and `register_engine("grid")` said "built-in engines cannot be
  overridden" — both false, since no grid engine is built in. `grid` is now a
  *reserved* name with an honest message pointing at
  `captcha_solver.workers.grid`, and reserved names are rejected when
  registered.
- **`SqliteStore` recovers from a crash on startup** — tasks left in
  `processing` are returned to `pending` in `__init__`, so a killed process no
  longer strands its queue. Connections are closed with
  `contextlib.closing`.
- **Worker pool idle sleep 0.05 s → 0.2 s** — the tight poll burned CPU for no
  latency win on a task set measured in seconds.
- **Docker image tag in `docker-compose.yml`** was still `0.2.0`; it now tracks
  the released version.
- **README:** grid rows moved out of the "Supported" table into a new
  "Experimental (tidak tersambung ke CLI/API)" section that states plainly that
  only Google's test sitekey has been proven and that hCaptcha is not
  implemented. The Dockerfile is described as single-stage with build args, not
  multi-stage. Build backend corrected from `hatchling` to `setuptools`; test
  counts and the per-file table refreshed (84 tests).
- **Upload cap** is configurable via `MIAW_MAX_UPLOAD_MB` (default 10);
  exceeding it returns `ERROR_TOO_BIG_CAPTCHA_FILESIZE`.

### Notes
- `Development Status :: 3 - Alpha` is kept deliberately and is now explained in
  the README: the public API is frozen, but engine coverage is narrow. The
  roadmap's "stable" referred to API stability, not product completeness; the
  wording was corrected to avoid the contradiction.
- **Untested in this release:** the GPU image variant (no GPU host available),
  and grid against a real site (Google's test sitekey only). Both are marked in
  the README.

## [1.0.0] — 2026-10-03

First stable release. One core, three doors (library / CLI / HTTP API), CPU-first.

### Added
- **Library API** — `solve_image`, `solve_audio`, `solve_text`, and a unified
  `solve()` dispatcher in `captcha_solver.core`.
- **Audio captcha engine** — offline speech-to-text via `faster-whisper`;
  handles Google's spoken-digit audio challenges (`4 c 7 n` → `4C7N`).
- **Grid captcha engine** — *experimental, not wired to the CLI or API.*
  reCAPTCHA v2 via headless Chromium + Playwright: the widget is driven from a
  real origin and the checkbox is clicked, but the solve stops at the image
  challenge. The audio-challenge fallback exists and is unreliable in practice
  (Google frequently answers `Try again later` based on IP reputation).
  **hCaptcha is not implemented** — `solve_hcaptcha()` raises. Reachable only by
  importing `captcha_solver.workers.grid` from Python.
- **Text / question engine** — arithmetic and word problems with word-number
  normalisation in English and Indonesian (`tiga tambah lima` → `8`).
- **2captcha-compatible HTTP contract** — `/in` (post, base64, textcaptcha,
  audio) and `/res` (`get`, `getbalance`) so existing integrations only need a
  `base_url` change.
- **Native HTTP endpoints** — `/solve`, `/solve/audio`, `/solve/text`, plus
  `/health`, `/stats`, `/balance`.
- **Task store** — in-memory by default; SQLite (WAL) for persistence across
  restarts, with TTL garbage collection and exclusive claim semantics.
- **Optional 2captcha fallback** — off by default, enabled only when
  `MIAW_FALLBACK=1` *and* a key is present.
- **API key auth** and **per-IP rate limiting**, both off by default.
- **Structured logging** — human-readable text or JSON, with secret redaction.
- **Centralised configuration** in `captcha_solver/config.py`, with a
  `redacted()` view safe to expose on `/health`.
- **Docker** — single-stage image (build args, not stages) with `core`, `grid`,
  and `gpu` build profiles.
- **CI/CD** — test matrix on GitHub Actions (CPU-only) and a release workflow
  producing a wheel plus a GHCR image.
- **Documentation** — `docs/` (engines, API, deployment), `examples/`, and this
  changelog.

### Security
- Secrets are never logged and never returned by `/health`.
- All scripts are portable — no absolute paths, hostnames, or IPs in the tree.

## [0.2.0] — 2026-10-03

### Added
- Audio worker (`faster-whisper`), 2captcha fallback module, grid worker
  scaffolding, config module, task store, structured logging, Docker files,
  and CI workflows.
- Test coverage expanded from 3 to 30 tests.

### Fixed
- Relative import in `fallback.py` (`from ..core` → `from .core`).
- Word-number normalisation ordering (`dua puluh` was becoming `2 puluh`).
- reCAPTCHA rejects `about:blank`; the widget must be served from a real HTTP
  origin.

## [0.1.0] — 2026-10-03

### Added
- Initial release: OCR engine (`ddddocr`), rule-based text engine, CLI
  (`miaw-solve`), and a minimal FastAPI server.

[1.0.0]: https://github.com/zakiyys/miaw-solver/releases/tag/v1.0.0
[0.2.0]: https://github.com/zakiyys/miaw-solver/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/zakiyys/miaw-solver/releases/tag/v0.1.0
