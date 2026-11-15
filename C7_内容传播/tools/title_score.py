#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标题评分器（Python 侧实现）。

设计约束：
  1. 评分是**确定性**的 —— 同一份 `数据/title_rubric.json` 驱动 Python 与 JS 两套实现，
     两边必须给出完全相同的分数。JS 侧在 app/js/core/titlescore.js，一致性由
     tests/titlescore-parity.test.js 保证。
  2. 报告里的每个数字都由本脚本产出，不允许手打。跑法：
         python tools/title_score.py            # 生成 CSV + Markdown 评分表
         python tools/title_score.py --check    # 只校验已提交的产物是否仍然一致（CI 用）

用法：
    python tools/title_score.py [--root .] [--check]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

GRADE_ORDER = ["弃用", "备选", "可用", "主推"]


def load_rubric(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def effective_length(title: str) -> int:
    """有效字符数：去掉空白后计算。用空白撑长度不算本事。"""
    return len(re.sub(r"\s+", "", title))


def _hits(kind: str, value, title: str) -> int:
    if kind == "regex":
        return 1 if re.search(value, title) else 0
    if kind == "regexCount":
        return len(re.findall(value, title))
    if kind == "words":
        return 1 if any(w in title for w in value) else 0
    if kind == "wordCount":
        return sum(title.count(w) for w in value)
    raise ValueError(f"unknown rule kind: {kind}")


def _apply_rule(rule: dict, title: str) -> tuple[int, int]:
    """返回 (实际得分, 命中次数)。cap 对正分是上限，对负分是下限。"""
    hits = _hits(rule["kind"], rule["value"], title)
    if hits == 0:
        return 0, 0
    points = rule["points"]
    cap = rule["cap"]
    raw = points * hits
    contrib = min(raw, cap) if points >= 0 else max(raw, cap)
    return contrib, hits


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def score_title(title: str, rubric: dict) -> dict:
    """返回 {hook, specificity, searchability, platformFit, credibility, total, reasons}"""
    reasons: list[str] = []
    dims = {d["id"]: d["max"] for d in rubric["dimensions"]}
    scores: dict[str, int] = {}

    # --- 正向维度：base + Σ 规则（逐条 cap，最后 clamp 到维度上限） ---
    for dim in ("hook", "specificity", "searchability"):
        spec = rubric[dim]
        total = spec["base"]
        for rule in spec["rules"]:
            contrib, hits = _apply_rule(rule, title)
            if contrib:
                total += contrib
                reasons.append(f"{dim}:{rule['label']}({contrib:+d})")
        scores[dim] = _clamp(total, 0, dims[dim])

    # --- platformFit：长度分档 + 扣分项 ---
    spec = rubric["platformFit"]
    length = effective_length(title)
    band_score = 0
    band_label = ""
    for band in spec["bands"]:
        if band["minLength"] <= length <= band["maxLength"]:
            band_score, band_label = band["score"], band["label"]
            break
    fit = band_score
    reasons.append(f"platformFit:{band_label}({band_score})")
    for rule in spec["penalties"]:
        contrib, _ = _apply_rule(rule, title)
        if contrib:
            fit += contrib
            reasons.append(f"platformFit:{rule['label']}({contrib:+d})")
    scores["platformFit"] = _clamp(fit, 0, dims["platformFit"])

    # --- credibility：base - 扣分 + 加分 ---
    spec = rubric["credibility"]
    cred = spec["base"]
    for rule in spec["penalties"]:
        contrib, _ = _apply_rule(rule, title)
        if contrib:
            cred += contrib
            reasons.append(f"credibility:{rule['label']}({contrib:+d})")
    for rule in spec["bonuses"]:
        contrib, _ = _apply_rule(rule, title)
        if contrib:
            cred += contrib
            reasons.append(f"credibility:{rule['label']}({contrib:+d})")
    scores["credibility"] = _clamp(cred, 0, dims["credibility"])

    total = sum(scores.values())
    total = _clamp(total, 0, sum(dims.values()))

    # --- 一票否决：标题党/绝对化用词不给辩解空间 ---
    veto = rubric.get("veto") or {}
    vetoed = any(w in title for w in veto.get("words", []))
    if vetoed:
        total = min(total, veto["cap"])
        reasons.append(f"veto:{veto['label']}(封顶 {veto['cap']})")

    scores["total"] = total
    thresholds = rubric["thresholds"]
    if vetoed:
        grade = "弃用"
    elif total >= thresholds["strong"]:
        grade = "主推"
    elif total >= thresholds["usable"]:
        grade = "可用"
    elif total >= thresholds["weak"]:
        grade = "备选"
    else:
        grade = "弃用"
    scores["grade"] = grade
    scores["chars"] = length
    scores["reasons"] = "; ".join(reasons)
    return scores


def read_titles(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


SCORED_HEADER = [
    "id", "formula", "title", "chars",
    "hook", "specificity", "searchability", "platformFit", "credibility",
    "total", "grade", "reasons",
]


def build_scored(rows: list[dict], rubric: dict) -> list[dict]:
    out = []
    for row in rows:
        s = score_title(row["title"], rubric)
        out.append({
            "id": row["id"],
            "formula": row["formula"],
            "title": row["title"],
            "chars": s["chars"],
            "hook": s["hook"],
            "specificity": s["specificity"],
            "searchability": s["searchability"],
            "platformFit": s["platformFit"],
            "credibility": s["credibility"],
            "total": s["total"],
            "grade": s["grade"],
            "reasons": s["reasons"],
        })
    out.sort(key=lambda r: (-r["total"], -r["specificity"], -r["hook"], r["id"]))
    return out


def render_csv(scored: list[dict]) -> str:
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=SCORED_HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerows(scored)
    return buf.getvalue()


def render_markdown(scored: list[dict], rubric: dict) -> str:
    dims = rubric["dimensions"]
    head = "| 排名 | ID | 标题 | " + " | ".join(f"{d['label']}({d['max']})" for d in dims) + " | 总分 | 评级 |"
    sep = "| ---: | --- | --- | " + " | ".join("---:" for _ in dims) + " | ---: | --- |"
    lines = [
        "<!-- 本文件由 tools/title_score.py 生成，请勿手改。改评分口径请改 数据/title_rubric.json。 -->",
        "",
        "| 排名 | ID | 标题 | " + " | ".join(f"{d['label']}({d['max']})" for d in dims) + " | 总分 | 评级 |",
        "| ---: | --- | --- | " + " | ".join("---:" for _ in dims) + " | ---: | --- |",
    ]
    for i, row in enumerate(scored, 1):
        cells = [row["hook"], row["specificity"], row["searchability"], row["platformFit"], row["credibility"]]
        lines.append(
            f"| {i} | {row['id']} | {row['title']} | "
            + " | ".join(str(c) for c in cells)
            + f" | **{row['total']}** | {row['grade']} |"
        )
    lines.append("")
    lines.append(
        f"共 {len(scored)} 条候选；评级阈值：主推 ≥ {rubric['thresholds']['strong']}，"
        f"可用 ≥ {rubric['thresholds']['usable']}，备选 ≥ {rubric['thresholds']['weak']}，其余弃用。"
    )
    return "\n".join(lines) + "\n"


def render_fixture(scored: list[dict]) -> str:
    """给 JS 侧对照用的最小 fixture：只保留分数，不保留理由（理由文案两边不必一致）。"""
    rows = [
        {k: row[k] for k in ("id", "title", "hook", "specificity", "searchability",
                             "platformFit", "credibility", "total", "grade")}
        for row in scored
    ]
    rows.sort(key=lambda r: r["id"])
    return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台默认 GBK，会把中文打成乱码
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="标题评分器")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--check", action="store_true", help="只校验产物是否与当前 rubric 一致")
    args = parser.parse_args(argv)

    root = Path(args.root)
    rubric = load_rubric(root / "数据" / "title_rubric.json")
    rows = read_titles(root / "数据" / "titles.csv")
    scored = build_scored(rows, rubric)
    csv_text = render_csv(scored)
    md_text = render_markdown(scored, rubric)

    csv_path = root / "数据" / "titles_scored.csv"
    md_path = root / "数据" / "标题评分表.md"
    fixture_path = root / "tests" / "fixtures" / "title_scores.json"
    fixture_text = render_fixture(scored)

    if args.check:
        stale = []
        if not csv_path.exists() or csv_path.read_text(encoding="utf-8") != csv_text:
            stale.append(csv_path.name)
        if not md_path.exists() or md_path.read_text(encoding="utf-8") != md_text:
            stale.append(md_path.name)
        if not fixture_path.exists() or fixture_path.read_text(encoding="utf-8") != fixture_text:
            stale.append("tests/fixtures/title_scores.json")
        if stale:
            print(f"[stale] {', '.join(stale)} 与 rubric/titles.csv 不一致，请重跑 tools/title_score.py", file=sys.stderr)
            return 1
        print(f"[ok] {len(scored)} 条标题评分产物一致（含 JS 侧 fixture）")
        return 0

    csv_path.write_text(csv_text, encoding="utf-8", newline="")
    md_path.write_text(md_text, encoding="utf-8", newline="")
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(fixture_text, encoding="utf-8", newline="")
    best = scored[0]
    print(f"[ok] scored {len(scored)} titles -> {csv_path.name}, {md_path.name}, tests/fixtures/title_scores.json")
    print(f"     top: {best['id']} {best['total']} 分 {best['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
