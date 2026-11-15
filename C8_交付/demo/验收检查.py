#!/usr/bin/env python
"""验收检查：读本目录里已生成的报告，逐条核对 docs/验收标准.md 的 AC/质量门槛。

用法（在 C8_交付/ 下）：
    python demo/验收检查.py

它不重新跑门禁，只检查「报告与产物本身」是否满足承诺 —— 跑门禁请用
`python -m submitgate check`。退出码 0 = 全部通过，1 = 有不符合项。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"

results: list[tuple[str, bool, str]] = []


def check(item: str, ok: bool, detail: str) -> None:
    results.append((item, ok, detail))


def main() -> int:
    report_path = DEMO / "交付验收报告.json"
    md_path = DEMO / "交付验收报告.md"
    html_path = DEMO / "导航站.html"

    for path in (report_path, md_path, html_path):
        check(f"产物存在：{path.name}", path.is_file(), f"{path.stat().st_size if path.is_file() else 0} 字节")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report["summary"]
    challenges = report["challenges"]

    check("AC1 报告由真实仓库生成", report["repo_root"] not in ("", "."), f"repo_root={report['repo_root']}")
    check("AC2 挑战数 = 11", summary["challenges"] == 11, f"{summary['challenges']} 个")
    check(
        "AC2 必需交付物逐条有结论",
        summary["required_total"] == 40,
        f"{summary['required_total']} 条（缺 {summary['required_missing']}）",
    )
    check("AC3 覆盖维度已单列", summary["covered_dimensions"] > 0, f"{summary['covered_dimensions']}/{summary['total_dimensions']}")
    check(
        "AC3 存在「需人工」维度（不假装能评）",
        any(dim["covered"] is False for ch in challenges for dim in ch["dimensions"]),
        "至少一个维度未覆盖",
    )
    c8 = next((ch for ch in challenges if ch["source_id"] == "C8"), None)
    check("Q2 C8 自检 PASS", bool(c8 and c8["status"] == "PASS"), f"C8 状态={c8['status'] if c8 else '缺失'}")
    check(
        "Q2 C8 必需交付物 4/4",
        bool(c8 and len(c8["missing"]) == 0),
        "4 条全部命中" if c8 else "无 C8 记录",
    )
    check(
        "AC2 每条缺失都点名",
        all(ch["missing"] for ch in challenges if ch["status"] == "FAIL"),
        f"{sum(1 for ch in challenges if ch['status'] == 'FAIL')} 个 FAIL 均有缺失名单",
    )
    check(
        "Q4 每条 ✗ 都有可核对对象",
        all(
            (check_item["evidence"] or check_item["detail"])
            for ch in challenges
            for check_item in ch["checks"]
            if check_item["status"] == "fail"
        ),
        "fail 项均给出证据路径或缺失对象名",
    )
    check("红旗规则存在", any(ch["red_flags"] for ch in challenges), f"{summary['red_flags']} 处红旗")

    html = html_path.read_text(encoding="utf-8")
    check("AC7 HTML 无外部脚本", "<script src" not in html, "")
    check("AC7 HTML 无 CDN/外链 http", "http://" not in html, "")
    check("AC7 HTML 内联样式", "<style>" in html, f"{len(html)} 字符")
    check("AC7 HTML 单文件 > 50KB", len(html) > 50_000, f"{len(html)} 字符")

    md = md_path.read_text(encoding="utf-8")
    for section in ("## 一、总览", "## 二、缺口清单", "## 三、逐挑战明细", "## 五、方法与边界"):
        check(f"报告结构：{section}", section in md, "")

    required_files = [
        ROOT / "07Meteorain_C8_proposal.md",
        ROOT / "07Meteorain_C8_AAR_W.md",
        ROOT / "07Meteorain_C8_AI日志.md",
        ROOT / "07Meteorain_C8_拿来说明.md",
    ]
    for path in required_files:
        check(f"必需交付物：{path.name}", path.is_file() and path.stat().st_size > 1000, "")

    width = max(len(item) for item, _, _ in results)
    passed = 0
    for item, ok, detail in results:
        mark = "✓" if ok else "✗"
        print(f"{mark} {item:<{width}}  {detail}")
        passed += 1 if ok else 0

    print()
    print(f"{passed}/{len(results)} 项通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
