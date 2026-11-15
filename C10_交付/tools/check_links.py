"""文档内链检查：所有相对链接都必须指向真实存在的文件/目录。

为什么需要它：交付物里链接比代码更容易坏——重命名一个文件，十份文档里
可能有三处链接悄悄变成死链，而**没人会去点**。CI 里跑一遍，比人肉点 40 次可靠。

用法：
    python tools/check_links.py          # 检查 C10_交付 下所有 .md
    python tools/check_links.py --quiet  # 只报告错误
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_PREFIX = ("http://", "https://", "mailto:", "#", "tel:")


def check(quiet: bool = False) -> int:
    md_files = sorted(ROOT.rglob("*.md"))
    problems: list[tuple[Path, str, str]] = []
    checked = 0

    for path in md_files:
        if any(part in {".git", "__pycache__", ".venv"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append((path, "<read>", str(exc)))
            continue
        # 跳过代码块：里面的 [x](y) 多半是示例
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for match in LINK.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith(SKIP_PREFIX):
                continue
            target = target.split("#", 1)[0].strip()
            if not target:
                continue
            checked += 1
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                problems.append((path, target, str(resolved)))

    if problems:
        print(f"✗ 发现 {len(problems)} 处死链（检查了 {len(md_files)} 个 md，{checked} 条链接）")
        for path, target, resolved in problems:
            print(f"  {path.relative_to(ROOT)} → {target}   （解析为 {resolved}）")
        return 1

    print(f"✓ {len(md_files)} 个 md、{checked} 条相对链接，全部有效")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检查 Markdown 相对链接")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    sys.exit(check(args.quiet))
