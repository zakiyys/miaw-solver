"""Worker gambar — OCR teks terdistorsi (ddddocr).

ddddocr memuat model ONNX saat pertama dipakai; wrapper ini menjaga muat-lazinya.
"""
from __future__ import annotations


class OcrWorker:
    def __init__(self):
        self._ocr = None

    def _load(self):
        if self._ocr is None:
            import ddddocr

            # show_ad=False wajib: tanpa ini ddddocr mencetak iklan ke stdout
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr

    def solve(self, data: bytes) -> str:
        result = self._load().classification(data)
        return (result or "").strip()
