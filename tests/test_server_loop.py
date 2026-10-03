"""Test bagian A — server tidak boleh memblokir event loop.

Memakai route `/in` yang sudah ada (JSON), bukan `/in.php`, supaya test ini
tetap bermakna walau bagian B belum dikerjakan.

Butuh fastapi + httpx + python-multipart. Kalau salah satunya tidak ada
(mis. matrix CI "core"), modul di-skip — bukan gagal.
"""
from __future__ import annotations

import base64
import importlib
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")          # python-multipart

from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API_KEY = "kunci-uji-123"
# PNG 1x1 transparan — cukup sebagai payload unggahan.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture()
def srv(monkeypatch):
    """Import ulang server.py dengan env uji, lalu kembalikan modulnya."""
    monkeypatch.setenv("MIAW_API_KEY", API_KEY)
    monkeypatch.setenv("MIAW_WORKERS", "2")
    monkeypatch.setenv("MIAW_RATE_LIMIT", "0")
    monkeypatch.delenv("MIAW_TASK_DB", raising=False)   # in-memory: offline, cepat
    import server
    importlib.reload(server)
    yield server


def _antre(client: TestClient, nama: str = "a.png") -> str:
    """Kirim satu tugas gambar lewat /in, balikin id-nya."""
    r = client.post(f"/in?key={API_KEY}",
                    files={"file": (nama, PNG_1PX, "image/png")},
                    data={"method": "post"})
    assert r.status_code == 200, r.text
    return r.json()["request"]


def _tunggu(client: TestClient, tid: str, *, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/res?key={API_KEY}&action=get&id={tid}").json()
        if body.get("status") == 1:
            return body
        if "NOT_READY" not in str(body.get("request", "")):
            return body
        time.sleep(0.1)
    raise AssertionError(f"task {tid} tidak selesai dalam {timeout}s")


def test_health_tidak_diblokir_saat_solve_lambat(srv, monkeypatch):
    """Solve 2 detik di latar tidak boleh membekukan /health.

    Sebelum perbaikan, solver sync dipanggil langsung di dalam coroutine →
    event loop beku → /health ikut menunggu sampai solve selesai.
    """
    def slow(_data):
        time.sleep(2.0)
        return "8f3kd", "local"

    monkeypatch.setattr(srv.fb, "solve_image_safe", slow)

    with TestClient(srv.app) as client:
        tid = _antre(client)
        assert tid

        # Tugas masih berjalan di latar — /health harus tetap instan.
        t0 = time.perf_counter()
        h = client.get("/health")
        dt = time.perf_counter() - t0

        assert h.status_code == 200
        assert dt < 0.3, f"/health butuh {dt:.3f}s — event loop terblokir"

        # Dan tugasnya tetap selesai dengan benar.
        assert _tunggu(client, tid)["request"] == "8f3kd"


def test_dua_tugas_lambat_paralel(srv, monkeypatch):
    """MIAW_WORKERS=2 → dua tugas 2 detik selesai < 3 detik (serial butuh ~4)."""
    def slow(_data):
        time.sleep(2.0)
        return "8f3kd", "local"

    monkeypatch.setattr(srv.fb, "solve_image_safe", slow)

    with TestClient(srv.app) as client:
        ids = [_antre(client, f"a{i}.png") for i in range(2)]

        t0 = time.perf_counter()
        for tid in ids:
            assert _tunggu(client, tid, timeout=10)["status"] == 1
        dt = time.perf_counter() - t0

    assert dt < 3.0, f"dua tugas 2 s selesai dalam {dt:.2f}s — tidak paralel"


def test_workers_dihormati(srv):
    """MIAW_WORKERS=2 → dua task pool hidup."""
    with TestClient(srv.app) as client:
        client.get("/health")
        assert len(srv.app.state.pool) == 2
