#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库事实快照：把文章里出现的每个"事实数字"变成可复算的产物。

两类数据，分开对待：

  * **实测**（files / kb / commits / tests_computed）—— 从 git 历史与源码静态计数得出，
    换台机器重跑就能复现（前提是 clone 到完整历史）。
  * **自报**（declared_tests）—— 各关 README 里自己写的数，逐条带出处与"证据串"。
    本脚本会去对应 README 里核对这串证据是否真的存在；对不上就报 `EVIDENCE_MISSING`。

为什么要有这个脚本：文章正文里写了"63 次提交、1300 多个文件、446 项自测"。
手打这三个数字的代价是——它们会在下一次提交后立刻变成假话。所以正文把它们钉在
`master@099371a`（C7 提交之前）这个快照上，而快照本身由本脚本产出。

用法：
    python tools/repo_facts.py --repo <仓库根>          # 重新生成快照（需完整 git 历史）
    python tools/repo_facts.py --check                  # 校验已提交快照的内部一致性 + 证据串（CI 用）

`--check` 不依赖 git（GitHub Actions 默认 shallow clone），只做两件事：
  1. 快照里 declared 与 computed 的差值与 `declared_tests.csv` 一致；
  2. 每个 evidence 串真的出现在对应 README 里。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

BASELINE_COMMIT = "165f7d3d7d0ad5d6a2339402528e46bf42cecc81"
BASELINE_DATE = "2026-11-15"
BASELINE_NOTE = "C7 提交之前的 master（含 C6A）"
SKIP_DIRS = {".git", ".github", "C7_内容传播"}

PY_TEST_RE = re.compile(r"^\s*def test_", re.M)
JS_TEST_RE = re.compile(r"(?:^|\s)(?:test|it)\s*\(", re.M)


def count_tests(root: Path) -> tuple[int, int, list[str]]:
    py = js = 0
    files: list[str] = []
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        if "test" not in rel.lower():
            continue
        if f.suffix == ".py":
            n = len(PY_TEST_RE.findall(f.read_text(encoding="utf-8", errors="replace")))
            if n:
                py += n
                files.append(f"{rel}:{n}")
        elif f.name.endswith(".test.js"):
            n = len(JS_TEST_RE.findall(f.read_text(encoding="utf-8", errors="replace")))
            if n:
                js += n
                files.append(f"{rel}:{n}")
    return py, js, files


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout


def load_declared(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["scope"]] = row
    return out


def build(repo: Path, declared: dict[str, dict]) -> tuple[list[dict], dict]:
    rows = []
    for d in sorted(repo.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name in SKIP_DIRS:
            continue
        files = [f for f in d.rglob("*") if f.is_file() and ".git" not in f.parts]
        size_kb = round(sum(f.stat().st_size for f in files) / 1024)
        commits = len(git(repo, "log", "--pretty=format:%H", "--", d.name).splitlines())
        py, js, detail = count_tests(d)
        dec = declared.get(d.name)
        rows.append({
            "scope": d.name,
            "files": len(files),
            "kb": size_kb,
            "commits": commits,
            "tests_computed": py + js,
            "tests_py": py,
            "tests_js": js,
            "declared_tests": dec["declared_tests"] if dec else "",
            "declared_source": dec["source"] if dec else "",
            "test_files": " ".join(detail),
        })
    meta = {
        "as_of_commit": BASELINE_COMMIT,
        "as_of_date": BASELINE_DATE,
        "baseline_note": BASELINE_NOTE,
        "repo": "https://github.com/07Meteorain/AI",
        "total_commits": int(git(repo, "rev-list", "--count", "HEAD").strip()),
        "counted_scopes": [r["scope"] for r in rows],
        "method": "files/kb: os.walk 计数；commits: git log -- <dir> 计数；tests: def test_ / test( / it( 静态正则计数",
    }
    return rows, meta


def render_csv(rows: list[dict]) -> str:
    import io

    header = ["scope", "files", "kb", "commits", "tests_computed", "tests_py", "tests_js",
              "declared_tests", "declared_source", "test_files"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def check(csv_path: Path, meta_path: Path, root: Path) -> int:
    problems: list[str] = []
    if not csv_path.exists() or not meta_path.exists():
        print("[fail] 缺少 数据/repo_facts.csv 或 repo_facts.meta.json", file=sys.stderr)
        return 1
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
    declared = load_declared(root / "数据" / "declared_tests.csv")

    # 1) 自报数必须与证据串一致，且实测差值可解释
    for row in rows:
        scope = row["scope"]
        dec = declared.get(scope)
        if dec:
            if row["declared_tests"] != dec["declared_tests"]:
                problems.append(f"{scope}: 快照 declared={row['declared_tests']} != declared_tests.csv {dec['declared_tests']}")
            if row["declared_tests"] != row["tests_computed"]:
                problems.append(f"{scope}: 自报 {row['declared_tests']} != 实测 {row['tests_computed']}（README 与代码不一致，需修正其中一方）")
        elif row["declared_tests"]:
            problems.append(f"{scope}: 快照有自报数但 declared_tests.csv 里没有出处")

    # 2) 证据串必须真的出现在 README 里
    for scope, dec in declared.items():
        src = root.parent / dec["source"] if not (root / dec["source"]).exists() else root / dec["source"]
        if not src.exists():
            problems.append(f"{scope}: 出处文件不存在 {dec['source']}")
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        if dec["evidence"] not in text:
            problems.append(f"{scope}: 证据串「{dec['evidence']}」不在 {dec['source']} 中")

    # 3) 总测试数必须与文章/清单里的口径一致
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    total = sum(int(r["tests_computed"]) for r in rows)
    if meta.get("total_tests") != total:
        problems.append(f"meta.total_tests={meta.get('total_tests')} 与快照合计 {total} 不一致")

    if problems:
        print("[fail] 仓库事实快照校验失败：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"[ok] repo_facts 快照自洽：{len(rows)} 个目录，合计 {total} 项测试")
    return 0


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="仓库事实快照")
    parser.add_argument("--root", default=str(here), help="C7_内容传播 目录")
    parser.add_argument("--repo", default=None, help="仓库根（重新生成时需要，需完整 git 历史）")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root)
    csv_path = root / "数据" / "repo_facts.csv"
    meta_path = root / "数据" / "repo_facts.meta.json"

    if args.check:
        return check(csv_path, meta_path, root)

    if not args.repo:
        print("需要 --repo <仓库根> 才能重新生成快照", file=sys.stderr)
        return 2
    repo = Path(args.repo).resolve()
    declared = load_declared(root / "数据" / "declared_tests.csv")
    rows, meta = build(repo, declared)
    meta["total_tests"] = sum(r["tests_computed"] for r in rows)
    meta["total_files"] = sum(r["files"] for r in rows)
    meta["total_commits"] = meta["total_commits"]

    csv_path.write_text(render_csv(rows), encoding="utf-8", newline="")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
    print(f"[ok] {len(rows)} 个目录 -> repo_facts.csv；合计 {meta['total_tests']} 项测试 / {meta['total_files']} 个文件 / {meta['total_commits']} 次提交")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
