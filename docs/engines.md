# Engines

Four engines, one core. Each is independently usable and independently testable.
Pick the cheapest one that solves your captcha.

| Engine | Input | Solves | Deps | Speed (CPU) |
|---|---|---|---|---|
| `ocr` | image bytes | distorted text (`8f3kd`) | ddddocr | ~50–200 ms |
| `text` | question string | arithmetic / word problems | none | < 1 ms |
| `audio` | audio bytes | spoken digits (`4C7N`) | faster-whisper | ~1–3 s |
| `grid` | page URL + sitekey | reCAPTCHA v2 checkbox path (**experimental** — stops at the challenge) | Playwright + Chromium | ~5–20 s |

> `grid` is the odd one out: it has **no** CLI flag, **no** API parameter, and
> `solve("grid")` raises. It's importable from Python only. hCaptcha is not
> implemented. See its section below before assuming it does anything for you.

## Coverage at a glance

**Supported:** distorted-text images · arithmetic and word questions (EN + ID) ·
spoken audio challenges.

**Experimental, not on any door:** reCAPTCHA v2 — the checkbox is clicked and the
challenge is reached, and that's where it ends.

**Not supported:** reCAPTCHA v3/Enterprise and Cloudflare Turnstile (score-based,
no puzzle to solve) · image-grid selection ("click all buses") · hCaptcha (any
puzzle) · slider/puzzle drag · FunCaptcha/Arkose · GeeTest. All of these need either
a vision model or browser fingerprinting — deliberately out of scope. Use the
2captcha fallback for them.

## GPU

The audio engine is the **only** one that can use a GPU, and it is **not
auto-detected** — the default stays `cpu` even on a CUDA machine. Set
`MIAW_WHISPER_DEVICE=cuda` to enable it; `MIAW_WHISPER_COMPUTE` then defaults to
`float16`. A misconfigured CUDA runtime fails loudly on the first audio solve
(missing `libcublas`/`libcudnn`), not at startup. See the README's *CPU vs GPU*
section for the full checklist.

---

## OCR — distorted image text

Wraps [`ddddocr`](https://github.com/sml2h3/ddddocr), a small CNN trained on
captcha-style text. Pure CPU, no GPU, ~30 MB of weights loaded lazily on first
use.

```python
from captcha_solver import solve_image
print(solve_image(open("captcha.png", "rb").read()))   # -> "8f3kd"
```

**Tuning:** `ddddocr` exposes `set_ranges` for restricted charsets (digits only
is faster and more accurate). Preprocess (grayscale, threshold, denoise) helps
on noisy images; the worker accepts raw bytes and leaves preprocessing to you.

**Fails when:** the image is a *selection grid* ("click all traffic lights") —
that is `grid` territory, not OCR.

---

## Text — arithmetic and word problems

Pure Python, zero dependencies, sub-millisecond. Handles:

- Symbolic: `4+8` → `12`, `7x6` → `42`, `100-58` → `42`, `10 ÷ 2` → `5`
- English words: `seven times six` → `42`, `twenty divided by four` → `5`
- Indonesian words: `tiga tambah lima` → `8`, `dua puluh dibagi empat` → `5`

```python
from captcha_solver import solve_text
print(solve_text("tiga tambah lima"))   # -> "8"
```

**Order matters:** long number phrases (`dua puluh`) are normalised *before*
short ones (`dua`), otherwise `dua puluh` degrades to `2 puluh`. The worker
sorts replacements by length descending.

**Safety:** the evaluator is a hand-written parser over a whitelist of operators
— `eval()` is never called.

---

## Audio — spoken digit challenges

Offline speech-to-text via [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper).
Handles the audio alternative offered by reCAPTCHA v2 and similar schemes.

```python
from captcha_solver import solve_audio
print(solve_audio(open("challenge.wav", "rb").read()))   # -> "4C7N"
```

Model, device, and compute type are env-overridable:

| Variable | Default | Notes |
|---|---|---|
| `MIAW_WHISPER_MODEL` | `base` | `tiny` is ~3× faster, slightly less accurate |
| `MIAW_WHISPER_DEVICE` | `cpu` | `cuda` for GPU |
| `MIAW_WHISPER_COMPUTE` | `int8` (cpu) / `float16` (cuda) | auto-selected |

**Post-processing:** Whisper often returns `"4 c 7 n"` with spaces. The worker
strips spaces and punctuation and keeps only alphanumerics, so the answer matches
the format these challenges expect.

**First call is slow:** the model downloads once (~150 MB for `base`) and is
cached. Subsequent calls reuse the loaded model.

---

## Grid — reCAPTCHA v2 (experimental) and hCaptcha (not implemented)

Driven by headless Chromium via Playwright.

| Capability | Status |
|---|---|
| Open the widget from a real origin, click the checkbox, reach the challenge | **works** — tested 3 Oct 2026 |
| Solve the image challenge ("select all buses") | **not implemented** — needs a vision model, deliberately out of scope |
| Audio-challenge route to a token | **unreliable** — Google frequently answers `Try again later` based on IP reputation, regardless of timing |
| `solve_hcaptcha()` | **raises** — no solving logic exists |
| Reachable from CLI / API / `solve("grid")` | **no** — Python import only |

The code path is:

1. **Checkbox** — render the widget, click the anchor, read `#g-recaptcha-response`.
2. **Audio challenge** — when the checkbox presents an image challenge, switch to the
   audio alternative, download the audio, hand it to the `audio` engine.

```python
import asyncio
from captcha_solver.workers.grid import GridWorker

async def main():
    w = GridWorker(headless=True)
    token = await w.solve_recaptcha_v2(
        pageurl="https://example.com/login",
        sitekey="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI",
    )
    print(len(token))

asyncio.run(main())
```

**Critical gotcha:** reCAPTCHA validates the *origin*. Serving the page with
`page.set_content()` yields an `about:blank` origin and Google answers
**"Invalid domain for site key"**. Always serve the page from a real HTTP origin
(a local server is fine). `scripts/prove_grid.py` demonstrates that setup.

**Cost:** the slowest engine — a browser launch plus a round-trip to Google.

> **Reality check.** `scripts/prove_grid.py` proving a *non-zero token* is not the
> same as solving a real site. Against Google's own demo on 3 Oct 2026 the flow
> stopped at the image challenge — exactly where it's designed to stop. Treat this
> engine as a scaffold for the checkbox path, not as a working reCAPTCHA solver.
> See the README's field notes for the full run.

---

## Choosing an engine

```
is it a text question?          -> text   (free, instant)
is it audio?                    -> audio  (offline, ~2 s)
is it an image with text?       -> ocr    (offline, ~0.1 s)
is it a checkbox / grid widget? -> grid   (browser, ~10 s)
```

When a local engine fails and `MIAW_FALLBACK=1` is set with a key present,
`fallback.solve_image_safe()` forwards to 2captcha. Without that flag the
failure propagates as a `SolverError` — the project never spends money silently.
