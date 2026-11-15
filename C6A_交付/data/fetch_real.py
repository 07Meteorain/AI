#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取本人仓库的真实提交数据（C6A 的「真实锚点」数据源）。

为什么单独一个脚本、而不是混进 build_dataset.py：

- 班级全景是**合成**数据，可以离线复现；这份是**真实**数据，需要网络与 API 配额。
  两者生命周期不同，混在一起会让「离线可复跑」这条性质失效。
- 抓取结果落盘为 `data/real/self_commits.json` 并随仓库提交，看板默认读快照，
  断网也能用；想刷新时再跑这个脚本。

它顺手证明了本挑战最想讲的一件事：**git 的 commit 时间是「推送时间」，不是「完成时间」。**
C2G 目录 50 条 commit 集中在 110 分钟内、C1 的 840 个文件只有 3 小时窗口——
如果拿 commit 时间当提交时间去判迟交，结论会整段失真。

用法：
    python data/fetch_real.py                 # 匿名（60 次/小时配额）
    GITHUB_TOKEN=xxx python data/fetch_real.py  # 提高配额
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = "07Meteorain/AI"
TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "real" / "self_commits.json"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
API = "https://api.github.com"


def get(url: str) -> object:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "c6a-dashboard")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_local(iso_utc: str) -> str:
    """UTC ISO → +08:00 ISO。时区差 8 小时，足以翻转「是否迟交」。"""
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def main() -> int:
    try:
        repo = get(f"{API}/repos/{REPO}")
        branch = repo.get("default_branch", "master")
        tree = get(f"{API}/repos/{REPO}/git/trees/{branch}?recursive=1")
    except urllib.error.HTTPError as e:
        print(f"GitHub API 失败：{e.code} {e.reason}（匿名配额 60 次/小时，可设 GITHUB_TOKEN）")
        return 1

    files_by_dir: dict[str, list[int]] = {}
    for node in tree.get("tree", []):
        if node.get("type") != "blob":
            continue
        parts = node["path"].split("/")
        if len(parts) < 2:
            continue
        d = parts[0]
        files_by_dir.setdefault(d, []).append(int(node.get("size") or 0))

    folders = sorted(files_by_dir)
    items = []
    for folder in folders:
        commits = get(f"{API}/repos/{REPO}/commits?path={urllib.parse.quote(folder)}&per_page=100")
        if not isinstance(commits, list):
            commits = []
        dates = sorted(commits and [c["commit"]["author"]["date"] for c in commits] or [])
        first = to_local(dates[0]) if dates else None
        last = to_local(dates[-1]) if dates else None
        span = 0.0
        if first and last:
            span = round(
                (datetime.fromisoformat(last) - datetime.fromisoformat(first)).total_seconds() / 3600, 2
            )
        items.append(
            {
                "folder": folder,
                "kind": "infra" if folder.startswith(".") else "delivery",
                "commits": len(commits),
                "first_commit": first,
                "last_commit": last,
                "span_hours": span,
                "commits_per_hour": round(len(commits) / span, 2) if span > 0 else None,
                "files": len(files_by_dir[folder]),
                "kb": round(sum(files_by_dir[folder]) / 1024, 1),
                "squashed": len(commits) >= 5 and span <= 4,  # 疑似一次性推送/历史改写
            }
        )

    payload = {
        "source": f"GitHub REST API /repos/{REPO}/commits（按目录过滤，每目录上限 100 条）+ /git/trees/{branch}",
        "repo": f"https://github.com/{REPO}",
        "branch": branch,
        "fetched_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "timezone": "GitHub 返回 UTC，统一换算为 +08:00 存储与展示",
        "caveat": "commit 时间是推送时间，不是完成时间；批量推送/改写历史会让它集中在几分钟内，不能直接当提交时间用。",
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {OUT.relative_to(ROOT)}：{len(items)} 个目录，{sum(i['commits'] for i in items)} 条 commit")
    for it in items:
        if it["kind"] == "delivery":
            flag = " ⚠一次性推送" if it["squashed"] else ""
            print(f"  {it['folder']:<24} {it['commits']:>3}c {it['files']:>5}f span={it['span_hours']:>6}h{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
