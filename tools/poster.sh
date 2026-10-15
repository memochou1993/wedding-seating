#!/usr/bin/env bash
# 輸出版席次表 → PDF（讀雲端最新資料）。用法：tools/poster.sh [a2|a1|a3]，預設 A2 橫式
set -euo pipefail
cd "$(dirname "$0")/.."
SIZE="${1:-a2}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
mkdir -p dist
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=15000 \
  --print-to-pdf="$PWD/dist/席次表-$SIZE.pdf" "file://$PWD/index.html?poster=$SIZE" 2>/dev/null
echo "dist/席次表-$SIZE.pdf"
