# HTTP API

Base URL in the examples: `http://127.0.0.1:8100`. Start the server with:

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8100
# or
docker compose up miaw-solver
```

## Authentication

Off by default. Set `MIAW_API_KEY` to enable; clients then send either:

- header `X-API-Key: <key>`, or
- query parameter `?key=<key>`

A rejected request returns HTTP 401 with `{"status": 0, "request": "ERROR_WRONG_USER_KEY"}`.

## Rate limiting

Off by default (`MIAW_RATE_LIMIT=0`). Set it to a positive integer to allow that
many requests **per minute per IP**. Exceeding it returns HTTP 429 with
`{"status": 0, "request": "ERROR_TOO_MANY_REQUESTS"}`.

---

## Native endpoints

Direct answers, no polling. Best when you control both sides.

### `POST /solve`

Multipart upload, field `file`.

```bash
curl -s -X POST http://127.0.0.1:8100/solve -F "file=@captcha.png"
```

```json
{"status": 1, "request": "8f3kd", "source": "local"}
```

### `POST /solve/audio`

Multipart upload, field `file`.

```bash
curl -s -X POST http://127.0.0.1:8100/solve/audio -F "file=@challenge.wav"
```

```json
{"status": 1, "request": "4C7N", "source": "local"}
```

### `POST /solve/text`

Form field `question`.

```bash
curl -s -X POST http://127.0.0.1:8100/solve/text -F "question=9 x 9"
```

```json
{"status": 1, "request": "81", "source": "local"}
```

### `GET /health`

Never returns secrets — only booleans and non-sensitive values.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "config": {"whisper_model": "base", "fallback": false, "auth": true},
  "engines": ["ddddocr", "rule-text", "faster-whisper"]
}
```

### `GET /stats`

```json
{"status": 1, "request": {"in": 3, "solve": 0, "ok": 3, "err": 0, "fallback": 0},
 "tasks": {"done": 3}}
```

### `GET /balance`

Always `0.0` — solving is local and free. Present for API-shape compatibility.

---

## 2captcha-compatible endpoints

Drop-in replacement: point an existing 2captcha client at this server's base URL
and it works unchanged. Tasks are queued and resolved by background workers, so
`/in` returns immediately even for slow engines.

### `POST /in`

Four input styles, selected by `method`:

| `method` | Body | Example |
|---|---|---|
| `post` | multipart `file` | `-F file=@captcha.png -F method=post` |
| `base64` | JSON `{"method":"base64","body":"<b64>"}` | image as base64 |
| `textcaptcha` | form `textcaptcha=<question>` | `-F method=textcaptcha -F textcaptcha="4+8"` |
| `audio` | multipart `file` (or auto-detected by magic bytes) | `-F file=@challenge.wav` |

Response:

```json
{"status": 1, "request": "ba1c72169d964aef"}
```

The `request` value is the task id to poll. Unknown methods return
`{"status": 0, "request": "ERROR_WRONG_METHOD"}`.

Audio is auto-detected: any upload whose first bytes look like a RIFF/WAV/MP3/OGG
container is routed to the audio engine even without `method=audio`.

### `GET /res` / `GET /res.php`

| Query | Result |
|---|---|
| `?action=get&id=<id>` | `OK\|<answer>` when done, `CAPCHA_NOT_READY` while pending |
| `?action=getbalance` | `OK\|0.0` |

Add `&json=1` to get `{"status":1,"request":"..."}` instead of plain text.

Polling example:

```bash
ID=$(curl -s -X POST "http://127.0.0.1:8100/in.php?key=$KEY" -F "file=@captcha.png" \
      | cut -d'|' -f2)

while :; do
  R=$(curl -s "http://127.0.0.1:8100/res.php?key=$KEY&action=get&id=$ID")
  case "$R" in *CAPCHA_NOT_READY*) sleep 1 ;; *) echo "$R"; break ;; esac
done
```

Errors follow 2captcha conventions:

| Response | Meaning |
|---|---|
| `CAPCHA_NOT_READY` | still queued or processing |
| `ERROR_WRONG_CAPTCHA_ID` | id unknown or expired — **stop polling** |
| `ERROR_CAPTCHA_UNSOLVABLE` | the engine failed on this captcha |
| `ERROR_WRONG_USER_KEY` | auth failed (HTTP 401) |
| `ERROR_TOO_MANY_REQUESTS` | rate limited (HTTP 429) |
| `ERROR_TOO_BIG_CAPTCHA_FILESIZE` | upload over `MIAW_MAX_UPLOAD_MB` |
| `ERROR_METHOD_NOT_SUPPORTED` | e.g. `method=userrecaptcha` — needs a vision model |
| `ERROR_WRONG_METHOD` | method not recognised / no payload |

---

## Migrating an existing 2captcha client

Only the base URL changes:

```diff
- base_url = "https://2captcha.com"
+ base_url = "http://your-miaw-solver:8100"
```

`/in.php` and `/res.php` are served natively and answer in 2captcha's own wire
format (`OK|<value>`, `CAPCHA_NOT_READY`, `ERROR_*`). Add `json=1` if you would
rather have JSON. `/in` and `/res` are kept as JSON-only aliases for clients
written against earlier versions.

The API key is accepted from `X-API-Key`, `?key=`, or a `key` field in the
form/JSON body — so a stock 2captcha client that posts `key=...` works unchanged.

### Methods that are **not** supported

`userrecaptcha`, `hcaptcha`, `turnstile`, `geetest`, `funcaptcha`, `coordinates`
and similar need a vision model or a third-party solver. They are rejected with
`ERROR_METHOD_NOT_SUPPORTED` instead of being silently misread as an image
captcha. Use 2captcha itself for those (the built-in fallback only covers image
captchas).

## Task store

| `MIAW_TASK_DB` | Behaviour |
|---|---|
| unset | in-memory — fast, lost on restart |
| path (e.g. `/data/tasks.db`) | SQLite with WAL — survives restarts, safe across processes |

Tasks expire after `MIAW_TASK_TTL` seconds (default 300) and are garbage
collected on each access. On startup, tasks left in `processing` by a crash are
returned to `pending` so a fresh worker picks them up.
