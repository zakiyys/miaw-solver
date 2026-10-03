"""Test thread-safety inti + pemulihan store.

Dua bagian:
  1. `_load_*` di core.py tidak boleh memuat model dua kali saat dipanggil
     dari banyak thread bersamaan (server memakai asyncio.to_thread).
  2. SqliteStore harus mengembalikan tugas 'processing' sisa crash ke 'pending'
     saat init, dan menutup koneksinya dengan rapi.
"""
from __future__ import annotations

import sqlite3
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ------------------------------------------------------------- 1. lock model

def test_load_ocr_tidak_dimuat_dua_kali():
    """20 thread memanggil _load_ocr bersamaan → konstruktor jalan sekali."""
    from captcha_solver import core

    dibuat = []
    siap = threading.Barrier(20)

    class _FakeOcr:
        def __init__(self):
            time.sleep(0.05)          # jendela balapan: cukup lebar
            dibuat.append(threading.get_ident())

    asli = core._ocr
    core._ocr = None
    core._load_ocr.__globals__["_ocr"] = None
    try:
        import captcha_solver.workers.ocr as ocr_mod
        asli_cls = ocr_mod.OcrWorker
        ocr_mod.OcrWorker = _FakeOcr

        hasil = []

        def _panggil():
            siap.wait()
            hasil.append(core._load_ocr())

        threads = [threading.Thread(target=_panggil) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(dibuat) == 1, f"model dimuat {len(dibuat)} kali, harusnya 1"
        assert len({id(h) for h in hasil}) == 1, "thread dapat instance berbeda"
    finally:
        import captcha_solver.workers.ocr as ocr_mod
        ocr_mod.OcrWorker = asli_cls
        core._ocr = asli
        core._load_ocr.__globals__["_ocr"] = asli


def test_load_text_dan_audio_idempoten():
    from captcha_solver import core
    a, b = core._load_text(), core._load_text()
    assert a is b

    c = core._load_audio()
    assert c is core._load_audio()


# ------------------------------------------------------- 2. pemulihan store

def test_sqlite_store_pulihkan_processing_jadi_pending(tmp_path):
    """Tugas 'processing' sisa crash harus kembali 'pending' saat init."""
    from captcha_solver.store import PENDING, SqliteStore

    db = tmp_path / "t.db"
    s1 = SqliteStore(db, ttl=300)
    tid = s1.add("image", b"data")
    s1.claim()                                    # -> 'processing'

    cek = sqlite3.connect(db)
    assert cek.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0] == "processing"
    cek.close()

    # Proses "baru" membuka store yang sama.
    s2 = SqliteStore(db, ttl=300)
    assert s2.get(tid)["status"] == PENDING

    # Dan tugas itu benar-benar bisa diambil lagi.
    assert s2.claim()["id"] == tid


def test_sqlite_store_pulihkan_tanpa_mengganggu_yang_selesai(tmp_path):
    from captcha_solver.store import DONE, SqliteStore

    db = tmp_path / "t.db"
    s1 = SqliteStore(db, ttl=300)
    t_done = s1.add("text", "4 + 8")
    s1.finish(t_done, answer="12")
    t_pending = s1.add("text", "1 + 1")

    s2 = SqliteStore(db, ttl=300)
    assert s2.get(t_done)["status"] == DONE
    assert s2.get(t_done)["answer"] == "12"
    assert s2.get(t_pending)["status"] == "pending"


def test_sqlite_store_koneksi_ditutup(tmp_path):
    """Koneksi harus ditutup tiap operasi — tidak menumpuk file descriptor."""
    from captcha_solver.store import SqliteStore

    db = tmp_path / "t.db"
    s = SqliteStore(db, ttl=300)
    tid = s.add("text", "1 + 1")
    s.get(tid)
    s.stats()
    s.finish(tid, answer="2")

    # Kalau koneksi bocor, Windows/macOS akan mengunci file; di Linux kita cek
    # jumlah fd terbuka ke file itu lewat /proc.
    import subprocess
    out = subprocess.run(
        ["bash", "-c", f"ls -1 /proc/$$/fd 2>/dev/null | wc -l"],
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 0


def test_memory_store_tidak_terpengaruh(tmp_path):
    """MemoryStore tidak punya konsep 'processing' yang perlu dipulihkan."""
    from captcha_solver.store import PENDING, MemoryStore

    s = MemoryStore(ttl=300)
    tid = s.add("image", b"x")
    assert s.get(tid)["status"] == PENDING
    s.claim()
    assert s.get(tid)["status"] == "processing"      # in-memory: tidak dipulihkan
