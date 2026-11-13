"""生成 PromptGate 的图标（SVG + PNG）。

只依赖 Pillow，且只在需要改图时运行一次；产出的 PNG 已随仓库提交，
所以「跑起来」不需要执行这个脚本。
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "app" / "assets"

BG_TOP = (10, 14, 26)
BG_BOTTOM = (26, 36, 64)
ACCENT = (139, 157, 255)
OK = (52, 211, 153)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_icon(size: int) -> Image.Image:
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角底
    radius = int(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=BG_TOP)

    # 垂直渐变（逐行画在圆角遮罩里）
    grad = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        gd.line([(0, y), (s, y)], fill=lerp(BG_TOP, BG_BOTTOM, y / s) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    img = Image.composite(grad, img, mask)
    d = ImageDraw.Draw(img)

    # 门框（两条竖线 + 顶梁）
    lw = max(2, int(s * 0.035))
    left = int(s * 0.27)
    right = int(s * 0.73)
    top = int(s * 0.24)
    bottom = int(s * 0.80)
    d.line([(left, top), (left, bottom)], fill=ACCENT + (255,), width=lw)
    d.line([(right, top), (right, bottom)], fill=ACCENT + (255,), width=lw)
    d.line([(left, top), (right, top)], fill=ACCENT + (255,), width=lw)

    # 门内对勾
    cx = s * 0.5
    cy = s * 0.55
    r = s * 0.16
    d.line(
        [(cx - r, cy + r * 0.05), (cx - r * 0.2, cy + r * 0.75), (cx + r, cy - r * 0.65)],
        fill=OK + (255,),
        width=int(lw * 1.5),
        joint="curve",
    )

    # 顶梁上的两个小灯
    d.ellipse(
        [cx - s * 0.035, top - s * 0.085, cx + s * 0.035, top - s * 0.015],
        fill=(245, 181, 68, 255),
    )

    return img.resize((size, size), Image.LANCZOS)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0a0e1a"/>
      <stop offset="1" stop-color="#1a2440"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="url(#bg)"/>
  <g fill="none" stroke="#8b9dff" stroke-width="4.5" stroke-linecap="round">
    <path d="M35 31v72M93 31v72M35 31h58"/>
  </g>
  <path d="M48 66l9 10 19-22" fill="none" stroke="#34d399" stroke-width="7"
        stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="64" cy="20" r="4.5" fill="#f5b544"/>
</svg>
"""


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "icon.svg").write_text(SVG, encoding="utf-8")
    for size in (192, 512):
        draw_icon(size).save(ASSETS / f"icon-{size}.png")
    # macOS/iOS 与浏览器标签页用的小图
    draw_icon(32).save(ASSETS / "favicon-32.png")
    print("图标已生成：", ", ".join(sorted(p.name for p in ASSETS.iterdir())))


if __name__ == "__main__":
    main()
