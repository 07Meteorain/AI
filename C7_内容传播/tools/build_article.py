#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 正文.md 渲染成公众号可粘贴的 HTML，并把 app/ 需要的静态资源同步过去。

为什么复用 C4B 的 wechat_publisher 而不是自己写一遍：
  C4B 那个转换器是上一关自己写的、确定性的（同一输入必得同一输出），并且已经处理了
  公众号编辑器的排版限制（内联样式、外链清理、callout、目录）。这里直接调用它，
  少一套实现，就少一处会漂移的地方。

产物（三个都是"生成的"，不要手改）：
  文章/微信版.html     —— 可直接全选复制进 mp.weixin.qq.com 的编辑器
  app/article.html     —— app 的阅读页（iframe 引用同一份 HTML）
  app/checklist.html   —— 《验收清单》单页（从 文章/验收清单.html 复制）
  app/assets/shots/*   —— 6 张数据截图的副本（让 app 可以独立分发）

用法：
    python tools/build_article.py          # 重新生成
    python tools/build_article.py --check  # 校验产物是否与源文件同步（CI 用）
"""

from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PUBLISHER_REL = "C4B_公众号文章生成技能/meteorain-wechat-publisher/scripts/wechat_publisher.py"

TARGETS = [
    ("文章/微信版.html", "app/article.html"),
    ("文章/验收清单.html", "app/checklist.html"),
]


def find_publisher(root: Path, override: str | None) -> Path:
    if override:
        p = Path(override)
        if p.exists():
            return p
        raise SystemExit(f"[fail] --publisher 指向的文件不存在：{p}")
    # C7 在仓库里时：<repo>/C7_内容传播 的兄弟目录
    for base in (root.parent, root.parent.parent):
        cand = base / PUBLISHER_REL
        if cand.exists():
            return cand
    raise SystemExit(
        "[fail] 找不到 C4B 的 wechat_publisher.py。\n"
        f"       期望位置：<repo>/{PUBLISHER_REL}\n"
        "       单独跑 C7 目录时请用 --publisher 指定绝对路径。"
    )


def render(publisher: Path, src: Path, dst: Path) -> None:
    cmd = [sys.executable, str(publisher), str(src), str(dst), "--theme", "accent", "--toc"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + "\n" + proc.stderr + "\n")
        raise SystemExit(f"[fail] 渲染失败：{src.name}")
    if not dst.exists() or dst.stat().st_size < 4000:
        raise SystemExit(f"[fail] 渲染产物异常：{dst}")


# --- 修 C4B 目录生成的一处缺陷 -------------------------------------------------
# C4B 的 wechat_publisher 生成的目录会漏掉第一个 h2（正文 6 个小标题，目录只有 5 条）。
# 用法上这是一次真实的"读代码没发现、用起来才发现"的 bug，记在 AI日志.md 第 6 轮。
# 这里不改 C4B（那是上一关的交付物），而是在生成的产物上重排目录：条目来自 h2 本身，
# 所以永远和正文对得上。
TOC_P_STYLE = (
    "font-size: 15px; line-height: 1.9; color: #202124; "
    "margin: 5px 0; font-weight: bold;"
)
H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _h2_texts(html: str) -> list[str]:
    out = []
    for raw in H2_RE.findall(html):
        text = TAG_RE.sub("", raw).strip()
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        if text:
            out.append(text)
    return out


def fix_toc(html: str) -> tuple[str, int]:
    """把目录条目重排成 h2 的全集。返回 (新 HTML, 补齐的条目数)。"""
    texts = _h2_texts(html)
    marker = "📖 本文目录"
    if not texts or marker not in html:
        return html, 0
    start = html.index(marker)
    end = html.index("</section>", start)
    block = html[start:end]
    existing = block.count("<p style=")  # 标题那一行的 <p> 在 marker 之前，不会被算进来
    if existing == len(texts):
        return html, 0
    items = "".join(
        f'<p style="{TOC_P_STYLE}">{i}. {html_escape(t)}</p>' for i, t in enumerate(texts, 1)
    )
    head_end = html.index("</p>", start) + len("</p>")
    new_html = html[:head_end] + items + html[end:]
    return new_html, max(len(texts) - existing, 0)


def html_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="正文 → 公众号 HTML + app 资源")
    ap.add_argument("--root", default=str(here))
    ap.add_argument("--publisher", default=None)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    publisher = find_publisher(root, args.publisher)

    with tempfile.TemporaryDirectory() as td:
        tmp_html = Path(td) / "wx.html"
        render(publisher, root / "文章" / "正文.md", tmp_html)
        html = tmp_html.read_text(encoding="utf-8")
        html, patched = fix_toc(html)
        rendered = html.encode("utf-8")

    wx = root / "文章" / "微信版.html"
    article = root / "app" / "article.html"

    if args.check:
        problems = []
        for path in (wx, article):
            if not path.exists():
                problems.append(f"{path.relative_to(root)}: 缺失")
            elif path.read_bytes() != rendered:
                problems.append(f"{path.relative_to(root)}: 与 正文.md 渲染结果不一致（改完正文忘了重跑 tools/build_article.py）")
        for src_rel, dst_rel in TARGETS[1:]:
            src, dst = root / src_rel, root / dst_rel
            if not dst.exists() or not filecmp.cmp(src, dst, shallow=False):
                problems.append(f"{dst_rel}: 与 {src_rel} 不一致")
        shots = sorted((root / "数据" / "screenshots").glob("*.png"))
        for s in shots:
            d = root / "app" / "assets" / "shots" / s.name
            if not d.exists() or not filecmp.cmp(s, d, shallow=False):
                problems.append(f"app/assets/shots/{s.name}: 与 数据/screenshots 不一致")
        if problems:
            print("[stale] 产物需要重新生成（python tools/build_article.py）：", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        print(f"[ok] 文章 HTML 与 {len(shots)} 张截图副本均与源文件一致")
        return 0

    wx.write_bytes(rendered)
    article.write_bytes(rendered)
    print(f"[ok] 文章/微信版.html  ({len(rendered) // 1024} KB)")
    if patched:
        print(f"[fix] 目录补齐 {patched} 条（C4B 的目录生成会漏掉第一个 h2，见 AI日志.md 第 6 轮）")

    for src_rel, dst_rel in TARGETS[1:]:
        shutil.copyfile(root / src_rel, root / dst_rel)
        print(f"[ok] {dst_rel}")

    shots_dir = root / "app" / "assets" / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for s in sorted((root / "数据" / "screenshots").glob("*.png")):
        shutil.copyfile(s, shots_dir / s.name)
        n += 1
    print(f"[ok] app/assets/shots/  {n} 张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
