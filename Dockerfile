# syntax=docker/dockerfile:1
# CPU-first image. GPU nggak wajib.
#
# Single-stage dengan build arg (bukan multi-stage) — lihat README.
#
# Build:
#   docker build -t miaw-solver .                        # server + audio (default)
#   docker build --build-arg INSTALL_GRID=1 -t miaw-solver:grid .   # + Chromium (berat)
#   docker build --build-arg BASE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 -t miaw-solver:gpu .
#
# Varian GPU WAJIB memakai tag `cudnn-runtime`: ctranslate2 (faster-whisper)
# butuh cuDNN, dan `nvidia/cuda:*-runtime-*` tidak membawanya.
ARG BASE=python:3.11-slim
FROM ${BASE}

# Varian CUDA (ubuntu) belum punya python3 → pasang dulu.
RUN if ! command -v python3 >/dev/null 2>&1; then \
        apt-get update && apt-get install -y --no-install-recommends \
            python3 python3-pip && rm -rf /var/lib/apt/lists/* ; \
    fi

# libgl/libglib → opencv (ddddocr) walau headless. ffmpeg → worker audio.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- dependensi dulu, kode belakangan: cache Docker tetap valid saat kode berubah ---
COPY requirements*.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-server.txt -r requirements-audio.txt

# Grid (opsional, berat): playwright + Chromium.
#
# PLAYWRIGHT_BROWSERS_PATH harus di-set SEBELUM `playwright install`, dan
# direktorinya harus di luar /root: kalau browser terpasang di cache root,
# container yang jalan sebagai user `miaw` tidak akan menemukannya.
ARG INSTALL_GRID=0
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN if [ "$INSTALL_GRID" = "1" ]; then \
        pip install --no-cache-dir -r requirements-grid.txt \
        && playwright install --with-deps chromium \
        && chmod -R a+rX /ms-playwright ; \
    fi

COPY pyproject.toml README.md LICENSE ./
COPY captcha_solver/ ./captcha_solver/
COPY cli.py server.py ./

# Jalankan sebagai non-root. User dibuat setelah instalasi (butuh root).
RUN useradd -m -u 10001 miaw \
    && mkdir -p /home/miaw/.cache \
    && chown -R miaw:miaw /app /home/miaw
USER miaw

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MIAW_WHISPER_MODEL=base \
    HOME=/home/miaw

EXPOSE 8100

# `python3`, bukan `python`: base Ubuntu/CUDA tidak punya alias `python`.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8100/health')"

# Default: API server. CLI: docker run --rm miaw-solver miaw-solve text "4+8"
ENTRYPOINT ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8100"]
