#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 demo/截图 拼成一张走查 GIF。

为什么用 GIF 而不是 mp4/录屏：
- 不依赖录屏软件（无头环境里录不了屏）；
- 帧就是「真实渲染出来的截图」，与本仓库代码一一对应，重跑即更新；
- 体积小（约 2–3 MB），GitHub 上直接能看。

依赖：Pillow（本机随 Python 运行时附带）。这不是看板运行时的依赖，
只影响「重新生成 demo 图」这一件事，所以放在 tools/ 下。
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    print("需要 Pillow：python -m pip install pillow")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "demo" / "截图"
OUT = ROOT / "demo" / "walkthrough.gif"

# 顺序 = 演示脚本的顺序：总览 → 洞察 → 学生详情 → 口径 → 真实数据 → 浅色
FRAMES = [
    ("01-总览.png", 2600),
    ("02-洞察.png", 2400),
    ("04-学生详情.png", 2400),
    ("05-口径.png", 2200),
    ("06-真实数据.png", 2000),
    ("07-浅色主题.png", 2000),
]
WIDTH = 1180  # 缩到这个宽度既能看清字，又能把体积压到 3 MB 内


def main() -> int:
    frames = []
    for name, ms in FRAMES:
        p = SHOTS / name
        if not p.exists():
            print(f"缺图：{p}")
            return 1
        im = Image.open(p).convert("RGB")
        h = round(im.height * WIDTH / im.width)
        im = im.resize((WIDTH, h), Image.LANCZOS)
        im = im.convert("P", palette=Image.ADAPTIVE, colors=128)
        frames.append((im, ms))

    frames[0][0].save(
        OUT,
        save_all=True,
        append_images=[f[0] for f in frames[1:]],
        duration=[f[1] for f in frames],
        loop=0,
        optimize=True,
        disposal=2,
    )
    kb = OUT.stat().st_size / 1024
    print(f"写入 {OUT.relative_to(ROOT)}：{len(frames)} 帧，{WIDTH}px 宽，{kb:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
