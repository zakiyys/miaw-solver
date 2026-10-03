#!/usr/bin/env bash
# Every CLI subcommand. Run from the repo root after installing the package.
set -euo pipefail

echo "== version =="
miaw-solve --version

echo
echo "== image (OCR) =="
miaw-solve image testdata/captcha_like.png

echo
echo "== image, raw bytes from stdin ('-' means stdin) =="
cat testdata/captcha_like.png | miaw-solve image -

echo
echo "== text =="
miaw-solve text "7 x 6"
miaw-solve text "tiga tambah lima"
miaw-solve text "100 - 58"

echo
echo "== audio =="
miaw-solve audio testdata/audio_4c7n.wav

echo
echo "== explicit router =="
miaw-solve auto image testdata/captcha_like.png
miaw-solve auto text "9 x 9"

echo
echo "== legacy alias: 'solve' == 'image' =="
miaw-solve solve testdata/captcha_like.png
