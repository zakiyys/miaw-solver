# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-10-03

First stable release. One core, three doors (library / CLI / HTTP API), CPU-first.

### Added
- **Library API** — `solve_image`, `solve_audio`, `solve_text`, and a unified
  `solve()` dispatcher in `captcha_solver.core`.
- **Audio captcha engine** — offline speech-to-text via `faster-whisper`;
  handles Google's spoken-digit audio challenges (`4 c 7 n` → `4C7N`).
- **Grid captcha engine** — reCAPTCHA v2 (including the audio-challenge
  fallback) and hCaptcha via headless Chromium + Playwright.
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
- **Docker** — multi-stage image with `core`, `grid`, and `gpu` build profiles.
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
