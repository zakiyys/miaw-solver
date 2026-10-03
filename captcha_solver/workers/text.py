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

# kamus gabungan untuk normalisasi frasa (urut panjang dulu)
_WORDS = {}
_WORDS.update(_ONES)
_WORDS.update(_TEENS)
_WORDS.update(_TENS)
_WORDS.update(_SCALES)


def _parse_number_words(s: str) -> str:
    """Ubah kata-angka (EN+ID) jadi digit, mendukung ratusan/ribuan.

    Contoh: "one hundred twenty five" -> "125", "dua ratus lima puluh" -> "250",
            "one thousand" -> "1000". Frasa panjang didahulukan supaya
            "dua puluh" tidak hancur jadi "2 puluh".
    """
    # Frasa (puluhan/belasan) dulu — paling panjang lebih dulu
    for phrase, val in sorted(_WORDS.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(rf"\b{re.escape(phrase)}\b", f" {val} ", s)

    # Sekarang token berupa angka + pengali skala. Gabungkan "20 5" -> 25,
    # "100 20 5" -> 125, "1 1000" -> 1000, dst.
    tokens = s.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        # kumpulkan deret angka berurutan
        nums: list[int] = []
        while i < len(tokens) and re.fullmatch(r"\d+", tokens[i]):
            nums.append(int(tokens[i]))
            i += 1
        if not nums:
            out.append(tokens[i])
            i += 1
            continue

        total = 0
        cur = 0
        for n in nums:
            if n >= 100:
                # pengali skala: kalikan akumulasi (atau 1 kalau kosong)
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

        # kata-angka -> digit, mendukung ratusan/ribuan/puluhan majemuk.
        q = _parse_number_words(q)
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
