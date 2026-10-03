"""Logging terstruktur — teks ramah-manusia atau JSON untuk agregator log.

Aturan: TIDAK PERNAH mencatat kunci API, isi gambar/audio, atau jawaban penuh
pada level INFO. Jawaban hanya muncul di DEBUG, dan dipotong.
"""
from __future__ import annotations

import json
import logging
import sys
import time


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # field tambahan via `extra={...}`
        for k in ("task_id", "kind", "source", "ms", "client", "status"):
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        bits = [f"{ts}", f"{record.levelname:<5}", record.getMessage()]
        for k in ("task_id", "kind", "source", "ms", "client", "status"):
            v = getattr(record, k, None)
            if v is not None:
                bits.append(f"{k}={v}")
        line = " ".join(bits)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup(level: str = "INFO", json_logs: bool = False, name: str = "miaw") -> logging.Logger:
    """Pasang handler sekali; panggilan berikutnya tidak menumpuk handler."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter() if json_logs else _TextFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get(name: str = "miaw") -> logging.Logger:
    return logging.getLogger(name)
