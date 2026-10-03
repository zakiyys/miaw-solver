"""Konfigurasi terpusat — satu tempat untuk semua knob.

Semua nilai punya default yang aman: tanpa konfigurasi apa pun, solver jalan
lokal dan gratis. Env var menimpa default; file .env (kalau ada) dimuat lebih
dulu supaya `docker compose` dan penggunaan lokal konsisten.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_TRUTHY = ("1", "true", "yes", "on")


def load_dotenv(path: str | Path = ".env") -> None:
    """Muat .env sederhana (KEY=VALUE) tanpa dependensi tambahan.

    Tidak menimpa env var yang sudah diset — shell selalu menang.
    """
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    v = _env(name)
    if not v:
        return default
    return v.lower() in _TRUTHY


@dataclass
class Config:
    """Konfigurasi runtime Miaw Solver."""

    # --- audio ---
    whisper_model: str = field(default_factory=lambda: _env("MIAW_WHISPER_MODEL", "base"))
    whisper_device: str = field(default_factory=lambda: _env("MIAW_WHISPER_DEVICE", "cpu"))
    whisper_compute: str = field(
        default_factory=lambda: _env(
            "MIAW_WHISPER_COMPUTE",
            "float16" if _env("MIAW_WHISPER_DEVICE", "cpu") == "cuda" else "int8",
        )
    )

    # --- fallback 2captcha ---
    fallback: bool = field(default_factory=lambda: _env_bool("MIAW_FALLBACK", False))
    twocaptcha_key: str = field(default_factory=lambda: _env("TWOCAPTCHA_API_KEY"))

    # --- keamanan API ---
    api_key: str = field(default_factory=lambda: _env("MIAW_API_KEY"))
    rate_limit: int = field(default_factory=lambda: _env_int("MIAW_RATE_LIMIT", 0))
    port: int = field(default_factory=lambda: _env_int("MIAW_PORT", 8100))

    # --- task store ---
    task_db: str = field(default_factory=lambda: _env("MIAW_TASK_DB", ""))
    task_ttl: int = field(default_factory=lambda: _env_int("MIAW_TASK_TTL", 300))
    workers: int = field(default_factory=lambda: _env_int("MIAW_WORKERS", 2))

    # --- grid ---
    grid_headless: bool = field(default_factory=lambda: _env_bool("MIAW_GRID_HEADLESS", True))

    # --- logging ---
    log_level: str = field(default_factory=lambda: _env("MIAW_LOG_LEVEL", "INFO").upper())
    log_json: bool = field(default_factory=lambda: _env_bool("MIAW_LOG_JSON", False))

    @classmethod
    def from_env(cls, dotenv: bool = True) -> Config:
        if dotenv:
            load_dotenv()
        return cls()

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def fallback_enabled(self) -> bool:
        return self.fallback and bool(self.twocaptcha_key)

    def redacted(self) -> dict:
        """Representasi aman untuk /health — TIDAK pernah memuat nilai rahasia."""
        return {
            "whisper_model": self.whisper_model,
            "whisper_device": self.whisper_device,
            "fallback": self.fallback_enabled,
            "auth": self.auth_enabled,
            "rate_limit": self.rate_limit,
            "task_db": bool(self.task_db),
            "workers": self.workers,
            "grid_headless": self.grid_headless,
            "log_level": self.log_level,
        }
