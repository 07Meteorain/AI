#!/usr/bin/env bash
# 用无头浏览器把终端风格 HTML 证据页转为 PNG。
# 挑战要求截图（.png），因此需要真实渲染这一步。
set -euo pipefail

EDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
DIR="$(cd "$(dirname "$0")/.." && pwd)/姓名_C4D_output_screenshots"
PROFILE="$(mktemp -d)"

echo "输出目录: $DIR"
shopt -s nullglob

convert_one() {
  local src="$1"
  local base
  base="$(basename "${src%.html}")"
  local out="$DIR/$base.png"

  "$EDGE" --headless=new --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=2 \
    --window-size=1400,1000 \
    --screenshot="$out" \
    --user-data-dir="$PROFILE" \
    "file:///$src" >/dev/null 2>&1 || true

  if [[ -s "$out" ]]; then
    printf '  ✓ %-28s %s\n' "$base.png" "$(du -h "$out" | cut -f1)"
  else
    printf '  ✗ %-28s 渲染失败\n' "$base.png"
  fi
}

for f in "$DIR"/*.html; do
  convert_one "$(cygpath -m "$f" 2>/dev/null || echo "$f")"
done

rm -rf "$PROFILE"
echo "完成。"