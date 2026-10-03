"""Text worker — captcha tanya-jawab sederhana.

Strategi (CPU, tanpa model): normalisasi → deteksi aritmatika → hitung aman.
Fallback: balikin token angka/kata yang paling masuk akal.
"""
from __future__ import annotations

import ast
import operator
import re

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

_WORDS = {
    "nol": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
    "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10,
    "sebelas": 11, "dua belas": 12, "dua puluh": 20, "seratus": 100,
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# kata-operator (ID + EN) -> simbol
_OPWORDS = {
    "tambah": "+", "ditambah": "+", "plus": "+", "and": "+",
    "kurang": "-", "dikurangi": "-", "minus": "-", "min": "-",
    "kali": "*", "dikali": "*", "times": "*", "multiplied": "*",
    "bagi": "/", "dibagi": "/", "divided": "/",
}

_SYM = {"+": "+", "-": "-", "×": "*", "x": "*", "*": "*", "÷": "/", "/": "/"}


def _safe_eval(expr: str):
    node = ast.parse(expr, mode="eval").body

    def _ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](_ev(n.left), _ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](_ev(n.operand))
        raise ValueError("ekspresi tidak didukung")

    return _ev(node)


class TextWorker:
    def solve(self, question: str) -> str:
        q = question.lower().strip()

        # kata-angka -> digit. WAJIB frasa panjang dulu ("dua puluh" sebelum "dua"),
        # kalau tidak "dua puluh" jadi "2 puluh" dan frasa 20-nya hilang.
        for w, d in sorted(_WORDS.items(), key=lambda kv: -len(kv[0])):
            q = re.sub(rf"\b{re.escape(w)}\b", str(d), q)
        # kata-operator -> simbol (sebelum simbol mentah), frasa panjang dulu juga
        for w, s in sorted(_OPWORDS.items(), key=lambda kv: -len(kv[0])):
            q = re.sub(rf"\b{re.escape(w)}\b", f" {s} ", q)
        # simbol -> operator
        for k, v in _SYM.items():
            q = q.replace(k, v)

        # ambil ekspresi aritmatika pertama
        m = re.search(r"-?\d+(?:\s*[+\-*/%]\s*-?\d+)+", q)
        if m:
            expr = m.group(0).replace(" ", "")
            try:
                val = _safe_eval(expr)
                if isinstance(val, float) and val.is_integer():
                    val = int(val)
                return str(val)
            except Exception:  # noqa: BLE001
                pass

        # fallback: angka tunggal yang disebut
        nums = re.findall(r"-?\d+", q)
        if nums:
            return nums[0]

        return q.strip()
