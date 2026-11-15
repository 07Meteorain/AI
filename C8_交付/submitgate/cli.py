"""命令行入口：``python -m submitgate check``。

默认参数是「在交付目录里直接敲一条命令」就能跑：

- 课程记录默认用随交付附带的 ``challenges/`` 快照（助教 clone 后无需另找数据）；
- 仓库默认用本交付目录的上一级（即仓库根）；
- 报告默认写到 ``reports/``。

退出码：``0`` 门禁通过、``1`` 有缺口/红旗、``2`` 用法或环境错误 —— 可直接当 CI 门禁。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

from . import __version__
from .challenge import load_challenge, parse_deliverables
from .checks import evaluate_challenge
from .engine import ToolError, run
from .report import to_html, to_json, to_markdown

PKG_DIR = Path(__file__).resolve().parent
DELIVERY_DIR = PKG_DIR.parent
DEFAULT_COURSE = DELIVERY_DIR / "challenges"
DEFAULT_REPO = DELIVERY_DIR.parent
DEFAULT_OUT = DELIVERY_DIR / "reports"
DEFAULT_MAPPING = DELIVERY_DIR / "mapping.json"
DEFAULT_GITHUB_BASE = os.environ.get(
    "SUBMITGATE_GITHUB_BASE", "https://github.com/07Meteorain/AI/tree/master"
)

EXIT_OK = 0
EXIT_GATE_FAIL = 1
EXIT_ERROR = 2


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="submitgate",
        description="挑战交付验收门禁：必需交付物齐全性 + 评分维度信号 + 红旗封顶",
    )
    parser.add_argument("--version", action="version", version=f"submitgate {__version__}")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="跑一次完整检查并生成报告")
    check.add_argument("--course", type=Path, default=DEFAULT_COURSE, help="课程记录根目录（含 <Cx>/challenge.json）")
    check.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="交付仓库根目录")
    check.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING, help="别名映射 JSON（可不存在）")
    check.add_argument("--out", type=Path, default=DEFAULT_OUT, help="报告输出目录")
    check.add_argument(
        "--formats",
        default="md,json,html",
        help="输出格式，逗号分隔：md,json,html（默认全出）",
    )
    check.add_argument("--github-base", default=DEFAULT_GITHUB_BASE, help="报告中文件链接前缀；传空串则输出纯路径")
    check.add_argument("--quiet", action="store_true", help="只输出结论，不打印逐挑战行")

    sub.add_parser("selftest", help="环境自检 + 在一个临时样例上跑通全流程")
    sub.add_parser("version", help="打印版本")
    return parser


def _cmd_check(args: argparse.Namespace) -> int:
    formats = {item.strip().lower() for item in (args.formats or "").split(",") if item.strip()}
    unknown = formats - {"md", "json", "html"}
    if unknown:
        raise ToolError("不支持的格式：" + "、".join(sorted(unknown)))

    report = run(args.course, args.repo, args.mapping)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    base = (args.github_base or "").strip() or None
    if "md" in formats:
        path = out_dir / "交付验收报告.md"
        path.write_text(to_markdown(report, base), encoding="utf-8")
        written.append(path)
    if "json" in formats:
        path = out_dir / "交付验收报告.json"
        path.write_text(to_json(report), encoding="utf-8")
        written.append(path)
    if "html" in formats:
        path = out_dir / "导航站.html"
        path.write_text(to_html(report, base), encoding="utf-8")
        written.append(path)

    if not args.quiet:
        print(f"submitgate {report.tool_version} · {report.total} 个挑战 · 仓库 HEAD {report.git_head or '—'}")
        print(f"课程记录：{report.course_root}")
        print(f"交付仓库：{report.repo_root}")
        print("-" * 72)
        for item in report.evaluations:
            missing = len(item.missing)
            total = len(item.deliverables)
            flags = ",".join(flag.id for flag in item.flags) or "-"
            print(
                f"[{'PASS' if item.passed else 'FAIL'}] {item.challenge.source_id:<5} "
                f"必需 {total - missing}/{total}  红旗 {flags:<34} "
                f"可验证 {item.total_score}/{item.max_score}（{len(item.covered_dimensions)}/{len(item.dimensions)} 维）"
            )
        print("-" * 72)
        if report.missing_delivery:
            print("无交付目录：" + "、".join(item.challenge.source_id for item in report.missing_delivery))
        if report.required_missing:
            print(f"缺失必需交付物：{report.required_missing}/{report.required_total} 项")

    for path in written:
        print(f"报告：{path}")
    verdict = "PASS" if report.gate_ok else "FAIL"
    print(f"结论：{verdict}（{len(report.passed)}/{report.total} 挑战通过；估算总分 {report.score}/{report.max_score}，非成绩）")
    return EXIT_OK if report.gate_ok else EXIT_GATE_FAIL


def _cmd_selftest(_: argparse.Namespace) -> int:
    """不依赖仓库真实数据：现场造一个最小课程 + 交付目录，跑通并断言结果。"""

    print(f"submitgate {__version__} 自检")
    print(f"python      : {platform.python_version()} ({platform.platform()})")
    print(f"交付目录    : {DELIVERY_DIR}")
    print(f"默认课程记录: {DEFAULT_COURSE}（存在={DEFAULT_COURSE.is_dir()}）")
    print(f"默认仓库根  : {DEFAULT_REPO}（存在={DEFAULT_REPO.is_dir()}）")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        course = root / "course"
        repo = root / "repo"
        delivery = repo / "C9_交付"
        (course / "C9").mkdir(parents=True)
        delivery.mkdir(parents=True)
        record = {
            "source_id": "C9",
            "challenge_id": "ch-selftest",
            "title": "自检样例",
            "deadline": "2099-12-31T23:59",
            "required_deliverables": "*proposal*,*AI日志*",
            "rubric_dimensions": json.dumps(
                {
                    "dimensions": [
                        {"id": "delivery", "label": "交付质量", "maxPoints": 25},
                        {"id": "artifactCompleteness", "label": "产物完整性", "maxPoints": 15},
                        {"id": "aiUsage", "label": "AI使用质量", "maxPoints": 20},
                        {"id": "reflectionQuality", "label": "复盘质量", "maxPoints": 20},
                    ]
                }
            ),
            "red_flags": json.dumps({"flags": [{"id": "missing_artifacts", "affects": "artifactCompleteness", "maxScore": 5}]}),
        }
        (course / "C9" / "challenge.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        (delivery / "proposal.md").write_text("# 提案\n\n" + "内容。" * 200, encoding="utf-8")
        (delivery / "README.md").write_text("# 说明\n\n## 快速开始\n\n```bash\npython -m demo\n```\n", encoding="utf-8")
        (delivery / "tests").mkdir()
        (delivery / "tests" / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

        challenge = load_challenge(course / "C9" / "challenge.json")
        assert challenge.source_id == "C9"
        assert [d.name for d in parse_deliverables(record["required_deliverables"])] == ["proposal", "AI日志"]

        evaluation = evaluate_challenge(challenge, delivery)
        assert "AI日志" in evaluation.missing, evaluation.missing
        assert evaluation.passed is False
        assert any(flag.id == "missing_artifacts" for flag in evaluation.flags)
        assert evaluation.total_score < evaluation.max_score

    print("自检通过：解析 / 匹配 / 缺失判定 / 红旗封顶 全部符合预期")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "version":
        print(f"submitgate {__version__}")
        return EXIT_OK
    if args.command == "selftest":
        return _cmd_selftest(args)
    if args.command == "check":
        try:
            return _cmd_check(args)
        except ToolError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return EXIT_ERROR
    parser.print_help()
    return EXIT_ERROR
