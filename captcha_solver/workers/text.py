"""Text worker — captcha tanya-jawab sederhana.

Strategi (CPU, tanpa model): normalisasi → deteksi aritmatika → hitung aman.

Prinsip: **tidak menebak.** Kalau tidak ada ekspresi aritmatika yang dikenali,
worker ini melempar error — tidak mengembalikan angka pertama yang kebetulan
dilihat, dan tidak mengembalikan pertanyaannya sendiri. README menyebutnya
"silence beats a confident wrong answer"; di sini bentuknya exception, supaya
`core.solve_text` bisa membungkusnya jadi `SolverError` dan pemanggil tahu
bahwa pertanyaan itu memang tidak bisa dijawab.
"""
from __future__ import annotations

import ast
import operator
import re

# ast.Pow sengaja TIDAK ada di sini: `**` tidak pernah muncul di captcha
# aritmatika, dan operator pangkat adalah jalan termurah menuju "9**9**9"
# menghabiskan CPU. Operator yang tidak dibutuhkan tidak didaftarkan.
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}

_ONES = {
    "nol": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
    "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9,
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}

# belasan
_TEENS = {
    "sepuluh": 10, "sebelas": 11, "dua belas": 12, "tiga belas": 13,
    "empat belas": 14, "lima belas": 15, "enam belas": 16, "tujuh belas": 17,
    "delapan belas": 18, "sembilan belas": 19,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}

# puluhan
_TENS = {
    "dua puluh": 20, "tiga puluh": 30, "empat puluh": 40, "lima puluh": 50,
    "enam puluh": 60, "tujuh puluh": 70, "delapan puluh": 80, "sembilan puluh": 90,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

# pengali skala
_SCALES = {
    "ratus": 100, "seratus": 100, "hundred": 100,
    "ribu": 1000, "seribu": 1000, "thousand": 1000,
    "juta": 1_000_000, "million": 1_000_000,
}

# kamus gabungan untuk normalisasi frasa (urut panjang dulu saat dipakai)
_WORDS: dict[str, int] = {}
_WORDS.update(_ONES)
_WORDS.update(_TEENS)
_WORDS.update(_TENS)
_WORDS.update(_SCALES)

# penanda internal: token ini berasal dari konversi kata-angka, jadi boleh
# digabung dengan tetangganya. Digit yang memang ditulis berjejer oleh pembuat
# captcha ("Enter the digits 4 7 1") TIDAK boleh digabung.
_MARK = "\x00"


def _parse_number_words(s: str) -> str:
    """Ubah kata-angka (EN+ID) jadi digit, mendukung ratusan/ribuan.

    Penggabungan hanya berlaku untuk token hasil konversi. ``one hundred twenty
    five`` -> ``125`` · ``dua ratus lima puluh`` -> ``250`` · ``one thousand`` ->
    ``1000``. Sebaliknya ``4 7 1`` (digit asli) tetap ``4 7 1``.

    Frasa panjang didahulukan supaya ``dua puluh`` tidak hancur jadi ``2 puluh``.
    """
    for phrase, val in sorted(_WORDS.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(rf"\b{re.escape(phrase)}\b", f" {_MARK}{val}{_MARK} ", s)

    out: list[str] = []
    i = 0
    tokens = s.split()
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith(_MARK):
            out.append(tok)
            i += 1
            continue

        # deret angka hasil konversi saja yang digabung
        nums: list[int] = []
        while i < len(tokens) and tokens[i].startswith(_MARK):
            nums.append(int(tokens[i].strip(_MARK)))
            i += 1

        total = 0
        cur = 0
        for n in nums:
            if n >= 100:
                cur = (cur or 1) * n
                if n >= 1000:
                    total += cur
                    cur = 0
            else:
                cur += n
        total += cur
        out.append(str(total))

    return " ".join(out)


# kata-operator (ID + EN) -> simbol
_OPWORDS = {
    "tambah": "+", "ditambah": "+", "plus": "+", "and": "+",
    "kurang": "-", "dikurangi": "-", "minus": "-", "min": "-",
    "kali": "*", "dikali": "*", "times": "*", "multiplied": "*",
    "bagi": "/", "dibagi": "/", "divided": "/",
}

# 'x'/'×' hanya jadi '*' kalau benar-benar diapit angka. `str.replace` global
# akan merusak kata yang kebetulan mengandung 'x' ("box", "six").
_X_BETWEEN_DIGITS = re.compile(r"(?<=\d)\s*[x×]\s*(?=\d)")


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
    """Jawab captcha tanya-jawab. Lempar `ValueError` kalau tidak bisa dijawab."""

    def solve(self, question: str) -> str:
        q = (question or "").lower().strip()
        if not q:
            raise ValueError("pertanyaan kosong")

        # kata-angka -> digit (hanya token hasil konversi yang digabung)
        q = _parse_number_words(q)
        # kata-operator -> simbol, frasa panjang dulu
        for w, s in sorted(_OPWORDS.items(), key=lambda kv: -len(kv[0])):
            q = re.sub(rf"\b{re.escape(w)}\b", f" {s} ", q)
        # 'x' di antara angka -> '*'
        q = _X_BETWEEN_DIGITS.sub(" * ", q)
        # sisa simbol mentah
        q = q.replace("÷", "/")

        m = re.search(r"-?\d+(?:\s*[+\-*/%]\s*-?\d+)+", q)
        if not m:
            # Tidak ada ekspresi aritmatika. Jangan menebak angka pertama dan
            # jangan mengembalikan pertanyaannya — itu jawaban salah yang pede.
            raise ValueError(
                "tidak ada ekspresi aritmatika yang dikenali di pertanyaan ini"
            )

        expr = m.group(0).replace(" ", "")
        val = _safe_eval(expr)          # ZeroDivisionError dibiarkan naik
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        return str(val)
