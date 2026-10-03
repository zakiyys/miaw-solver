#!/usr/bin/env bash
# Native + 2captcha-compatible HTTP endpoints.
#
#   python -m uvicorn server:app --host 127.0.0.1 --port 8100
set -euo pipefail

B="${BASE_URL:-http://127.0.0.1:8100}"
KEY="${MIAW_API_KEY:-}"
H=()
[ -n "$KEY" ] && H=(-H "X-API-Key: $KEY")

echo "== /health =="
curl -s "$B/health" | python3 -m json.tool

echo
echo "== POST /solve (image, direct answer) =="
curl -s -X POST "$B/solve" "${H[@]}" -F "file=@testdata/captcha_like.png" | python3 -m json.tool

echo
echo "== POST /solve/text =="
curl -s -X POST "$B/solve/text" "${H[@]}" -F "question=9 x 9" | python3 -m json.tool

echo
echo "== POST /solve/audio =="
curl -s -X POST "$B/solve/audio" "${H[@]}" -F "file=@testdata/audio_4c7n.wav" | python3 -m json.tool

echo
echo "== 2captcha flow: POST /in then poll GET /res =="
ID=$(curl -s -X POST "$B/in" "${H[@]}" -F "file=@testdata/captcha_like.png" -F "method=post" \
     | python3 -c 'import sys,json;print(json.load(sys.stdin)["request"])')
echo "  task id: $ID"
for _ in $(seq 1 15); do
  R=$(curl -s "$B/res?action=get&id=$ID" "${H[@]}")
  case "$R" in
    *CAPCHA_NOT_READY*) sleep 1 ;;
    *) echo "  result : $R"; break ;;
  esac
done

echo
echo "== textcaptcha via /in =="
ID2=$(curl -s -X POST "$B/in" "${H[@]}" -F "method=textcaptcha" -F "textcaptcha=100 - 58" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["request"])')
sleep 1
curl -s "$B/res?action=get&id=$ID2" "${H[@]}"; echo

echo
echo "== /balance and /stats =="
curl -s "$B/balance" "${H[@]}"; echo
curl -s "$B/stats" "${H[@]}" | python3 -m json.tool
