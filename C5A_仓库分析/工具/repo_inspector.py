#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repo_inspector —— 零依赖 Git 仓库结构分析器。

用法::

    python repo_inspector.py <仓库路径>
    python repo_inspector.py <仓库路径> --out-md 报告.md --out-json 指标.json
    python repo_inspector.py <仓库路径> --now 2026-11-10T23:30:19+08:00

设计约束：

1. 只依赖 Python 标准库和 ``git`` 命令，任何装了 git 的机器都能复现；
2. 同时输出「人读的 Markdown」和「机读的 JSON」，方便二次处理；
3. 每个指标都写明口径，报告中给出的数字都可用 git 原生命令复核。

退出码：0 成功；2 路径不是 Git 仓库；3 git 命令失败。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = 1

COMMIT_FORMAT = "%H%x1f%an%x1f%ae%x1f%cI%x1f%s%x1f%b%x1e"

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<desc>\S.*)$"
)

TEST_PATH_RE = re.compile(
    r"(^|/)test_[^/]+\.(py|rb|js|ts)$"
    r"|_test\.(py|go|rb)$"
    r"|\.(test|spec)\.[jt]sx?$"
    r"|(^|/)tests?/[^/]+\.(py|rb|js|ts|go)$",
    re.IGNORECASE,
)

SOURCE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".scala", ".sh", ".ps1", ".sql", ".lua", ".r", ".m", ".mm", ".vue",
    ".svelte", ".dart", ".ex", ".exs",
}

DOC_EXTS = {".md", ".rst", ".adoc", ".txt"}

GOVERNANCE_CHECKS = [
    ("readme", "README", 6, "根目录 README"),
    ("license", "LICENSE", 4, "开源许可证"),
    ("contributing", "CONTRIBUTING", 5, "贡献指南"),
    ("changelog", "CHANGELOG", 4, "变更日志"),
    ("code_of_conduct", "CODE_OF_CONDUCT", 3, "行为准则"),
    ("security", "SECURITY", 3, "安全披露政策"),
    ("ci", "CI 工作流", 8, ".github/workflows 下的流水线"),
    ("issue_templates", "Issue 模板", 4, "结构化的 Issue 模板"),
    ("dependabot", "依赖自动更新", 3, "Dependabot / Renovate 配置"),
    ("release_workflow", "发布流水线", 5, "自动构建或发布工作流"),
    ("tests", "测试目录", 8, "tests/ 或 test/ 目录"),
    ("test_files", "测试文件", 7, "≥10 个测试文件"),
    ("test_ratio", "测试代码密度", 5, "测试 LOC / 源码 LOC ≥ 0.3"),
    ("tags", "版本标签", 5, "≥3 个 tag"),
    ("conventional", "规范化提交", 8, "Conventional Commits 占比 ≥ 30%"),
    ("merges", "合并痕迹", 4, "≥3 个 merge commit（分支/PR 协作）"),
    ("message_quality", "提交信息质量", 3, "主题长度 10–72 字符且超长占比 <10%"),
    ("recent", "近期活跃", 8, "最近 365 天内有提交"),
    ("branch_hygiene", "分支卫生", 7, "过期远程分支占比 ≤ 25%"),
]


class GitError(RuntimeError):
    """git 命令返回非零状态。"""


def run_git(repo, *args):
    """在指定仓库运行 git，返回 UTF-8 解码后的 stdout。

    :raises GitError: git 返回非零状态。
    """
    cmd = ["git", "-C", str(repo), "-c", "core.quotepath=false"] + list(args)
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if proc.returncode != 0:
        raise GitError(
            "git {} 失败（exit {}）：{}".format(
                " ".join(args),
                proc.returncode,
                proc.stderr.decode("utf-8", "replace").strip(),
            )
        )
    return proc.stdout.decode("utf-8", "replace")


def try_git(repo, *args, default=""):
    """运行 git，失败时返回 default，用于可选信息。"""
    try:
        return run_git(repo, *args)
    except GitError:
        return default


def parse_iso(value):
    """解析 git 的 ISO-8601 时间（含偏移量）。"""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def count_lines(data):
    """按行计数；末尾没有换行符也算一行。"""
    if not data:
        return 0
    lines = data.count(b"\n")
    if not data.endswith(b"\n"):
        lines += 1
    return lines


def is_binary(data):
    """前 8KB 出现 NUL 字节即视为二进制。"""
    return b"\x00" in data[:8192]


def extension_of(path):
    """返回小写扩展名，无扩展名时返回固定标记。"""
    suffix = Path(path).suffix.lower()
    return suffix if suffix else "(无扩展名)"


def directory_of(path):
    """取路径第一层目录；根目录文件单独归类。"""
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "(根目录)"


def is_source(path):
    return extension_of(path) in SOURCE_EXTS


def is_test_path(path):
    return bool(TEST_PATH_RE.search(path))


def classify_commit(subject):
    """解析 Conventional Commit，返回 (type, scope, breaking) 或 None。"""
    match = CONVENTIONAL_RE.match(subject.strip())
    if not match:
        return None
    return (
        match.group("type"),
        match.group("scope"),
        bool(match.group("breaking")),
    )


def human_int(value):
    return "{:,}".format(int(value))


def human_bytes(size):
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return "{:.1f} {}".format(value, unit) if unit != "B" else "{:.0f} B".format(value)
        value /= 1024
    return "{:.1f} GB".format(value)


def pct(part, total, digits=1):
    if not total:
        return "—"
    return ("{:.%df}%%" % digits).format(part * 100.0 / total)


def table(headers, rows):
    """生成 Markdown 表格。"""
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join([" --- "] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def _file_size(repo, path):
    try:
        return os.path.getsize(os.path.join(str(repo), path.replace("/", os.sep)))
    except OSError:
        return 0


def _read_file(repo, path):
    try:
        with open(os.path.join(str(repo), path.replace("/", os.sep)), "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def collect_files(repo, tracked):
    """统计文件数量、行数、扩展名、目录与最大文件。"""
    ext_files = Counter()
    ext_loc = Counter()
    dir_files = Counter()
    dir_loc = Counter()
    largest = []
    binary_count = 0
    total_loc = 0
    source_loc = 0
    test_loc = 0
    test_file_count = 0

    for path in tracked:
        size = _file_size(repo, path)
        data = _read_file(repo, path)
        binary = is_binary(data)
        loc = 0 if binary else count_lines(data)
        ext = extension_of(path)
        directory = directory_of(path)

        ext_files[ext] += 1
        ext_loc[ext] += loc
        dir_files[directory] += 1
        dir_loc[directory] += loc
        total_loc += loc
        if binary:
            binary_count += 1
        if is_source(path):
            if is_test_path(path):
                test_file_count += 1
                test_loc += loc
            else:
                source_loc += loc
        elif is_test_path(path):
            test_file_count += 1
            test_loc += loc
        largest.append((path, size))

    largest.sort(key=lambda item: item[1], reverse=True)
    return {
        "tracked": len(tracked),
        "binary": binary_count,
        "text": len(tracked) - binary_count,
        "total_loc": total_loc,
        "source_loc": source_loc,
        "test_loc": test_loc,
        "test_file_count": test_file_count,
        "by_extension": [
            {
                "ext": ext,
                "files": files,
                "loc": ext_loc[ext],
                "share": files / len(tracked) if tracked else 0.0,
            }
            for ext, files in ext_files.most_common()
        ],
        "by_directory": [
            {
                "dir": directory,
                "files": files,
                "loc": dir_loc[directory],
                "share": files / len(tracked) if tracked else 0.0,
            }
            for directory, files in dir_files.most_common()
        ],
        "largest": [
            {"path": path, "size": size} for path, size in largest[:20]
        ],
    }


def collect_commits(repo, top_n):
    """解析提交历史：作者、类型、年份、消息质量、churn。"""
    raw = run_git(repo, "log", "--pretty=format:" + COMMIT_FORMAT)
    merge_hashes = set(
        run_git(repo, "log", "--merges", "--format=%H").split()
    )

    records = []
    for block in raw.split("\x1e"):
        block = block.strip("\n")
        if not block:
            continue
        parts = block.split("\x1f")
        if len(parts) < 6:
            continue
        sha, author, email, date_text, subject = parts[:5]
        body = "\x1f".join(parts[5:])
        try:
            committed = parse_iso(date_text)
        except ValueError:
            continue
        records.append(
            {
                "sha": sha,
                "author": author,
                "email": email,
                "date": committed,
                "subject": subject.strip(),
                "body": body.strip(),
                "merge": sha in merge_hashes,
            }
        )

    authors = Counter(record["author"] for record in records)
    by_year = Counter(str(record["date"].year) for record in records)
    type_counts = Counter()
    conventional = 0
    subject_lengths = []
    long_subjects = 0
    with_body = 0
    for record in records:
        subject = record["subject"]
        subject_lengths.append(len(subject))
        if len(subject) > 72:
            long_subjects += 1
        if record["body"]:
            with_body += 1
        parsed = classify_commit(subject)
        if parsed:
            conventional += 1
            type_counts[parsed[0]] += 1

    # 变更热点：一次 git log 同时拿到每个提交改动的文件。
    churn = Counter()
    test_touching = 0
    raw_paths = run_git(
        repo, "log", "--no-merges", "--pretty=format:%x01%H", "--name-only"
    )
    for block in raw_paths.split("\x01")[1:]:
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        paths = lines[1:]
        churn.update(paths)
        if any(is_test_path(path) for path in paths):
            test_touching += 1

    non_merge_total = max(1, len(records) - len(merge_hashes))
    return {
        "total": len(records),
        "merges": len(merge_hashes),
        "merge_ratio": len(merge_hashes) / len(records) if records else 0.0,
        "authors": [
            {"name": name, "count": count, "share": count / len(records) if records else 0.0}
            for name, count in authors.most_common(top_n)
        ],
        "author_total": len(authors),
        "by_year": [
            {"year": year, "count": by_year[year]} for year in sorted(by_year)
        ],
        "conventional_count": conventional,
        "conventional_ratio": conventional / non_merge_total,
        "type_counts": dict(type_counts.most_common()),
        "subject_avg_len": (
            sum(subject_lengths) / len(subject_lengths) if subject_lengths else 0.0
        ),
        "subject_gt_72_ratio": long_subjects / len(records) if records else 0.0,
        "body_ratio": with_body / len(records) if records else 0.0,
        "churn": [
            {"path": path, "commits": count, "share": count / non_merge_total}
            for path, count in churn.most_common(20)
        ],
        "test_touching_commits": test_touching,
        "test_touch_ratio": test_touching / non_merge_total,
    }


def collect_branches(repo, stale_days, now):
    """收集本地/远程分支，统计超过 stale_days 未更新的远程分支。"""
    raw = run_git(
        repo,
        "for-each-ref",
        "--format=%(refname)%09%(committerdate:iso-strict)",
        "refs/heads",
        "refs/remotes",
    )
    default_ref = try_git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    default_branch = default_ref.split("/", 1)[-1] if default_ref else ""
    if not default_branch:
        default_branch = try_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() or "master"

    local = []
    remote = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        refname, _, date_text = line.partition("\t")
        refname = refname.strip()
        if refname.endswith("/HEAD"):
            continue
        try:
            committed = parse_iso(date_text.strip())
        except ValueError:
            continue
        if refname.startswith("refs/heads/"):
            name = refname[len("refs/heads/"):]
            local.append({"name": name, "date": committed.isoformat(), "days": max(0, (now - committed).days)})
        elif refname.startswith("refs/remotes/"):
            name = refname[len("refs/remotes/"):]
            remote.append({"name": name, "date": committed.isoformat(), "days": max(0, (now - committed).days)})

    cutoff = now - timedelta(days=stale_days)
    stale = [
        item
        for item in remote
        if item["name"].split("/", 1)[-1] != default_branch
        and parse_iso(item["date"]) < cutoff
    ]
    return {
        "local_count": len(local),
        "remote_count": len(remote),
        "default": default_branch,
        "stale_days": stale_days,
        "stale_count": len(stale),
        "stale_ratio": len(stale) / len(remote) if remote else 0.0,
        "stale": stale,
        "local": local,
    }


def collect_tags(repo):
    raw = run_git(
        repo,
        "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname:short)%09%(creatordate:short)",
        "refs/tags",
    )
    tags = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        name, _, date_text = line.partition("\t")
        tags.append({"name": name.strip(), "date": date_text.strip()})
    return {
        "count": len(tags),
        "latest": tags[0]["name"] if tags else "",
        "latest_date": tags[0]["date"] if tags else "",
        "list": tags,
    }


def collect_governance(repo):
    """检查常见工程治理文件/目录是否存在。"""
    root = Path(str(repo))

    def exists_any(names):
        return any((root / name).exists() for name in names)

    workflows = root / ".github" / "workflows"
    workflow_names = []
    if workflows.is_dir():
        workflow_names = sorted(
            path.name for path in workflows.iterdir() if path.suffix in (".yml", ".yaml")
        )
    issue_templates = root / ".github" / "ISSUE_TEMPLATE"

    checks = {
        "readme": exists_any(["README.md", "README.rst", "README.txt", "README"]),
        "license": exists_any(["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]),
        "contributing": exists_any(["CONTRIBUTING.md", "CONTRIBUTING.rst", ".github/CONTRIBUTING.md"]),
        "changelog": exists_any(["CHANGELOG.md", "CHANGELOG.rst", "CHANGES.md", "HISTORY.md"]),
        "code_of_conduct": exists_any(["CODE_OF_CONDUCT.md", ".github/CODE_OF_CONDUCT.md"]),
        "security": exists_any(["SECURITY.md", ".github/SECURITY.md"]),
        "ci": bool(workflow_names),
        "issue_templates": issue_templates.is_dir()
        and any(issue_templates.iterdir()),
        "dependabot": (root / ".github" / "dependabot.yml").exists()
        or (root / ".github" / "dependabot.yaml").exists(),
        "release_workflow": any(
            "release" in name or "publish" in name for name in workflow_names
        ),
        "tests": (root / "tests").is_dir() or (root / "test").is_dir(),
    }
    checks["test_files"] = len(list(root.glob("tests/**/test_*.py"))) >= 10 if (root / "tests").is_dir() else False
    return {
        "checks": checks,
        "workflows": workflow_names,
    }


def compute_health(metrics):
    """按「文档 / 自动化 / 测试 / 历史 / 维护」五组检查计算 0–100 分。"""
    gov = metrics["governance"]["checks"]
    files = metrics["files"]
    commits = metrics["commits"]
    branches = metrics["branches"]
    tags = metrics["tags"]
    repo = metrics["repo"]

    test_ratio = (files["test_loc"] / files["source_loc"]) if files["source_loc"] else 0.0
    recent_days = repo.get("last_commit_age_days", 9999)
    stale_ratio = branches.get("stale_ratio", 0.0)

    earned = {}
    evidence = {}

    for key, label, points, _desc in GOVERNANCE_CHECKS:
        if key == "test_ratio":
            ok = test_ratio >= 0.3
            evidence[key] = "测试/源码 LOC = {:.2f}".format(test_ratio)
        elif key == "conventional":
            ok = commits["conventional_ratio"] >= 0.3
            evidence[key] = "占比 {:.1f}%".format(commits["conventional_ratio"] * 100)
        elif key == "merges":
            ok = commits["merges"] >= 3
            evidence[key] = "{} 个 merge commit".format(commits["merges"])
        elif key == "message_quality":
            ok = 10 <= commits["subject_avg_len"] <= 72 and commits["subject_gt_72_ratio"] < 0.1
            evidence[key] = "平均 {:.1f} 字符，超长 {:.1f}%".format(
                commits["subject_avg_len"], commits["subject_gt_72_ratio"] * 100
            )
        elif key == "recent":
            ok = recent_days <= 365
            evidence[key] = "最近提交距今 {} 天".format(recent_days)
        elif key == "branch_hygiene":
            ok = stale_ratio <= 0.25
            evidence[key] = "过期远程分支 {}/{}".format(
                branches["stale_count"], branches["remote_count"]
            )
        elif key == "tags":
            ok = tags["count"] >= 3
            evidence[key] = "{} 个 tag，最新 {}".format(
                tags["count"], tags["latest"] or "—"
            )
        else:
            ok = bool(gov.get(key))
            evidence[key] = "存在" if ok else "缺失"
        earned[key] = points if ok else 0

    score = sum(earned.values())
    checks = []
    for key, label, points, desc in GOVERNANCE_CHECKS:
        checks.append(
            {
                "id": key,
                "label": label,
                "points": points,
                "earned": earned[key],
                "ok": earned[key] > 0,
                "evidence": evidence[key],
                "description": desc,
            }
        )

    findings = []
    if score < 60:
        findings.append("健康度低于 60 分，工程基建存在明显缺口。")
    if not gov.get("readme"):
        findings.append("缺少 README，外部读者无法快速理解项目。")
    if not gov.get("ci"):
        findings.append("未发现 CI 工作流，提交质量只能靠本地自觉。")
    if commits["conventional_ratio"] < 0.3:
        findings.append(
            "Conventional Commits 占比仅 {:.1f}%，提交类型无法被工具聚合。".format(
                commits["conventional_ratio"] * 100
            )
        )
    if recent_days > 365:
        findings.append(
            "最近一次提交距今 {} 天，项目处于低活跃/维护状态，依赖前需评估。".format(recent_days)
        )
    if branches["stale_count"]:
        findings.append(
            "有 {} 个远程分支超过 {} 天未更新，建议合并或删除。".format(
                branches["stale_count"], branches.get("stale_days", 180)
            )
        )
    if test_ratio < 0.3:
        findings.append("测试代码密度偏低（测试/源码 LOC = {:.2f}）。".format(test_ratio))
    if stale_ratio > 0.25:
        findings.append("过期远程分支占比 {:.0f}%，分支模型缺少清理机制。".format(stale_ratio * 100))
    if not findings:
        findings.append("未发现显著风险信号。")

    return {"score": score, "checks": checks, "findings": findings}


def inspect_repo(path, top_n=10, stale_days=180, now=None):
    """分析一个本地 Git 仓库，返回指标字典。"""
    repo = Path(path).resolve()
    try:
        run_git(repo, "rev-parse", "--git-dir")
    except GitError as exc:
        raise GitError("{} 不是可用的 Git 仓库：{}".format(repo, exc))

    # 允许传入仓库子目录：统一提升到工作区根目录，避免 ls-files 相对路径错位。
    toplevel = try_git(repo, "rev-parse", "--show-toplevel").strip()
    if toplevel:
        repo = Path(toplevel)

    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    head_sha = run_git(repo, "rev-parse", "HEAD").strip()
    head_subject = run_git(repo, "log", "-1", "--format=%s").strip()
    head_date_text = run_git(repo, "log", "-1", "--format=%cI").strip()
    head_date = parse_iso(head_date_text)
    last_commit_age_days = max(0, (now - head_date).days)

    first_text = try_git(
        repo, "log", "--reverse", "--format=%cI", "--max-parents=0", "HEAD"
    ).strip().splitlines()
    first_text = first_text[0].strip() if first_text else ""
    first_date = parse_iso(first_text) if first_text else head_date

    branch = try_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() or "HEAD"
    remote = try_git(repo, "remote", "get-url", "origin").strip()
    dirty = bool(try_git(repo, "status", "--porcelain").strip())

    tracked = [item for item in run_git(repo, "ls-files", "-z").split("\x00") if item]
    files = collect_files(repo, tracked)
    commits = collect_commits(repo, top_n)
    branches = collect_branches(repo, stale_days, now)
    tags = collect_tags(repo)
    governance = collect_governance(repo)

    repo_meta = {
        "name": repo.name,
        "path": str(repo),
        "remote": remote,
        "branch": branch,
        "head_sha": head_sha,
        "head_subject": head_subject,
        "head_date": head_date.isoformat(),
        "first_commit_date": first_date.isoformat(),
        "last_commit_age_days": last_commit_age_days,
        "age_days": max(0, (now - first_date).days),
        "dirty": dirty,
        "total_commits": commits["total"],
        "tracked_files": files["tracked"],
    }

    metrics = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "repo": repo_meta,
        "tags": tags,
        "branches": branches,
        "files": files,
        "commits": commits,
        "governance": governance,
        "health": None,
    }
    metrics["health"] = compute_health(metrics)
    return metrics


def render_markdown(metrics):
    """把指标字典渲染为中文 Markdown 报告。"""
    repo = metrics["repo"]
    files = metrics["files"]
    commits = metrics["commits"]
    branches = metrics["branches"]
    tags = metrics["tags"]
    health = metrics["health"]

    lines = []
    lines.append("# 仓库结构分析报告：`{}`".format(repo["name"]))
    lines.append("")
    lines.append(
        "> 由 `工具/repo_inspector.py` 于 {} 生成；所有指标均为本地 git 只读统计，口径见文末。".format(
            metrics["generated_at"]
        )
    )
    lines.append("")

    lines.append("## 1. 概览")
    lines.append("")
    overview = [
        ("远程地址", repo["remote"] or "（无）"),
        ("默认分支", repo["branch"]),
        ("HEAD", "`{}` {}".format(repo["head_sha"][:10], repo["head_subject"])),
        ("提交总数", human_int(repo["total_commits"])),
        ("贡献者", human_int(commits["author_total"])),
        ("首次提交", repo["first_commit_date"][:10]),
        ("最近提交", repo["head_date"][:10]),
        ("仓库年龄", "{} 天".format(human_int(repo["age_days"]))),
        ("版本标签", "{} 个（最新 {}）".format(tags["count"], tags["latest"] or "—")),
        ("分支", "本地 {} / 远程 {}".format(branches["local_count"], branches["remote_count"])),
        ("工作区", "有未提交改动" if repo["dirty"] else "干净"),
    ]
    lines.append(table(["项目", "值"], overview))
    lines.append("")

    lines.append("## 2. 文件与语言构成")
    lines.append("")
    lines.append(
        "共跟踪 **{}** 个文件（文本 {} / 二进制 {}），文本合计 **{}** 行；源码 {} 行，测试 {} 行（{} 个测试文件）。".format(
            human_int(files["tracked"]),
            human_int(files["text"]),
            human_int(files["binary"]),
            human_int(files["total_loc"]),
            human_int(files["source_loc"]),
            human_int(files["test_loc"]),
            human_int(files["test_file_count"]),
        )
    )
    lines.append("")
    ext_rows = [
        (
            "`{}`".format(item["ext"]),
            human_int(item["files"]),
            human_int(item["loc"]),
            pct(item["share"], 1.0),
        )
        for item in files["by_extension"][:10]
    ]
    lines.append("### 扩展名 Top 10")
    lines.append("")
    lines.append(table(["扩展名", "文件数", "行数", "文件占比"], ext_rows))
    lines.append("")

    dir_rows = [
        (
            "`{}`".format(item["dir"]),
            human_int(item["files"]),
            human_int(item["loc"]),
            pct(item["share"], 1.0),
        )
        for item in files["by_directory"][:10]
    ]
    lines.append("### 顶层目录 Top 10")
    lines.append("")
    lines.append(table(["目录", "文件数", "行数", "文件占比"], dir_rows))
    lines.append("")

    largest_rows = [
        ("`{}`".format(item["path"]), human_bytes(item["size"]))
        for item in files["largest"][:5]
    ]
    lines.append("### 最大的 5 个文件")
    lines.append("")
    lines.append(table(["文件", "大小"], largest_rows))
    lines.append("")

    lines.append("## 3. 提交与协作习惯")
    lines.append("")
    lines.append(
        "提交信息平均 {:.1f} 字符；含正文 {:.1f}%；Conventional Commits {} 条（{:.1f}%）；merge commit {} 个（{:.1f}%）。".format(
            commits["subject_avg_len"],
            commits["body_ratio"] * 100,
            human_int(commits["conventional_count"]),
            commits["conventional_ratio"] * 100,
            human_int(commits["merges"]),
            commits["merge_ratio"] * 100,
        )
    )
    lines.append("")
    if commits["type_counts"]:
        type_rows = [
            ("`{}`".format(key), human_int(value))
            for key, value in commits["type_counts"].items()
        ]
        lines.append("### 规范提交类型分布")
        lines.append("")
        lines.append(table(["类型", "数量"], type_rows))
        lines.append("")

    author_rows = [
        (item["name"], human_int(item["count"]), pct(item["share"], 1.0))
        for item in commits["authors"]
    ]
    lines.append("### 贡献者 Top {}".format(len(author_rows)))
    lines.append("")
    lines.append(table(["作者", "提交数", "占比"], author_rows))
    lines.append("")

    year_rows = [(item["year"], human_int(item["count"])) for item in commits["by_year"]]
    lines.append("### 按年份提交数")
    lines.append("")
    lines.append(table(["年份", "提交数"], year_rows))
    lines.append("")

    lines.append("## 4. 工程治理清单")
    lines.append("")
    gov_rows = []
    for check in health["checks"]:
        gov_rows.append(
            (
                check["label"],
                "✅" if check["ok"] else "❌",
                check["evidence"],
            )
        )
    lines.append(table(["检查项", "状态", "证据"], gov_rows))
    lines.append("")

    lines.append("## 5. 变更热点与测试联动")
    lines.append("")
    if commits["churn"]:
        churn_rows = [
            ("`{}`".format(item["path"]), human_int(item["commits"]), pct(item["share"], 1.0))
            for item in commits["churn"][:10]
        ]
        lines.append(table(["文件", "改动提交数", "占全部提交"], churn_rows))
        lines.append("")
    lines.append(
        "有 {} 个提交（{:.1f}%）同时改动了测试文件，可作为「测试是否跟随代码」的粗略信号。".format(
            human_int(commits["test_touching_commits"]),
            commits["test_touch_ratio"] * 100,
        )
    )
    lines.append("")

    lines.append("## 6. 健康度评分：**{}/100**".format(health["score"]))
    lines.append("")
    score_rows = [
        (
            check["label"],
            "{}/{}".format(check["earned"], check["points"]),
            check["evidence"],
        )
        for check in health["checks"]
    ]
    lines.append(table(["维度", "得分", "证据"], score_rows))
    lines.append("")
    lines.append("### 发现")
    lines.append("")
    for finding in health["findings"]:
        lines.append("- " + finding)
    lines.append("")

    lines.append("## 附：指标口径")
    lines.append("")
    lines.append("- 提交统计使用 `git log` 的 committer date，工作区状态取 `git status --porcelain`。")
    lines.append("- 行数为纯文本文件按 `\\n` 计数的结果；含 NUL 字节的前 8KB 片段视为二进制并跳过行数。")
    lines.append("- 测试文件按路径匹配 `tests/`、`test_*.py`、`*_test.go`、`*.test.js` 等常见约定。")
    lines.append("- 变更热点按历史路径统计，不追踪 `git mv` 重命名，因此旧路径可能单独出现。")
    lines.append("- 贡献者按 author name 去重，同一人的不同署名会被计为多人。")
    lines.append("- 「过期远程分支」指超过 {} 天未更新、且不是默认分支的 `origin/*` 分支。".format(branches["stale_days"]))
    lines.append("- 健康度是启发式评分，只用于横向比较与发现缺口，不代表代码质量本身。")
    lines.append("")
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description="零依赖 Git 仓库结构分析器：输出 Markdown 报告与 JSON 指标。",
    )
    parser.add_argument("repo", help="本地 Git 仓库路径")
    parser.add_argument("--out-md", help="Markdown 报告输出路径（默认打印到 stdout）")
    parser.add_argument("--out-json", help="JSON 指标输出路径")
    parser.add_argument("--top", type=int, default=10, help="Top N 数量，默认 10")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=180,
        help="远程分支多少天未更新算过期，默认 180",
    )
    parser.add_argument(
        "--now",
        help="用于计算年龄的基准时间（ISO-8601），便于复现历史报告",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="只写文件，不向 stdout 打印 Markdown",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    now = None
    if args.now:
        try:
            now = parse_iso(args.now)
        except ValueError:
            print("错误：--now 需要 ISO-8601 时间，例如 2026-11-10T23:30:19+08:00", file=sys.stderr)
            return 2

    try:
        metrics = inspect_repo(args.repo, top_n=args.top, stale_days=args.stale_days, now=now)
    except GitError as exc:
        print("错误：{}".format(exc), file=sys.stderr)
        return 2

    markdown = render_markdown(metrics)
    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.out_md:
        out_path = Path(args.out_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown + "\n", encoding="utf-8")
    if not args.quiet and not args.out_md:
        print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
