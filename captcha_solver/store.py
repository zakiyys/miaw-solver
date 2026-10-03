"""Task store — antrean tugas bergaya 2captcha.

Dua backend:
    MemoryStore  — default, tanpa dependensi, cocok untuk satu proses.
    SqliteStore  — persisten; tugas tetap ada setelah restart, dan bisa dibaca
                   beberapa proses/worker sekaligus (WAL).

Kontrak yang ditiru 2captcha:
    - `/in`  -> task_id segera (tanpa menunggu solve selesai)
    - `/res` -> "CAPCHA_NOT_READY" selama belum selesai, lalu jawabannya
    - id tak dikenal / kedaluwarsa -> CAPCHA_NOT_READY
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path

PENDING = "pending"
DONE = "done"
ERROR = "error"


def new_id() -> str:
    return uuid.uuid4().hex[:16]


class MemoryStore:
    """Store in-memory. Cepat, hilang saat proses mati."""

    def __init__(self, ttl: int = 300):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._rows: dict[str, dict] = {}

    def add(self, kind: str, payload: dict) -> str:
        tid = new_id()
        with self._lock:
            self._gc()
            self._rows[tid] = {
                "id": tid,
                "kind": kind,
                "payload": payload,
                "status": PENDING,
                "answer": None,
                "error": None,
                "created": time.time(),
            }
        return tid

    def claim(self) -> dict | None:
        """Ambil satu tugas pending (tandai 'processing' agar tidak diambil dobel)."""
        with self._lock:
            self._gc()
            for row in self._rows.values():
                if row["status"] == PENDING:
                    row["status"] = "processing"
                    return dict(row)
        return None

    def finish(self, tid: str, answer: str | None = None, error: str | None = None) -> None:
        with self._lock:
            row = self._rows.get(tid)
            if not row:
                return
            if error:
                row["status"], row["error"] = ERROR, error
            else:
                row["status"], row["answer"] = DONE, answer

    def get(self, tid: str) -> dict | None:
        with self._lock:
            self._gc()
            row = self._rows.get(tid)
            return dict(row) if row else None

    def stats(self) -> dict:
        with self._lock:
            self._gc()
            out = {PENDING: 0, DONE: 0, ERROR: 0, "processing": 0}
            for r in self._rows.values():
                out[r["status"]] = out.get(r["status"], 0) + 1
            return out

    def _gc(self) -> None:
        now = time.time()
        for k in [k for k, v in self._rows.items() if now - v["created"] > self._ttl]:
            self._rows.pop(k, None)


class SqliteStore:
    """Store persisten (WAL). Aman untuk beberapa proses sekaligus.

    Payload biner (gambar/audio) disimpan sebagai BLOB, bukan JSON — JSON tidak
    bisa memuat bytes dan base64 akan membengkakkan ukuran ~33%.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS tasks (
        id       TEXT PRIMARY KEY,
        kind     TEXT NOT NULL,
        payload  BLOB,
        ptext    TEXT,
        status   TEXT NOT NULL,
        answer   TEXT,
        error    TEXT,
        created  REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, created);
    """

    def __init__(self, path: str | Path, ttl: int = 300):
        self._path = str(path)
        self._ttl = ttl
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(self._SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        return c

    @staticmethod
    def _encode(payload):
        """Balikin (blob, teks): tepat satu yang terisi."""
        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload), None
        return None, "" if payload is None else str(payload)

    @staticmethod
    def _decode(row: sqlite3.Row):
        blob, text = row["payload"], row["ptext"]
        return bytes(blob) if blob is not None else text

    def add(self, kind: str, payload) -> str:
        blob, text = self._encode(payload)
        tid = new_id()
        with self._lock, self._conn() as c:
            self._gc(c)
            c.execute(
                "INSERT INTO tasks(id,kind,payload,ptext,status,created) VALUES(?,?,?,?,?,?)",
                (tid, kind, blob, text, PENDING, time.time()),
            )
        return tid

    def claim(self) -> dict | None:
        with self._lock, self._conn() as c:
            self._gc(c)
            row = c.execute(
                "SELECT * FROM tasks WHERE status=? ORDER BY created LIMIT 1", (PENDING,)
            ).fetchone()
            if not row:
                return None
            c.execute("UPDATE tasks SET status='processing' WHERE id=?", (row["id"],))
            d = dict(row)
            d["payload"] = self._decode(row)
            d["status"] = "processing"
            return d

    def finish(self, tid: str, answer: str | None = None, error: str | None = None) -> None:
        with self._lock, self._conn() as c:
            if error:
                c.execute("UPDATE tasks SET status=?,error=? WHERE id=?", (ERROR, error, tid))
            else:
                c.execute("UPDATE tasks SET status=?,answer=? WHERE id=?", (DONE, answer, tid))

    def get(self, tid: str) -> dict | None:
        with self._lock, self._conn() as c:
            self._gc(c)
            row = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["payload"] = self._decode(row)
            return d

    def stats(self) -> dict:
        with self._lock, self._conn() as c:
            self._gc(c)
            rows = c.execute("SELECT status, COUNT(*) n FROM tasks GROUP BY status").fetchall()
            return {r["status"]: r["n"] for r in rows}

    def _gc(self, c: sqlite3.Connection) -> None:
        c.execute("DELETE FROM tasks WHERE created < ?", (time.time() - self._ttl,))


def make_store(path: str = "", ttl: int = 300):
    """Pilih backend: SQLite kalau path diisi, kalau tidak in-memory."""
    if path:
        return SqliteStore(path, ttl=ttl)
    return MemoryStore(ttl=ttl)
