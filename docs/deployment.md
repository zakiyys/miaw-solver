# Deployment

## Requirements

| | Minimum | Notes |
|---|---|---|
| CPU | 1 vCPU | `text` engine needs almost nothing |
| RAM | 512 MB | 1 GB if you enable `audio` (Whisper model) |
| Disk | 200 MB | 500 MB with Chromium for `grid` |
| Python | 3.10+ | 3.11/3.12 recommended |
| GPU | none | optional; only speeds up `audio` |

CPU-only is the default and the supported baseline. GPU is a bonus path.

---

## Bare metal / VM

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements-all.txt

# run the API
python -m uvicorn server:app --host 0.0.0.0 --port 8100
```

### systemd unit

```ini
# /etc/systemd/system/miaw-solver.service
[Unit]
Description=Miaw Solver
After=network.target

[Service]
Type=simple
User=miaw
WorkingDirectory=/opt/miaw-solver
EnvironmentFile=/opt/miaw-solver/.env
ExecStart=/opt/miaw-solver/venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8100
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now miaw-solver
curl -s localhost:8100/health
```

---

## Docker

Multi-stage build with three profiles. The default image is CPU-only and does
**not** include Chromium or the Whisper model.

```bash
# core (image + text) — smallest
docker build -t miaw-solver:core .

# + grid (adds Chromium, ~1 GB)
docker build --build-arg INSTALL_GRID=1 -t miaw-solver:grid .

# + GPU base for the audio engine
docker build --build-arg BASE=nvidia/cuda:12.4.1-runtime-ubuntu22.04 \
             -t miaw-solver:gpu .
```

### compose

```bash
docker compose up -d miaw-solver          # core
docker compose --profile grid up -d       # with Chromium
docker compose --profile gpu up -d        # with CUDA
```

The compose file mounts a named volume at `/data` for the SQLite task store, so
queued tasks survive container restarts.

### Healthcheck

The image ships a `HEALTHCHECK` that hits `/health`. Compose waits on it before
marking the service healthy:

```bash
docker inspect --format '{{.State.Health.Status}}' <container>
```

---

## Configuration

Copy `.env.example` to `.env` and edit. Every variable has a safe default —
**an unconfigured instance is local-only, unauthenticated, unlimited, and free.**

| Variable | Default | Purpose |
|---|---|---|
| `MIAW_PORT` | `8100` | listen port |
| `MIAW_API_KEY` | *(unset)* | enable API key auth |
| `MIAW_RATE_LIMIT` | `0` | requests/minute/IP; 0 = unlimited |
| `MIAW_TASK_DB` | *(unset)* | SQLite path; unset = in-memory |
| `MIAW_TASK_TTL` | `300` | seconds before a task is garbage collected |
| `MIAW_WORKERS` | `2` | background solving workers |
| `MIAW_FALLBACK` | `0` | enable 2captcha fallback |
| `TWOCAPTCHA_API_KEY` | *(unset)* | required *with* `MIAW_FALLBACK=1` |
| `MIAW_WHISPER_MODEL` | `base` | `tiny`/`base`/`small` |
| `MIAW_WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `MIAW_WHISPER_COMPUTE` | auto | `int8` on CPU, `float16` on CUDA |
| `MIAW_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `MIAW_LOG_JSON` | `0` | `1` = JSON lines for log aggregators |
| `MIAW_GRID_HEADLESS` | `1` | `0` to watch the browser (debugging) |

### Security notes

- `/health` returns a **redacted** config view — booleans only, never key values.
- The fallback is deliberately double-gated (`MIAW_FALLBACK=1` **and** a key), so
  a stray environment variable can never start billing you silently.
- Secrets are never logged. Answers are logged only at `DEBUG`, truncated.

---

## Reverse proxy

Behind nginx, keep the app on localhost and terminate TLS at the proxy:

```nginx
location /captcha/ {
    proxy_pass http://127.0.0.1:8100/;
    proxy_set_header X-Real-IP $remote_addr;   # required for per-IP rate limiting
    proxy_read_timeout 120s;                    # grid solves are slow
}
```

`X-Real-IP` matters: without it every request appears to come from the proxy and
rate limiting degrades to a single global bucket.

---

## Scaling

- The server is stateless except for the task store. With `MIAW_TASK_DB` on a
  shared volume (or any SQLite-accessible path), you can run several replicas.
- `grid` is the bottleneck — each solve launches a browser. Give grid-heavy
  deployments more RAM, not more CPU.
- `audio` is CPU-bound at ~1–3 s per solve on `base`. `tiny` roughly triples
  throughput at a small accuracy cost.
