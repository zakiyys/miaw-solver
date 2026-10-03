"""Test server API — event loop, kompatibilitas 2captcha, auth.

Butuh fastapi + httpx + python-multipart. Kalau salah satunya tidak ada
(mis. di matrix CI "core"), seluruh modul di-skip — bukan gagal.
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


def _wait_done(client: TestClient, tid: str, *, timeout: float = 20.0) -> str:
    """Poll /res sampai selesai. Balikin body mentah."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get("/res.php", params={"key": API_KEY, "action": "get", "id": tid})
        if not r.text.startswith("CAPCHA_NOT_READY"):
            return r.text
        time.sleep(0.2)
    raise AssertionError(f"task {tid} tidak selesai dalam {timeout}s")


# ------------------------------------------------------------------ A. loop

def test_health_tidak_diblokir_saat_solve_lambat(srv, monkeypatch):
    """Solve 2 detik di latar tidak boleh membekukan /health.

    Sebelum perbaikan, solver sync dipanggil langsung di dalam coroutine →
    event loop beku → /health ikut nunggu.
    """
    def slow(_data):
        time.sleep(2.0)
        return "8f3kd", "local"

    monkeypatch.setattr(srv.fb, "solve_image_safe", slow)

    with TestClient(srv.app) as client:
        r = client.post("/in.php",
                        files={"file": ("a.png", PNG_1PX, "image/png")},
                        data={"key": API_KEY, "method": "post"})
        assert r.status_code == 200, r.text

        # Tugas masih jalan di latar — /health harus tetap instan.
        t0 = time.perf_counter()
        h = client.get("/health")
        dt = time.perf_counter() - t0
        assert h.status_code == 200
        assert dt < 0.3, f"/health butuh {dt:.3f}s — event loop terblokir"


def test_dua_tugas_lambat_paralel(srv, monkeypatch):
    """MIAW_WORKERS=2 → dua tugas 2 detik selesai < 3 detik (bukan 4)."""
    def slow(_data):
        time.sleep(2.0)
        return "8f3kd", "local"

    monkeypatch.setattr(srv.fb, "solve_image_safe", slow)

    with TestClient(srv.app) as client:
        ids = []
        for i in range(2):
            r = client.post("/in.php",
                            files={"file": (f"a{i}.png", PNG_1PX, "image/png")},
                            data={"key": API_KEY, "method": "post"})
            assert r.status_code == 200
            ids.append(r.text.split("|", 1)[1])

        t0 = time.perf_counter()
        for tid in ids:
            _wait_done(client, tid, timeout=10)
        dt = time.perf_counter() - t0

    assert dt < 3.0, f"dua tugas 2 s selesai dalam {dt:.2f}s — tidak paralel"


# ------------------------------------------------------- B. kompat 2captcha

def test_in_php_key_di_form_balas_teks_polos(srv):
    """/in.php dengan key di form → 200 dan body `OK|<id>` (teks polos)."""
    with TestClient(srv.app) as client:
        r = client.post("/in.php",
                        files={"file": ("a.png", PNG_1PX, "image/png")},
                        data={"key": API_KEY, "method": "post"})
    assert r.status_code == 200, r.text
    assert r.text.startswith("OK|"), r.text
    assert len(r.text.split("|", 1)[1]) >= 8
    assert r.headers["content-type"].startswith("text/plain")


def test_in_php_json_eq_1_balas_json(srv):
    """json=1 → JSON {"status":1,"request":"<id>"}."""
    with TestClient(srv.app) as client:
        r = client.post("/in.php?json=1",
                        files={"file": ("a.png", PNG_1PX, "image/png")},
                        data={"key": API_KEY, "method": "post"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == 1
    assert len(body["request"]) >= 8


def test_res_php_key_di_query(srv):
    """/res.php?key=..&action=get&id=.. → `OK|<jawaban>`.

    Jawaban dibandingkan dengan hasil library langsung, bukan string yang
    dipatok: nilai OCR bergantung pada build ddddocr/onnxruntime per
    interpreter (pernah beda antara py3.10 dan py3.12), jadi mematok string
    literal di sini akan bikin CI merah palsu.
    """
    from captcha_solver import solve_image

    fixture = (ROOT / "testdata" / "captcha_like.png").read_bytes()
    harap = solve_image(fixture)

    with TestClient(srv.app) as client:
        r = client.post("/in.php",
                        files={"file": ("captcha_like.png", fixture, "image/png")},
                        data={"key": API_KEY, "method": "post"})
        assert r.status_code == 200, r.text
        tid = r.text.split("|", 1)[1]

        out = _wait_done(client, tid)

    assert out.startswith("OK|"), out
    assert out.split("|", 1)[1] == harap


def test_res_php_id_ngawur(srv):
    """Id tak dikenal → ERROR_WRONG_CAPTCHA_ID (bukan CAPCHA_NOT_READY)."""
    with TestClient(srv.app) as client:
        r = client.get("/res.php",
                       params={"key": API_KEY, "action": "get", "id": "ngawur123"})
    assert r.status_code == 200
    assert r.text == "ERROR_WRONG_CAPTCHA_ID", r.text


def test_res_php_kedaluwarsa(srv):
    """Id yang sudah dibersihkan TTL juga → ERROR_WRONG_CAPTCHA_ID."""
    with TestClient(srv.app) as client:
        r = client.post("/in.php",
                        files={"file": ("a.png", PNG_1PX, "image/png")},
                        data={"key": API_KEY, "method": "post"})
        tid = r.text.split("|", 1)[1]
        srv.STORE._rows.pop(tid, None) if hasattr(srv.STORE, "_rows") else None
        r2 = client.get("/res.php",
                        params={"key": API_KEY, "action": "get", "id": tid})
    assert r2.text == "ERROR_WRONG_CAPTCHA_ID", r2.text


def test_key_salah_401(srv):
    with TestClient(srv.app) as client:
        r = client.post("/in.php",
                        files={"file": ("a.png", PNG_1PX, "image/png")},
                        data={"key": "salah", "method": "post"})
    assert r.status_code == 401, r.text


def test_key_kosong_401(srv):
    with TestClient(srv.app) as client:
        r = client.post("/in.php",
                        files={"file": ("a.png", PNG_1PX, "image/png")},
                        data={"method": "post"})
    assert r.status_code == 401, r.text


def test_key_dari_header_dan_query(srv):
    """Header X-API-Key dan ?key= juga diterima."""
    with TestClient(srv.app) as client:
        r1 = client.post("/in.php",
                         files={"file": ("a.png", PNG_1PX, "image/png")},
                         data={"method": "post"},
                         headers={"X-API-Key": API_KEY})
        r2 = client.post(f"/in.php?key={API_KEY}",
                         files={"file": ("a.png", PNG_1PX, "image/png")},
                         data={"method": "post"})
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text


def test_in_dan_res_tetap_json(srv):
    """Path /in dan /res (tanpa .php) tidak boleh berubah jadi teks polos."""
    with TestClient(srv.app) as client:
        r = client.post("/in",
                        files={"file": ("a.png", PNG_1PX, "image/png")},
                        data={"key": API_KEY, "method": "post"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == 1 and "request" in body

        r2 = client.get("/res", params={"key": API_KEY, "action": "get", "id": "ngawur"})
        assert r2.json() == {"status": 0, "request": "ERROR_WRONG_CAPTCHA_ID"}


def test_userrecaptcha_ditolak_jelas(srv):
    """method=userrecaptcha bukan captcha gambar — tolak, jangan salah tafsir."""
    with TestClient(srv.app) as client:
        r = client.post("/in.php",
                        files={"file": ("a.png", PNG_1PX, "image/png")},
                        data={"key": API_KEY, "method": "userrecaptcha",
                              "googlekey": "x", "pageurl": "http://x/"})
    assert r.status_code == 200
    assert r.text == "ERROR_METHOD_NOT_SUPPORTED", r.text
    # pastikan TIDAK masuk antrean sebagai tugas gambar
    with TestClient(srv.app) as client:
        s = client.get("/stats").json()
    assert s["request"]["in"] >= 1


def test_unggahan_terlalu_besar(srv, monkeypatch):
    """Lewat MIAW_MAX_UPLOAD_MB → ERROR_TOO_BIG_CAPTCHA_FILESIZE."""
    monkeypatch.setattr(srv.CFG, "max_upload_mb", 1)
    besar = b"\x89PNG\r\n\x1a\n" + b"\x00" * (1024 * 1024 + 2048)

    with TestClient(srv.app) as client:
        r = client.post("/in.php",
                        files={"file": ("big.png", besar, "image/png")},
                        data={"key": API_KEY, "method": "post"})
    assert r.text == "ERROR_TOO_BIG_CAPTCHA_FILESIZE", r.text


def test_rate_limiter_bersihkan_ip_mati(srv, monkeypatch):
    """IP yang tidak pernah kembali tidak boleh menumpuk di _HITS."""
    monkeypatch.setattr(srv.CFG, "rate_limit", 5)
    now = time.time()
    srv._HITS.clear()
    # 1500 IP basi, di atas ambang sweep
    for i in range(1500):
        srv._HITS[f"10.0.{i // 256}.{i % 256}"] = [now - 3600]

    class _FakeReq:
        class client:  # noqa: N801
            host = "192.168.1.1"

    assert srv._rate_ok(_FakeReq()) is True

    basi = [k for k, v in srv._HITS.items()
            if k != "192.168.1.1" and all(now - t >= 60 for t in v)]
    assert not basi, f"{len(basi)} IP basi masih tertinggal"
    assert "192.168.1.1" in srv._HITS


def test_worker_menghormati_workers(srv):
    """MIAW_WORKERS=2 → dua task pool hidup."""
    with TestClient(srv.app) as client:
        client.get("/health")
        assert len(srv.app.state.pool) == 2
