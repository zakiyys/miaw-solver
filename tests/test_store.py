"""Uji config + task store — offline, tanpa jaringan."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ------------------------------------------------------------------- config

def test_config_defaults_are_safe(monkeypatch) -> None:
    """Tanpa env apa pun: fallback MATI, auth MATI, rate limit MATI."""
    for k in ("MIAW_FALLBACK", "MIAW_API_KEY", "MIAW_RATE_LIMIT",
              "TWOCAPTCHA_API_KEY", "MIAW_WHISPER_MODEL", "MIAW_TASK_DB"):
        monkeypatch.delenv(k, raising=False)
    from captcha_solver.config import Config

    c = Config.from_env(dotenv=False)
    assert c.fallback is False
    assert c.fallback_enabled is False
    assert c.auth_enabled is False
    assert c.rate_limit == 0
    assert c.whisper_model == "base"
    assert c.whisper_device == "cpu"


def test_config_fallback_needs_both_flags(monkeypatch) -> None:
    """Fallback hanya nyala kalau flag DAN kunci ada — biar nggak diam-diam bayar."""
    from captcha_solver.config import Config

    monkeypatch.setenv("MIAW_FALLBACK", "1")
    monkeypatch.delenv("TWOCAPTCHA_API_KEY", raising=False)
    assert Config.from_env(dotenv=False).fallback_enabled is False

    monkeypatch.setenv("TWOCAPTCHA_API_KEY", "x" * 32)
    assert Config.from_env(dotenv=False).fallback_enabled is True

    monkeypatch.setenv("MIAW_FALLBACK", "0")
    assert Config.from_env(dotenv=False).fallback_enabled is False


def test_config_redacted_never_leaks_secrets(monkeypatch) -> None:
    """redacted() dipakai /health — TIDAK boleh memuat nilai rahasia."""
    from captcha_solver.config import Config

    secret_key = "SUPER-SECRET-2CAPTCHA-KEY"
    api_key = "SUPER-SECRET-API-KEY"
    monkeypatch.setenv("TWOCAPTCHA_API_KEY", secret_key)
    monkeypatch.setenv("MIAW_API_KEY", api_key)
    monkeypatch.setenv("MIAW_FALLBACK", "1")

    blob = repr(Config.from_env(dotenv=False).redacted())
    assert secret_key not in blob
    assert api_key not in blob
    assert "True" in blob  # hanya boolean yang bocor, bukan nilainya


def test_config_cuda_defaults_to_float16(monkeypatch) -> None:
    from captcha_solver.config import Config

    monkeypatch.setenv("MIAW_WHISPER_DEVICE", "cuda")
    monkeypatch.delenv("MIAW_WHISPER_COMPUTE", raising=False)
    assert Config.from_env(dotenv=False).whisper_compute == "float16"


# -------------------------------------------------------------- memory store

def test_memory_store_lifecycle() -> None:
    from captcha_solver.store import DONE, PENDING, make_store

    s = make_store(ttl=60)
    tid = s.add("text", "4+8")
    assert tid and len(tid) == 16

    t = s.get(tid)
    assert t["status"] == PENDING and t["payload"] == "4+8"

    claimed = s.claim()
    assert claimed["id"] == tid and claimed["status"] == "processing"
    # sudah diklaim -> tidak boleh diambil dua kali
    assert s.claim() is None

    s.finish(tid, answer="12")
    assert s.get(tid)["status"] == DONE
    assert s.get(tid)["answer"] == "12"


def test_memory_store_error_and_unknown() -> None:
    from captcha_solver.store import ERROR, make_store

    s = make_store(ttl=60)
    tid = s.add("image", b"x")
    s.finish(tid, error="boom")
    assert s.get(tid)["status"] == ERROR
    assert s.get("nope") is None


def test_memory_store_ttl_expires() -> None:
    from captcha_solver.store import make_store

    s = make_store(ttl=0)
    tid = s.add("text", "1+1")
    time.sleep(0.01)
    assert s.get(tid) is None


# -------------------------------------------------------------- sqlite store

def test_sqlite_store_persists(tmp_path: Path) -> None:
    from captcha_solver.store import DONE, SqliteStore

    db = tmp_path / "tasks.db"
    s1 = SqliteStore(db, ttl=60)
    tid = s1.add("audio", b"RIFF")
    s1.finish(tid, answer="4C7N")

    # instance baru (simulasi restart) harus tetap melihat hasilnya
    s2 = SqliteStore(db, ttl=60)
    row = s2.get(tid)
    assert row["status"] == DONE and row["answer"] == "4C7N"
    assert row["payload"] == b"RIFF"


def test_sqlite_store_claim_is_exclusive(tmp_path: Path) -> None:
    from captcha_solver.store import SqliteStore

    s = SqliteStore(tmp_path / "t.db", ttl=60)
    a = s.add("text", "1")
    s.add("text", "2")
    first = s.claim()
    second = s.claim()
    assert first["id"] == a
    assert second["id"] != first["id"]  # tidak boleh tugas yang sama


def test_store_backend_selection(tmp_path: Path) -> None:
    from captcha_solver.store import MemoryStore, SqliteStore, make_store

    assert isinstance(make_store(), MemoryStore)
    assert isinstance(make_store(str(tmp_path / "x.db")), SqliteStore)


def _main() -> int:
    print("jalankan dengan pytest")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
