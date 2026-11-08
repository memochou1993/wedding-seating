#!/usr/bin/env bash
# 輸出版座位表 → PDF（讀雲端最新資料）。用法：tools/poster.sh [a2|a1|a3] [1122]，預設 A2 橫式、1025 文定
set -euo pipefail
cd "$(dirname "$0")/.."
SIZE="${1:-a2}"
SHOW="${2:-}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
PAGE="index.html"; OUT="dist/座位表-$SIZE.pdf"
if [ -n "$SHOW" ]; then PAGE="$SHOW/index.html"; OUT="dist/$SHOW-座位表-$SIZE.pdf"; fi
mkdir -p dist
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=15000 \
  --print-to-pdf="$PWD/$OUT" "file://$PWD/$PAGE?poster=$SIZE" 2>/dev/null
echo "$OUT"
