#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前的产物自检（零依赖，只用标准库）。

CI 的 Pages 工作流没有安装 Pillow，所以不能跑 chartgen --check。
这个脚本只做"发布出去会不会坏"的三件事：

  1. app/assets/shots/ 与 数据/screenshots/ 逐字节一致（副本漂移 -> 线上图和数据不符）
  2. app/article.html 存在且不是空壳（正文没渲染就发布 -> 读者点开是白页）
  3. 数据指纹 manifest 存在（截图与数据可追溯）

用法：python tools/pages_check.py [--root .]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="发布前自检")
    ap.add_argument("--root", default=str(here))
    args = ap.parse_args(argv)

    root = Path(args.root)
    problems: list[str] = []

    shots_dir = root / "数据" / "screenshots"
    shots = sorted(shots_dir.glob("*.png"))
    if len(shots) != 6:
        problems.append(f"数据/screenshots 里应有 6 张 PNG，实际 {len(shots)} 张")
    for src in shots:
        dst = root / "app" / "assets" / "shots" / src.name
        if not dst.exists():
            problems.append(f"app/assets/shots/{src.name} 缺失（跑 tools/build_article.py）")
        elif sha(src) != sha(dst):
            problems.append(f"app/assets/shots/{src.name} 与 数据/screenshots 不一致")

    article = root / "app" / "article.html"
    if not article.exists():
        problems.append("app/article.html 缺失（跑 tools/build_article.py）")
    elif article.stat().st_size < 8000:
        problems.append(f"app/article.html 只有 {article.stat().st_size} 字节，疑似渲染失败")

    manifest = shots_dir / "manifest.json"
    if not manifest.exists():
        problems.append("数据/screenshots/manifest.json 缺失（跑 tools/chartgen.py）")
    else:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if len(data.get("charts", {})) != 6:
            problems.append("manifest 里的图表条目不是 6 个")

    if problems:
        print("[fail] 发布前自检未通过：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"[ok] 发布前自检通过：{len(shots)} 张截图 + 正文 HTML + manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
