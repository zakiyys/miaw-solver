# Miaw Solver (Captcha Solver)

**Self-hosted CAPTCHA solver — CPU-first.** No GPU required, no per-solve cost.

[![CI](https://github.com/zakiyys/miaw-solver/actions/workflows/ci.yml/badge.svg)](https://github.com/zakiyys/miaw-solver/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CPU-first](https://img.shields.io/badge/CPU--first-yes-green.svg)](#cpu-vs-gpu)

> **Miaw Solver** — one core, three interfaces: **Library · CLI · API Server**.
> The API is a **drop-in replacement for 2captcha** — just change `base_url` and you're done.

![Miaw Solver — distorted squiggle in, clean text out, plain CPU, no GPU needed](assets/blotcat-hero-banner.png)

---

## What it solves — and what it doesn't

Be honest up front, so you don't deploy it expecting magic.

### ✅ Supported

| CAPTCHA type | How | Distinguishes |
|---|---|---|
| **Image / distorted text** | `ddddocr` CNN | the classic squiggly-text image |
| **Simple arithmetic / word question** | rule engine + safe arithmetic | "7 x 6 = ?", "tiga tambah lima" |
| **Audio / spoken challenge** | `faster-whisper` offline STT | reCAPTCHA's "listen" alternative |

### 🧪 Experimental — not wired to the CLI or the API

Reachable only by importing `captcha_solver.workers.grid` from Python.

| CAPTCHA type | What actually works | What doesn't |
|---|---|---|
| **reCAPTCHA v2 (checkbox)** | Browser opens the widget from a real origin, clicks the checkbox, and reaches the challenge. **Proven only against Google's official test sitekey**, which passes with no challenge at all. | On a real site it stops at the image challenge ("select all buses"). The audio route is frequently refused with `Try again later` based on IP reputation. No vision model, no fingerprint spoofing — by design. |
| **hCaptcha** | Nothing. `solve_hcaptcha()` raises. | Not implemented. There is no hCaptcha code path beyond the raise. |

> `solve("grid")` raises with an explanation. There is no CLI flag and no API
> parameter for it. Tested 3 Oct 2026; see
> [field notes](#field-notes-real-captchas-3-oct-2026).

### ❌ Not supported

| CAPTCHA type | Why not | Workaround |
|---|---|---|
| **reCAPTCHA v3 / Enterprise** | score-based, no challenge to solve — needs fingerprinting + residential proxies | 2captcha fallback |
| **Cloudflare Turnstile** | same: proof-of-work + fingerprint, not a puzzle | 2captcha fallback |
| **Image-grid tiles** ("select all buses") | needs an object-detection/vision model — deliberately out of scope for a CPU-first, no-GPU project | 2captcha fallback |
| **hCaptcha (any puzzle)** | `solve_hcaptcha()` raises by design — the widget flow above reaches the challenge but nothing solves the tiles | 2captcha fallback |
| **Sliders / puzzle-piece drag** | needs behavioural simulation + a vision model | 2captcha fallback |
| **FunCaptcha / Arkose** | proprietary, needs a full browser farm | — |
| **GeeTest v3/v4** | proprietary JS + behavioural scoring | 2captcha fallback |
| **Bot-detection gates generally** | out of scope — this is a *captcha solver*, not an anti-bot bypass toolkit | — |

**Not going to happen, by design.** No vision model, no stealth/anti-fingerprinting
patches, no proxy rotation. Those three are what "solve harder captchas" would
actually require, and each one turns this project into something else. If you need
them, 2captcha is a *service* that already does it — which is exactly why the
optional fallback exists.

**The honest summary:** this tool reliably nails the *cheap* 80% — text images,
arithmetic, and audio. The remaining 20% needs a **vision model over a selection
grid** or **browser fingerprinting**, both out of scope. reCAPTCHA v2 sits on the
line: the browser plumbing is real, but without one of those two it stays stuck at
the challenge. That's exactly why the optional
2captcha fallback exists: local-first for the easy stuff, one line of config to
hand the hard stuff off.


---

## Documentation

| Doc | Contents |
|---|---|
| [docs/engines.md](docs/engines.md) | How each of the four engines works, its cost, its limits |
| [docs/api.md](docs/api.md) | HTTP reference — native endpoints + 2captcha-compatible contract |
| [docs/deployment.md](docs/deployment.md) | systemd, Docker, config table, reverse proxy, scaling |
| [examples/](examples/) | Runnable library, CLI, curl, and custom-engine examples |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Ground rules, setup, how to add an engine |


---

## Proof it works

Real output, nothing hand-waved. Every line below is a command result.

### Text CAPTCHA

```console
$ miaw-solve text "7 x 6"
42
$ miaw-solve text "tiga tambah lima"
8
$ miaw-solve text "dua puluh dibagi empat"
5
```

Works in Indonesian and English, with digits or spelled-out numbers.

### Image CAPTCHA (ddddocr)

The fixture is a **synthetic** captcha generated for this repo — no real site's
captcha is bundled, so you can reproduce everything yourself:

![Synthetic distorted-text CAPTCHA showing 8f3kd — noise lines and salt-and-pepper dots](docs/img/image-captcha-input.png)

*Input (shown at 3× so you can read it): distorted text `8f3kd` with intersecting
noise lines and salt-and-pepper dots.*

```console
$ miaw-solve image testdata/captcha_like.png
8f3kd

$ wc -c < testdata/captcha_like.png
9670
```

Full command output, so nothing is hidden:

```console
$ miaw-solve image testdata/captcha_like.png; echo "exit=$?"
8f3kd
exit=0
```

Regenerate or roll your own fixture with the `captcha` package — the worker takes
raw image bytes and doesn't care where they came from.

### Audio CAPTCHA (faster-whisper)

```console
$ miaw-solve audio testdata/audio_4c7n.wav
4C7N
```

The fixture was synthesized as `"4 c 7 n"` and comes back as `4C7N` — ~1–2 s on CPU.
You can regenerate the fixture yourself with `scripts/make_audio_fixture.py`.

> No image for this one — audio is a waveform, not something a screenshot conveys.
> The command output above *is* the proof.

### reCAPTCHA v2 (headless Chromium)

Against Google's official v2 test sitekey, the grid route renders the widget and
collects a token — proof the browser flow is wired correctly:

```console
$ python scripts/prove_grid.py
=== bukti GridWorker: reCAPTCHA v2 test-key ===
  origin        : http://127.0.0.1:33557/
  widget        : ter-render OK ('This reCAPTCHA is for testing purposes only...')
  token length  : 1742
  token sample  : '0cAFcWeA4YP8VycCt5tyljlVX42_tMQr6127SN7u'
  HASIL         : OK jalur grid berfungsi (token didapat)
```

Reproduce it yourself with `python scripts/prove_grid.py`. The **token length
varies between runs** (observed 1700–1742 chars) — what matters is that it is
non-empty, which is the difference between a working widget and Google rejecting
your origin.

> Two field notes worth having, both learned the hard way:
> **(1)** reCAPTCHA rejects the `about:blank` origin — a widget rendered with
> `page.set_content()` shows *"ERROR for site owner: Invalid domain for site key"*
> instead of a checkbox. It must be served from a real `http(s)` origin, so the
> worker spins up a tiny local HTTP server. **(2)** the widget needs ~1.5 s to
> settle; clicking too early times out.

### Against real, live CAPTCHAs — field test

The test-key proof above shows the wiring works. It does **not** show what happens
against a production site. So we ran that too, and recorded the exact stopping
point. Reproduce with `python scripts/test_real_grid.py`.

```console
>>> Google official reCAPTCHA v2 demo  (google.com/recaptcha/api2/demo)
    1. halaman terbuka      : HTTP 200 (275 ms)
    2. widget ter-render    : iframe anchor ditemukan
    3. cek pesan            : ok — "I'm not a robot reCAPTCHA"
    4. checkbox diklik      : ok
    5. token                : kosong
    6. tantangan            : GAMBAR muncul — 'Select all images with a bus'
    => BERHENTI DI TANTANGAN GAMBAR (butuh model vision)
```

Read that honestly: the browser flow is correct — page loads, widget renders,
checkbox clicks. The wall is the **image challenge**, which needs a vision model.
The audio detour was attempted too (`scripts/test_real_recaptcha_audio.py`) and
Google answered **"Try again later"**, its standard soft block for datacenter-ish
IP reputation. Neither is a bug in this repo; both are documented ceilings.

The engines that *do* run standalone were measured against real CAPTCHAs pulled
from the [ddddocr](https://github.com/sml2h3/ddddocr) sample set:

| Real CAPTCHA | Truth | Our answer | Result |
|---|---|---|---|
| `yzm1.png` — distorted alphanumeric | `3n3D` | `3n3d` | ✅ correct (case-insensitive) |
| `yzm2.jpeg` — Chinese click-order puzzle | *not a text task* | `''` | ✅ correctly **declined** |

The second row is the interesting one: a puzzle CAPTCHA is outside the OCR
engine's contract, and it returns empty rather than guessing. Silence beats a
confident wrong answer.

Text engine, including multi-word numbers in both languages:

```console
$ miaw-solve text "one hundred minus twenty five"   →  75
$ miaw-solve text "dua ratus lima puluh dibagi lima" →  50
$ miaw-solve text "one thousand minus one"           →  999
$ miaw-solve text "sembilan belas tambah satu"       →  20
```

> This last group is a **regression fix found by the field test, not by unit
> tests**. The original word-number table stopped at `dua puluh` / `seratus` and
> had no `hundred`/`thousand`, so `one hundred minus twenty five` parsed as `1`.
> Fixed in `captcha_solver/workers/text.py`; regression cases added to
> `tests/test_core.py`.

### API (2captcha-compatible)

```console
$ curl -X POST http://localhost:8100/solve -F "file=@captcha.png"
{"status":1,"request":"8f3kd","source":"local"}

$ curl -X POST http://localhost:8100/solve/text -F "question=7 x 6"
{"status":1,"request":"42","source":"local"}

$ curl -X POST http://localhost:8100/solve/audio -F "file=@challenge.wav"
{"status":1,"request":"4C7N","source":"local"}
```

Full 2captcha mirror also verified — `method=post`, `method=base64`,
`method=textcaptcha`, and auto-detected audio, each followed by `/res?action=get`:

```console
$ curl -X POST http://localhost:8100/in -F "file=@captcha.png" -F "method=post"
{"status":1,"request":"9853a3b6b613445f"}
$ curl "http://localhost:8100/res?action=get&id=9853a3b6b613445f"
{"status":1,"request":"8f3kd"}
```

### The `.php` paths behave like 2captcha

`/in.php` and `/res.php` are aliases for `/in` and `/res`, but they follow
2captcha's **wire format**: plain text by default, JSON only on request.

```console
$ curl -X POST localhost:8100/in.php -F "file=@captcha.png" -F "method=post" -F "key=$KEY"
OK|9853a3b6b613445f

$ curl "localhost:8100/res.php?key=$KEY&action=get&id=9853a3b6b613445f"
OK|8f3kd

$ curl -X POST "localhost:8100/in.php?json=1" -F "file=@captcha.png" -F "method=post" -F "key=$KEY"
{"status":1,"request":"9853a3b6b613445f"}
```

The key may arrive as `X-API-Key` header, a `key` query parameter, **or** a `key`
field in the form/JSON body — 2captcha sends it in the body, so the body has to be
read before the key can be checked.

Error strings follow 2captcha:

| Situation | `.php` body | `/in`, `/res` JSON |
|---|---|---|
| unknown or expired id | `ERROR_WRONG_CAPTCHA_ID` | `{"status":0,"request":"ERROR_WRONG_CAPTCHA_ID"}` |
| still queued | `CAPCHA_NOT_READY` | `{"status":0,"request":"CAPCHA_NOT_READY"}` |
| solve failed | `ERROR_CAPTCHA_UNSOLVABLE` | `{"status":0,"request":"ERROR_CAPTCHA_UNSOLVABLE"}` |
| upload over `MIAW_MAX_UPLOAD_MB` | `ERROR_TOO_BIG_CAPTCHA_FILESIZE` | same string in JSON |
| bad/missing key | `ERROR_WRONG_USER_KEY` (HTTP 401) | same string in JSON |
| `method=userrecaptcha` etc. | `ERROR_METHOD_NOT_SUPPORTED` | same string in JSON |

> An unknown id returns `ERROR_WRONG_CAPTCHA_ID`, **not** `CAPCHA_NOT_READY`.
> Reporting a missing id as "not ready" makes polling clients wait forever.

Methods that need a vision model or a third-party solver — `userrecaptcha`,
`hcaptcha`, `turnstile`, `geetest`, `funcaptcha`, `coordinates`, and friends —
are rejected explicitly instead of being silently treated as an image captcha.

### Event loop

Every solve runs in a worker thread (`asyncio.to_thread`), so a slow solve — audio,
or the 2captcha fallback that polls for up to 120 s — never freezes the server.
Measured with the solver stubbed to `time.sleep(2)`:

```console
/in.php returned in        13.1 ms
/health while task running  2.9 ms      # before the fix: waited the full 2 s
2 tasks @ 2 s, MIAW_WORKERS=2  2.25 s   # serial would be ~4 s
```

### Auth & rate limiting

Both verified, not just claimed:

```console
$ curl -o /dev/null -w "%{http_code}" -X POST localhost:8100/solve -F "file=@x.png"
401                          # no API key while MIAW_API_KEY is set
$ curl -o /dev/null -w "%{http_code}" -H "X-API-Key: <your-key>" \
    -X POST localhost:8100/solve/text -F "question=1+1"
200 200 429 429 429          # MIAW_RATE_LIMIT=3 → the 4th request is throttled
```

### Tests

```console
$ pytest tests/
49 passed in 2.91s
```

49 tests, CPU-only, no network in the default suite. CI runs them on Python
3.10 / 3.11 / 3.12 **plus** a Docker job that boots the image and smoke-tests the API.

---

## Quick start

### 1. CLI

```bash
pip install .
miaw-solve image captcha.png       # image  → "8f3kd"
miaw-solve text "What is 7 x 6 ?"   # text   → "42"
miaw-solve audio challenge.wav      # audio  → "4C7N"
cat captcha.png | miaw-solve image -   # read from stdin
```

Optional extras:

```bash
pip install ".[audio]"   # audio CAPTCHA   (faster-whisper)
pip install ".[grid]"    # reCAPTCHA v2    (playwright + chromium)
pip install ".[all]"     # everything
playwright install chromium            # once, only if you installed [grid]
```

### 2. Library

```python
from captcha_solver import solve_image, solve_text, solve_audio, solve

print(solve_image("captcha.png"))                 # → "8f3kd"
print(solve_text("Berapa hasil dari 4 + 8 ?"))    # → "12"
print(solve_audio("challenge.wav"))               # → "4C7N"

# or route by type once you know it
print(solve("text", "9 x 9"))                     # → "81"
```

### 3. API server (2captcha-compatible — one-line switch)

```bash
docker compose up -d                        # listens on :8100
curl -X POST http://localhost:8100/solve -F "file=@captcha.png"
# → {"status":1,"request":"8f3kd","source":"local"}
```

**Already using 2captcha?**

```diff
- base_url = "https://2captcha.com"
+ base_url = "http://localhost:8100"
```

Done. No more per-solve fees.

### Docker

```bash
docker compose up -d                      # CPU, server + audio
docker compose --profile grid up -d       # + Chromium for reCAPTCHA v2
docker compose --profile gpu up -d        # + CUDA (needs nvidia-container-toolkit)
```

Copy `.env.example` → `.env` to set the optional knobs (see [Configuration](#configuration)).

---

## 2captcha compatibility table

| 2captcha endpoint | Miaw Solver |
|---|---|
| `POST /in.php` `method=post` | `POST /in.php` or `/in` (multipart `file`) → `OK\|<task_id>` / JSON |
| `POST /in.php` `method=base64` | same (JSON `{"method":"base64","body":"...","key":"..."}`) |
| `POST /in.php` `method=textcaptcha` | same (form `textcaptcha=...`) |
| `POST /in.php` `method=audio` | same (multipart `file`, audio auto-detected by magic bytes) |
| `POST /in.php` `method=userrecaptcha` | **not supported** → `ERROR_METHOD_NOT_SUPPORTED` |
| `GET /res.php?action=get&id=` | `GET /res.php` or `/res` → `OK\|<answer>` / JSON |
| `GET /res.php?action=getbalance` | `GET /balance` → `OK\|0.0` / JSON |
| *(not in 2captcha)* | `POST /solve` — answer immediately, no polling |
| *(not in 2captcha)* | `POST /solve/text`, `POST /solve/audio` |
| *(not in 2captcha)* | `GET /health`, `GET /stats` |

The `.php` paths answer in 2captcha's own wire format (plain text, JSON with
`?json=1`); `/in` and `/res` always answer JSON so existing clients keep working.
An unknown or expired id returns `ERROR_WRONG_CAPTCHA_ID` — not
`CAPCHA_NOT_READY`, which would make a polling client wait forever.

---

## Configuration

All optional — with no configuration the solver just runs locally and free.

| Env var | Default | Meaning |
|---|---|---|
| `MIAW_FALLBACK` | `0` | `1` = when the local solver fails, forward images to 2captcha (**paid**) |
| `TWOCAPTCHA_API_KEY` | — | required for the fallback to work |
| `MIAW_API_KEY` | — | if set, every endpoint except `/health` needs `X-API-Key` (or `?key=`) |
| `MIAW_RATE_LIMIT` | `0` | max requests/minute per IP; `0` = unlimited |
| `MIAW_WHISPER_MODEL` | `base` | `tiny` (fast) · `base` (balanced) · `small` (accurate) |
| `MIAW_WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `MIAW_WHISPER_COMPUTE` | `int8` (`float16` on CUDA) | CTranslate2 compute type |
| `MIAW_PORT` | `8100` | host port for docker compose |

The fallback is **off by default on purpose** — a solver that silently spends money
is a bug, not a feature.

### Security

- `/health` is intentionally unauthenticated (containers need it for healthchecks).
- Rate limiting is per IP and deliberately simple; put it behind a reverse proxy
  if you expose it to the internet.
- With `MIAW_API_KEY` unset the API is **open**. Never expose it publicly like that.

---

## Dependencies

Keep the footprint honest: the **core** is tiny and pure-CPU; audio and grid are opt-in
extras, so a plain install never drags in a speech model or a browser engine.

### Core — required (image + text)

| Package | Version used | Why it's here |
|---|---|---|
| [`ddddocr`](https://github.com/sml2h3/ddddocr) | `1.6.1` | The OCR engine for distorted-text images. Ships its own ONNX model (~12 MB) inside the wheel and runs on CPU via `onnxruntime`. **Pinned** — its API and bundled model change between releases. |
| [`pillow`](https://python-pillow.org/) | `>=10` | Image decoding. Brought in for preprocessing and to normalise any input format before OCR. |
| [`numpy`](https://numpy.org/) | `>=1.24` | Array plumbing underneath ddddocr/opencv. Declared explicitly so the version floor is honest. |

Transitive (pulled in automatically, no action needed): `onnxruntime` (~1.30),
`opencv-python-headless` (~5.0) — the headless build matters, it avoids requiring a
display on a server.

### Extra: `server` — the API door

| Package | Version used | Why |
|---|---|---|
| `fastapi` | `>=0.110` | The HTTP layer. Async, and its `UploadFile` handles multipart without extra glue. |
| `uvicorn[standard]` | `>=0.27` | ASGI server. The `[standard]` variant pulls in the fast C parsers/websocket bits. |
| `python-multipart` | `>=0.0.9` | Required by FastAPI to parse `multipart/form-data` — i.e. every image upload. Easy to forget; the server 422s without it. |

### Extra: `audio` — speech CAPTCHA

| Package | Version used | Why |
|---|---|---|
| [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) | `>=1.0` (1.2.1 tested) | Speech-to-text via CTranslate2 — several times faster than the reference Whisper on the same CPU, which is why it's the audio engine here. |

Transitive: `ctranslate2` (~4.8, the actual inference runtime), `tokenizers`,
`huggingface-hub` (model download). The `base` model (~75 MB) is fetched **once** on
first audio use, then cached — mount a volume for it in Docker so restarts don't
re-download.

### Extra: `grid` — reCAPTCHA v2 (experimental)

| Package | Version used | Why |
|---|---|---|
| [`playwright`](https://playwright.dev/python/) | `>=1.40` (1.63.0 tested) | Drives a real headless Chromium to reach the audio challenge. Heavier than everything else — kept behind an extra so it's never installed by accident. |

This extra buys you a **browser**, not a working reCAPTCHA solver. What it does:
opens the widget from a real origin, clicks the checkbox, and reaches the
challenge. What it doesn't: solve the image challenge, or get past an IP-reputation
block on the audio route. hCaptcha is not implemented at all.

Plus the browser binary itself: `playwright install chromium` (~170 MB). Not a Python
dependency, so it can't be declared in `pyproject.toml` — you install it once.

### System packages (Docker image only)

`libgl1`, `libglib2.0-0` (needed by opencv even in headless mode) and `ffmpeg`
(decodes any audio format the client sends). All handled by the provided `Dockerfile`.

### Deliberate non-dependencies

- **No PyTorch.** ddddocr speaks ONNX and faster-whisper speaks CTranslate2, so the
  multi-GB torch install is avoided entirely — that is what keeps the CPU image small.
- **No `requests`.** HTTP calls to 2captcha use the standard library (`urllib`), so the
  core has zero HTTP dependencies.
- **No cloud calls by default.** Nothing leaves the machine unless you explicitly set
  `MIAW_FALLBACK=1`.

Install size guide: core ≈ 200 MB, `+server` ≈ +40 MB, `+audio` ≈ +150 MB (plus the
75 MB model on first run), `+grid` ≈ +170 MB of browser.

### Test tooling

| Package | Version used | Why |
|---|---|---|
| `pytest` | `>=8` (9.1.1 tested) | The test runner. All tests are offline and deterministic. |
| `hatchling` | build backend | Declared as `build-system` in `pyproject.toml`; no manual install needed. |

---

## Project layout

```text
miaw-solver/
├── captcha_solver/          # the package (import name stays `captcha_solver`)
│   ├── __init__.py          #   public API + __version__
│   ├── core.py              #   the brain — solve_image / solve_text / solve_audio / solve
│   ├── config.py            #   every knob in one place, env-driven, redacted() view
│   ├── store.py             #   task queue — MemoryStore / SqliteStore
│   ├── logging_setup.py     #   text or JSON logs, secret-safe
│   ├── fallback.py          #   optional 2captcha safety net (opt-in, double-gated)
│   ├── cli.py               #   🚪 door 1 — `miaw-solve`
│   └── workers/
│       ├── ocr.py           #   🧩 image → ddddocr
│       ├── text.py          #   🧩 text  → rules + safe arithmetic
│       ├── audio.py         #   🧩 audio → faster-whisper
│       └── grid.py          #   🧩 grid  → Playwright (reCAPTCHA v2 / hCaptcha)
├── server.py                # 🚪 door 3 — FastAPI, 2captcha-compatible
├── cli.py                   # thin shim for `python cli.py`
├── docs/                    # engines · api · deployment
├── examples/                # runnable library / CLI / curl / custom-engine samples
├── tests/                   # offline suite (core · store · grid · plugins)
├── testdata/                # small fixtures used by tests and examples
├── scripts/                 # dev-only helpers (generate fixtures, live grid proof)
├── assets/                  # README banners
├── Dockerfile               # multi-stage: core / grid / gpu
└── docker-compose.yml       # profiles: default · grid · gpu
```

Library is door 2 — there is no separate directory for it: `import captcha_solver`
*is* the library, and the CLI and server are both thin wrappers over it.

### Extension point

Add your own engine without touching the core:

```python
from captcha_solver import register_engine, solve

register_engine("roman", lambda q: str(roman_to_int(q)))
solve("roman", "XIV")          # -> "14"
```

Built-in engine names cannot be overridden, so a stray registration can never
silently change default behaviour. See `examples/custom_engine.py`.


---

## Architecture

```text
captcha_solver/
├── core.py              # the brain — solve_image / solve_text / solve_audio / solve
├── fallback.py          # optional 2captcha safety net (local-first)
├── cli.py               # 🚪 entry point: miaw-solve
└── workers/
    ├── ocr.py           # 🧩 image   → ddddocr
    ├── text.py          # 🧩 text    → rules + safe AST arithmetic
    ├── audio.py         # 🧩 audio   → faster-whisper
    └── grid.py          # 🧩 grid    → Playwright (reCAPTCHA v2 audio route)
server.py                # 🚪 FastAPI server, 2captcha-compatible
tests/                   # test suite (runs on CPU-only CI)
```

**Design rule:** all solving logic lives in `captcha_solver/` (the library).
The CLI and API server are thin wrappers — never put logic in them.

![One core, three doors — library, CLI and API all lead to the same engine](assets/blotcat-architecture-banner.png)

### Lazy loading

`import captcha_solver` stays light. Heavy models (ddddocr's ONNX graph, the
whisper weights, Chromium) are only loaded when a door actually asks for that
captcha type. The core holds one singleton per worker, created on first use.

---

## CPU vs GPU

Default is CPU-only, and that is the point: the test suite runs on free CI runners
and the Docker image has no CUDA dependency. A GPU is a **turbo option**, not a
requirement — it only speeds up the **audio** engine. Nothing else uses it.

### ⚠️ GPU is NOT auto-detected — you must turn it on

The default is `cpu` and it stays `cpu` until you say otherwise. Even on a machine
with a perfectly good CUDA card, this project will quietly run on CPU. That is
deliberate (predictable behaviour, no surprise VRAM use), but it means **a GPU does
nothing until you configure it.** Verified behaviour:

```console
$ python -c "from captcha_solver.config import Config; c=Config.from_env(dotenv=False); print(c.whisper_device, c.whisper_compute)"
cpu int8        # <- on a machine that HAS a CUDA GPU

$ MIAW_WHISPER_DEVICE=cuda python -c "from captcha_solver.config import Config; c=Config.from_env(dotenv=False); print(c.whisper_device, c.whisper_compute)"
cuda float16    # <- only after you ask
```

### To enable GPU, do all four things

1. **Have a working CUDA runtime.** `ctranslate2` needs the CUDA libraries
   (cuBLAS + cuDNN) matching your build. Check what your install actually supports
   **before** assuming:
   ```bash
   python -c "import ctranslate2; print(ctranslate2.get_supported_compute_types('cuda'))"
   # this machine, ctranslate2 4.8.2, CPU-only build: {'float32', 'int8_float32', 'int8'}
   # a CUDA-enabled build additionally reports float16 / int8_float16
   ```
   ⚠️ **Note:** if `float16` is *not* in that set, your CUDA libs are missing or the
   wrong version. Set `MIAW_WHISPER_DEVICE=cuda` and pin
   `MIAW_WHISPER_COMPUTE=float32` or `int8_float32` instead of relying on the
   `float16` default.
2. **Set the device:**
   ```bash
   export MIAW_WHISPER_DEVICE=cuda
   ```
3. **Choose a compute type.** Setting `cuda` makes the *default* `float16`, but
   faster-whisper only accepts a type the runtime reports as supported (see step 1).
   Override with one that is:
   ```bash
   export MIAW_WHISPER_COMPUTE=float16      # fastest, ~half VRAM — needs matching CUDA libs
   # export MIAW_WHISPER_COMPUTE=int8_float16  # least VRAM
   # export MIAW_WHISPER_COMPUTE=int8_float32  # good middle ground
   # export MIAW_WHISPER_COMPUTE=float32       # most accurate, slowest
   ```
4. **Give the container the GPU** if you're on Docker — the `gpu` profile already
   does this via the `nvidia` runtime:
   ```bash
   docker compose --profile gpu up -d
   ```

Verify it actually took effect — `/health` reports the live config:

```bash
curl -s localhost:8100/health | python3 -m json.tool | grep -E 'device|compute'
```

### If CUDA is misconfigured

You get a loud error on the **first audio solve**, not at startup — the model is
loaded lazily. Typical failure is a missing `libcublas.so.12` or
`libcudnn.so.9`. Fix the library, or just unset the variable and fall back to CPU;
nothing else in the project depends on the GPU.

### What actually gets faster

| Engine | GPU benefit |
|---|---|
| `audio` (faster-whisper) | **yes** — roughly 3–5× on `base`, more on `small` |
| `image` (ddddocr / ONNX) | no — CPU is already ~50–150 ms |
| `text` (pure Python) | no — microseconds either way |
| `grid` (Chromium) | no — it's network + page-render bound |

> Bottom line: **skip the GPU unless you're doing high-volume audio solving.**
> For everything else it's dead weight, and the CPU path is the one CI actually tests.


---

## Tests

```bash
pytest tests/                    # 49 tests, offline, deterministic
pytest tests/ -v                 # verbose
pytest tests/test_core.py -q     # a single file
python scripts/prove_grid.py     # live grid check (needs network + Chromium)
```

| File | Tests | Covers |
|---|---|---|
| `tests/test_core.py` | 15 | the public API — image, text, audio, routing, errors |
| `tests/test_store.py` | 12 | memory + SQLite stores, TTL, exclusive claim, crash recovery, `redacted()` |
| `tests/test_grid.py` | 5 | grid URL/sitekey handling, audio detection |
| `tests/test_plugins.py` | 11 | `register_engine` — naming, overrides, error wrapping |
| `tests/test_concurrency.py` | 6 | `_load_*` must not double-load models across threads |
| `tests/test_server_loop.py` | 3 | the event loop stays responsive while a solve runs |
| `tests/test_server.py` | 15 | auth, 2captcha wire format, upload cap, unknown ids (needs `fastapi` + `httpx`) |

`tests/test_server*.py` skip automatically when `fastapi`/`httpx` aren't installed,
so the plain `pytest tests/` run stays dependency-light.

CI runs on GitHub Actions across Python 3.10 / 3.11 / 3.12 — **CPU-only runners**,
which proves the project needs no GPU — plus a Docker job that boots the image,
waits for `/health`, and checks an API response.

---

## Roadmap

**Shipped:**

- **v0.1** — core + CLI + library + API (image & text) ✅
- **v0.2** — audio (faster-whisper), 2captcha fallback, auth + rate limit, Docker ✅
- **v0.3** — grid worker scaffold: reCAPTCHA v2 *experimental* (reaches the challenge, then stops; not on any door) · hCaptcha not implemented at all ✅
- **v0.4** — SQLite task store, structured logging, config module ✅
- **v1.0** — stable API, full docs, published wheel + GHCR image ✅
- **v1.0.1** — non-blocking server, real 2captcha compatibility ✅ **(current)**

<p align="center"><code>v1.0.1</code></p>

**Possible next steps (no promises):**

- Metrics endpoint (Prometheus format) alongside `/stats`
- Webhook callbacks so clients don't have to poll `/res`
- More languages in the text engine
- **Not** on this list: vision models, stealth patches, proxy rotation. Those are
  what the reCAPTCHA v2 path would need to go from "reaches the challenge" to
  "solves it" — and they'd break the CPU-first, no-fingerprinting promise. If you
  want them, point the fallback at 2captcha.

---

## License

MIT — see [LICENSE](LICENSE).
