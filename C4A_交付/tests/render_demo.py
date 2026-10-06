#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_demo.py — 生成 demo/ 下的终端截图（交付物之一：C4 要求的 demo）

为什么要这个脚本：
    C4 要求 demo 是"真实运行结果"，不是手画的示意图。
    所以这里不写死文本，而是**读取真实运行日志**再渲染成图——
    图里的每一个数字都来自实际执行，杜绝"演示与实现不符"。

用法：
    python render_demo.py --log run_output.txt -o ../demo/demo_evaluator_cli.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

MONO = "C:/Windows/Fonts/consola.ttf"
CJK = "C:/Windows/Fonts/msyh.ttc"


def is_cjk(ch: str) -> bool:
    return ord(ch) > 0x2E80


def render_terminal(lines: list[tuple[str, tuple[int, int, int]]],
                    title: str, out: Path, width: int = 1080,
                    lh: int = 25, top: int = 60) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, top + lh * len(lines) + 24), (22, 24, 30))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, 44], fill=(38, 42, 52))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([18 + i * 22, 15, 30 + i * 22, 27], fill=c)
    ft = ImageFont.truetype(MONO, 15)
    d.text((92, 13), title, font=ft, fill=(190, 196, 210))

    def flush(x, y, buf, cjk, col):
        if not buf:
            return x
        fo = ImageFont.truetype(CJK if cjk else MONO, 16)
        d.text((x, y), buf, font=fo, fill=col)
        return x + d.textlength(buf, font=fo)

    y = top
    for txt, col in lines:
        if txt:
            x, buf, cur = 18, "", None
            for ch in txt:
                c = is_cjk(ch)
                if cur is None:
                    cur = c
                if c != cur:
                    x = flush(x, y, buf, cur, col)
                    buf, cur = ch, c
                else:
                    buf += ch
            flush(x, y, buf, cur, col)
        y += lh
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"生成: {out}  {img.size}")


# 终端配色
GREEN = (126, 211, 133)
WHITE = (214, 222, 235)
GREY = (110, 116, 130)
BLUE = (126, 185, 247)
ORANGE = (240, 175, 120)
RED = (240, 130, 130)
YELLOW = (230, 200, 120)


def colorize(line: str) -> tuple[str, tuple[int, int, int]]:
    """按内容给终端行上色，让截图尽量贴近真实终端观感。"""
    s = line.rstrip("\n")
    if s.startswith("$ ") or s.startswith("python "):
        return s, GREEN
    if s.startswith("[collect]"):
        return s, BLUE
    if any(k in s for k in ("报告(MD)", "数据(JSON)", "详表(XLSX)", "扫描路径",
                            "作者数", "C4 文件数", "达成级别")):
        return s, WHITE
    if set(s.strip()) == {"-"} and s.strip():
        return s, GREY
    if "完整性 100%" in s:
        return s, GREEN
    if "完整性" in s and "[low]" in s:
        return s, ORANGE
    if "[low]" in s and "完整性" in s:
        return s, RED
    return s, WHITE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, help="真实运行输出日志文件")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--title", default="MINGW64:/c/C4A_交付 — bash")
    ap.add_argument("--cwd", default="C4A_交付",
                    help="把日志里的长绝对路径折叠成这个前缀，避免截图溢出")
    args = ap.parse_args()

    raw = Path(args.log).read_text(encoding="utf-8", errors="replace").splitlines()
    # 折叠超长绝对路径：取仓库内相对部分，保证截图可读
    folded = []
    for ln in raw:
        s = ln.rstrip("\n")
        if "我的挑战" in s:
            head, _, tail = s.partition("我的挑战")
            # 保留 C4A_交付/ 之后的相对路径
            idx = tail.find("C4A_交付")
            s = f"{head}{args.cwd}" + (tail[idx + len('C4A_交付'):] if idx >= 0 else "")
        folded.append(s)
    keep = [ln for ln in folded if ln.strip() and not ln.startswith(("Verifying",))]
    lines = [colorize(ln) for ln in keep]
    render_terminal(lines, args.title, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())