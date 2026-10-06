#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pr_desc.py — 自动生成结构化 PR 描述。

输入：仓库路径 + 基准分支
输出：Markdown 格式的 PR 描述
"""

import argparse
import subprocess
import sys
from pathlib import Path

MAX_DIFF_LINES = 2000


def git(repo: Path, *args) -> str:
    """执行 git 命令并返回 stdout。失败时返回空串而非抛异常。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def collect_commits(repo: Path, base: str) -> list[str]:
    log = git(repo, "log", f"{base}..HEAD", "--pretty=format:%h %s")
    return [ln for ln in log.splitlines() if ln.strip()]


def collect_diff(repo: Path, base: str) -> tuple[str, bool]:
    diff = git(repo, "diff", f"{base}...HEAD", "--stat")
    lines = diff.splitlines()
    truncated = len(lines) > MAX_DIFF_LINES
    return "\n".join(lines[:MAX_DIFF_LINES]), truncated


def render(commits: list[str], diff_stat: str, truncated: bool) -> str:
    """组装最终 PR 描述。"""
    out = ["## PR 描述（自动生成）", "", "### 变更内容"]
    if commits:
        out += [f"- {c}" for c in commits]
    else:
        out.append("- （无新 commit）")

    out += ["", "### 变更原因", "- 见 commit message"]

    out += ["", "### 验证方式", "- 请补充测试结果"]
    if truncated:
        out.append(f"\n> ⚠️ diff 超过 {MAX_DIFF_LINES} 行，已截断")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 PR 描述")
    ap.add_argument("--repo", required=True, help="仓库路径")
    ap.add_argument("--base", default="main", help="基准分支")
    ap.add_argument("--out", default=None, help="输出文件，默认 stdout")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        sys.stderr.write(f"ERROR: '{repo}' 不是有效目录\n")
        return 1

    commits = collect_commits(repo, args.base)
    if not commits and not git(repo, "rev-parse", "HEAD"):
        sys.stderr.write("ERROR: 仓库无 commit\n")
        return 1

    diff_stat, truncated = collect_diff(repo, args.base)
    text = render(commits, diff_stat, truncated)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())