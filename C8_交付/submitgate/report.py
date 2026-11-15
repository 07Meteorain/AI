"""报告渲染：同一份评估结果，输出三种形态。

- JSON：给脚本/CI 用，字段稳定；
- Markdown：给人逐条核对用，助教可以直接在 GitHub 上读；
- HTML：单文件、零外部资源、双击即开，给「不想装任何东西」的人用。
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from .engine import Report

STATUS_ICON = {"pass": "✓", "fail": "✗", "unverified": "–"}


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "—"


def _rel(report: Report, path: Path | None) -> str:
    if path is None:
        return "—"
    try:
        return Path(path).relative_to(report.repo_root).as_posix()
    except ValueError:
        return str(path)


def _link(base: str | None, rel_path: str, label: str | None = None) -> str:
    text = label or rel_path
    if not base:
        return text
    return f"[{text}]({base.rstrip('/')}/{quote(rel_path, safe='/')})"


# ---------------------------------------------------------------- JSON


def _challenge_dict(report: Report, item) -> dict[str, Any]:
    dir_rel = _rel(report, item.delivery_dir)

    def repo_path(rel: str) -> str:
        return f"{dir_rel}/{rel}" if dir_rel and dir_rel != "—" else rel

    return {
        "source_id": item.challenge.source_id,
        "challenge_id": item.challenge.challenge_id,
        "title": item.challenge.title,
        "deadline": item.challenge.deadline,
        "status": item.status,
        "delivery_dir": dir_rel,
        "file_count": len(item.files),
        "missing": item.missing,
        "score": item.total_score,
        "max_score": item.max_score,
        "full_score": item.full_score,
        "covered_dimensions": len(item.covered_dimensions),
        "total_dimensions": len(item.dimensions),
        "dimensions": [
            {
                "id": dim.id,
                "label": dim.label,
                "max_points": dim.max_points,
                "score": dim.score,
                "pass_ratio": round(dim.pass_ratio, 3),
                "covered": dim.covered,
                "coverage_note": dim.coverage_note,
                "capped": dim.capped,
                "cap_reason": dim.cap_reason,
            }
            for dim in item.dimensions
        ],
        "deliverables": [
            {
                "raw": out.deliverable.raw,
                "name": out.deliverable.name,
                "wildcard": out.deliverable.wildcard,
                "ok": out.ok,
                "note": out.note,
                "files": [repo_path(hit.rel) for hit in out.hits[:8]],
            }
            for out in item.deliverables
        ],
        "red_flags": [
            {
                "id": flag.id,
                "description": flag.description,
                "dimension": flag.dimension,
                "max_score": flag.max_score,
                "detail": flag.detail,
            }
            for flag in item.flags
        ],
        "checks": [
            {
                "id": check.id,
                "label": check.label,
                "dimension": check.dimension,
                "weight": check.weight,
                "status": check.status,
                "detail": check.detail,
                "evidence": check.evidence,
            }
            for check in item.checks
        ],
        "notes": item.notes,
    }


def to_dict(report: Report) -> dict[str, Any]:
    return {
        "tool": "submitgate",
        "version": report.tool_version,
        "generated_at": report.generated_at.isoformat(timespec="seconds"),
        "course_root": str(report.course_root),
        "repo_root": str(report.repo_root),
        "git_head": report.git_head,
        "summary": {
            "challenges": report.total,
            "passed": len(report.passed),
            "failed": len(report.failed),
            "missing_delivery": len(report.missing_delivery),
            "red_flags": report.flag_count,
            "required_total": report.required_total,
            "required_missing": report.required_missing,
            "score": report.score,
            "max_score": report.max_score,
            "full_score": report.full_score,
            "covered_dimensions": report.covered_dimensions,
            "total_dimensions": report.total_dimensions,
            "gate": "PASS" if report.gate_ok else "FAIL",
        },
        "challenges": [_challenge_dict(report, item) for item in report.evaluations],
        "orphans": [_rel(report, path) for path in report.mapping.orphans],
        "mapping_notes": list(report.mapping.notes),
    }


def to_json(report: Report) -> str:
    return json.dumps(to_dict(report), ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------- Markdown


def _overview_table(report: Report, base: str | None) -> list[str]:
    lines = [
        "| 挑战 | 状态 | 交付目录 | 必需交付物 | 红旗 | 可验证分 | 覆盖维度 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.evaluations:
        total = len(item.deliverables)
        missing = len(item.missing)
        req = f"{total - missing}/{total}"
        flags = "、".join(flag.id for flag in item.flags) or "—"
        score = f"{item.total_score}/{item.max_score}" if item.max_score else "—"
        coverage = f"{len(item.covered_dimensions)}/{len(item.dimensions)}"
        status = "✅ PASS" if item.passed else "❌ FAIL"
        path = _rel(report, item.delivery_dir)
        dir_cell = _link(base, path) if item.delivery_dir else "—（无目录）"
        lines.append(f"| {item.challenge.source_id} | {status} | {dir_cell} | {req} | {flags} | {score} | {coverage} |")
    return lines


def _gap_section(report: Report) -> list[str]:
    lines = ["## 二、缺口清单（学生自查用）", ""]
    failed = report.failed
    if not failed:
        lines.append("全部挑战的必需交付物齐全、无红旗触发。")
        lines.append("")
        return lines

    lines.append("> 排序：先「连目录都没有」的，再按缺失条数从多到少。")
    lines.append("")
    for item in sorted(failed, key=lambda ev: (ev.delivery_dir is not None, -len(ev.missing), ev.challenge.source_id)):
        name = f"{item.challenge.source_id} · {item.challenge.title}"
        lines.append(f"### {name}")
        lines.append("")
        if item.delivery_dir is None:
            lines.append("- **仓库里没有对应交付目录**，需要在仓库根新建 `Cx_交付/`。")
        if item.missing:
            lines.append("- **缺少必需交付物**：" + "、".join(f"`{name}`" for name in item.missing))
        for flag in item.flags:
            lines.append(f"- **红旗 `{flag.id}`**：{flag.description}（{flag.detail}）→ 该维度封顶 {flag.max_score} 分")
        for check in item.checks:
            if check.status == "fail":
                lines.append(f"- **未通过** `{check.id}`：{check.label} — {check.detail}")
        lines.append("")
    return lines


def _challenge_section(report: Report, item, base: str | None) -> list[str]:
    challenge = item.challenge
    dir_rel = _rel(report, item.delivery_dir)
    lines = [
        f"### {challenge.source_id} · {challenge.title}",
        "",
        f"- 挑战 ID：`{challenge.challenge_id}`",
        f"- 截止时间：{challenge.deadline or '未提供'}",
        f"- 交付目录：{dir_rel}（{len(item.files)} 个文件）",
        f"- 结论：**{'PASS' if item.passed else 'FAIL'}** ｜ 可验证分 {item.total_score}/{item.max_score}"
        f"（{len(item.covered_dimensions)}/{len(item.dimensions)} 个维度可自动验证）",
        "",
        "**必需交付物**",
        "",
        "| 平台要求 | 结论 | 命中文件 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for out in item.deliverables:
        icon = "✅" if out.ok else "❌"
        files = "<br>".join(_link(base, f"{dir_rel}/{hit.rel}", hit.rel) for hit in out.hits[:3]) or "—"
        lines.append(f"| `{out.deliverable.raw}` | {icon} | {files} | {out.note} |")

    lines += ["", "**维度估算**", "", "| 维度 | 得分 | 依据通过率 | 覆盖 | 备注 |", "| --- | --- | --- | --- | --- |"]
    for dim in item.dimensions:
        if not dim.covered:
            lines.append(f"| {dim.label} | — | — | 需人工 | {dim.coverage_note} |")
            continue
        note = dim.cap_reason or ("封顶" if dim.capped else "—")
        lines.append(f"| {dim.label} | {dim.score}/{dim.max_points} | {_pct(dim.pass_ratio)} | 可验证 | {note} |")

    if item.flags:
        lines += ["", "**红旗**", ""]
        for flag in item.flags:
            lines.append(f"- `{flag.id}` {flag.description} — {flag.detail}（封顶 {flag.max_score} 分）")

    lines += ["", "<details><summary>检查明细（点开看证据）</summary>", "", "| # | 检查项 | 权重 | 结论 | 证据 |", "| --- | --- | --- | --- | --- |"]
    for index, check in enumerate(item.checks, start=1):
        icon = {"pass": "✅", "fail": "❌", "unverified": "➖"}[check.status]
        evidence = "<br>".join(_link(base, rel) for rel in check.evidence) or "—"
        lines.append(f"| {index} | {check.label} | {check.weight:g} | {icon} {check.detail} | {evidence} |")
    lines += ["", "</details>", ""]
    if item.notes:
        lines += ["> " + note for note in item.notes] + [""]
    return lines


def to_markdown(report: Report, github_base: str | None = None) -> str:
    lines = [
        "# 挑战交付验收报告",
        "",
        f"> 生成时间：{_fmt_dt(report.generated_at)} ｜ 工具：submitgate {report.tool_version}"
        + (f" ｜ 仓库 HEAD：`{report.git_head}`" if report.git_head else ""),
        f"> 课程记录：`{report.course_root}`",
        f"> 交付仓库：`{report.repo_root}`",
        "",
        "## 一、总览",
        "",
        f"**{report.total} 个挑战**：{len(report.passed)} 个 PASS、{len(report.failed)} 个 FAIL；"
        f"必需交付物缺 {report.required_missing}/{report.required_total} 项；红旗 {report.flag_count} 处；"
        f"可验证维度得分 {report.score}/{report.max_score}。",
        "",
        "> 「可验证分」只覆盖能从文件系统核对的维度："
        f"{report.covered_dimensions}/{report.total_dimensions} 个维度、合计 {report.max_score} 分"
        f"（全部维度满分 {report.full_score} 分）。缺的维度列在「需人工」里，不用 0 分假装算过。",
        "",
        "> 它用来定位该补什么，**不是成绩**。",
        "",
    ]
    lines += _overview_table(report, github_base)
    lines += [""]
    lines += _gap_section(report)
    lines += ["## 三、逐挑战明细", ""]
    for item in report.evaluations:
        lines += _challenge_section(report, item, github_base)
    lines += ["## 四、仓库里没有对应挑战记录的目录", ""]
    if report.mapping.orphans:
        lines.append("> 这些目录有交付内容，但课程记录里没有同名挑战（可能是历史挑战、子挑战，或目录名不规整）。")
        lines.append("")
        for path in report.mapping.orphans:
            lines.append(f"- {_rel(report, path)}")
    else:
        lines.append("无。")
    lines += ["", "## 五、方法与边界", "",
              "1. **只做文件级事实判断**：匹配文件名/路径、统计字符与轮次、读 git 最后提交时间；不评价内容质量、不判断观点对错。",
              "2. **必需交付物匹配规则**：平台写 `*X*` 的按「路径包含 X」匹配（因此 `AI日志/AI使用日志.md` 也算命中 X）；写 `X.md` 的按文件名全等匹配。",
              "3. **维度分是加权通过率**，每项信号的权重与证据都在「检查明细」里，可逐条反驳。",
              "4. **红旗照抄平台规则**：命中即把对应维度封顶，不做加权稀释。",
              "5. **按时交付只用 git 提交时间**：文件 mtime 在 clone 后会被重置，不可信。",
              "6. 本工具不能替代人读：`PASS` 只说明「该有的证据都在」，不说明「写得好」。",
              "",
              "## 六、复跑",
              "",
              "```bash",
              "python -m submitgate check --course <课程记录目录> --repo <仓库根> --out reports",
              "```",
              ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- HTML

_CSS = """
:root { color-scheme: light dark; --bg:#0f1115; --fg:#e8eaed; --muted:#9aa0a6; --card:#171a21;
        --line:#2a2f3a; --pass:#34a853; --fail:#ea4335; --warn:#f9ab00; --accent:#8ab4f8; }
@media (prefers-color-scheme: light) { :root { --bg:#f7f8fa; --fg:#1f2328; --muted:#57606a;
        --card:#ffffff; --line:#d8dee4; --accent:#0969da; } }
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
       font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif; }
.wrap { max-width:1040px; margin:0 auto; }
h1 { font-size:24px; margin:0 0 6px; }
h2 { font-size:18px; margin:34px 0 12px; padding-bottom:6px; border-bottom:1px solid var(--line); }
h3 { font-size:16px; margin:0 0 8px; }
.meta { color:var(--muted); font-size:13px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:18px 0; }
.kpi { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
.kpi b { display:block; font-size:22px; }
.kpi span { color:var(--muted); font-size:12px; }
table { width:100%; border-collapse:collapse; background:var(--card); font-size:14px; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
tr:last-child td { border-bottom:0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin:14px 0; }
.pill { display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; font-weight:600; }
.pill.pass { background:rgba(52,168,83,.16); color:var(--pass); }
.pill.fail { background:rgba(234,67,53,.16); color:var(--fail); }
.pill.skip { background:rgba(154,160,166,.16); color:var(--muted); }
.bar { height:6px; background:var(--line); border-radius:999px; overflow:hidden; margin-top:6px; }
.bar i { display:block; height:100%; background:var(--accent); }
.dims { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-top:12px; }
.dim { border:1px solid var(--line); border-radius:8px; padding:8px 10px; }
.dim b { font-size:13px; }
.dim small { color:var(--muted); }
details { margin-top:10px; }
summary { cursor:pointer; color:var(--accent); font-size:13px; }
code { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12.5px; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.flag { color:var(--warn); }
.gap { border-left:3px solid var(--fail); padding-left:10px; margin:8px 0; }
small.muted { color:var(--muted); }
@media print { body { background:#fff; color:#000; } .kpi,.card,table { border-color:#ccc; } }
"""


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=False)


def _html_link(base: str | None, rel_path: str, label: str | None = None) -> str:
    text = _esc(label or rel_path)
    if not base:
        return f"<code>{_esc(rel_path)}</code>"
    url = f"{base.rstrip('/')}/{quote(rel_path, safe='/')}"
    return f'<a href="{_esc(url)}">{text}</a>'


def to_html(report: Report, github_base: str | None = None) -> str:
    summary = {
        "challenges": report.total,
        "passed": len(report.passed),
        "failed": len(report.failed),
        "missing": report.required_missing,
        "flags": report.flag_count,
        "score": f"{report.score}/{report.max_score}",
        "coverage": f"{report.covered_dimensions}/{report.total_dimensions}",
    }
    rows = []
    for item in report.evaluations:
        pill = "pass" if item.passed else "fail"
        req = f"{len(item.deliverables) - len(item.missing)}/{len(item.deliverables)}"
        dir_cell = _html_link(github_base, _rel(report, item.delivery_dir)) if item.delivery_dir else "—"
        rows.append(
            f'<tr data-status="{"pass" if item.passed else "fail"}">'
            f'<td><b>{_esc(item.challenge.source_id)}</b></td>'
            f'<td><span class="pill {pill}">{"PASS" if item.passed else "FAIL"}</span></td>'
            f"<td>{dir_cell}</td><td>{req}</td>"
            f"<td>{_esc(', '.join(flag.id for flag in item.flags) or '—')}</td>"
            f'<td>{item.total_score}/{item.max_score}<br><small class="muted">'
            f"{len(item.covered_dimensions)}/{len(item.dimensions)} 维</small></td></tr>"
        )

    cards = []
    for item in report.evaluations:
        dir_rel = _rel(report, item.delivery_dir)

        def repo_path(rel: str, dir_rel: str = dir_rel) -> str:
            return f"{dir_rel}/{rel}" if dir_rel and dir_rel != "—" else rel

        dim_html = []
        for dim in item.dimensions:
            if not dim.covered:
                dim_html.append(
                    f'<div class="dim"><b>{_esc(dim.label)}</b> 需人工'
                    f'<br><small>{dim.max_points} 分未计入估算</small></div>'
                )
                continue
            width = int(round(dim.pass_ratio * 100))
            dim_html.append(
                f'<div class="dim"><b>{_esc(dim.label)}</b> {dim.score}/{dim.max_points}'
                f"<br><small>{_pct(dim.pass_ratio)}</small>"
                f'<div class="bar"><i style="width:{width}%"></i></div></div>'
            )
        deliv_rows = []
        for out in item.deliverables:
            icon = '<span class="pill pass">✓</span>' if out.ok else '<span class="pill fail">✗</span>'
            files = "<br>".join(_html_link(github_base, repo_path(hit.rel)) for hit in out.hits[:3]) or "—"
            deliv_rows.append(
                f"<tr><td><code>{_esc(out.deliverable.raw)}</code></td><td>{icon}</td><td>{files}</td>"
                f"<td><small class=\"muted\">{_esc(out.note)}</small></td></tr>"
            )
        flag_html = "".join(
            f'<div class="flag">⚠ 红旗 <code>{_esc(flag.id)}</code>：{_esc(flag.description)} '
            f"— {_esc(flag.detail)}（封顶 {flag.max_score} 分）</div>"
            for flag in item.flags
        )
        check_rows = []
        for check in item.checks:
            pill = {"pass": "pass", "fail": "fail", "unverified": "skip"}[check.status]
            mark = {"pass": "✓", "fail": "✗", "unverified": "–"}[check.status]
            evidence = "<br>".join(_html_link(github_base, rel) for rel in check.evidence) or "—"
            check_rows.append(
                f"<tr><td><span class=\"pill {pill}\">{mark}</span></td><td>{_esc(check.label)}</td>"
                f"<td>{check.weight:g}</td><td>{_esc(check.detail)}</td><td>{evidence}</td></tr>"
            )
        cards.append(
            f'<section class="card" data-status="{"pass" if item.passed else "fail"}" '
            f'id="ch-{_esc(item.challenge.source_id)}">'
            f'<h3>{_esc(item.challenge.source_id)} · {_esc(item.challenge.title)} '
            f'<span class="pill {"pass" if item.passed else "fail"}">'
            f'{"PASS" if item.passed else "FAIL"}</span></h3>'
            f'<div class="meta">交付目录：{_html_link(github_base, _rel(report, item.delivery_dir)) if item.delivery_dir else "—"}'
            f" ｜ {len(item.files)} 个文件 ｜ 估算分 {item.total_score}/{item.max_score}"
            f" ｜ 截止 {_esc(item.challenge.deadline or '—')}</div>"
            f'<div class="dims">{"".join(dim_html)}</div>'
            f"{flag_html}"
            f'<details><summary>必需交付物（{len(item.deliverables)} 项）</summary>'
            f'<table><tr><th>平台要求</th><th>结论</th><th>命中文件</th><th>说明</th></tr>{"".join(deliv_rows)}</table></details>'
            f'<details><summary>检查明细（{len(item.checks)} 项，含证据）</summary>'
            f'<table><tr><th></th><th>检查项</th><th>权重</th><th>结论</th><th>证据</th></tr>{"".join(check_rows)}</table></details>'
            f"</section>"
        )

    gap_items = []
    for item in report.failed:
        parts = []
        if item.delivery_dir is None:
            parts.append("无交付目录")
        if item.missing:
            parts.append("缺：" + "、".join(item.missing))
        for flag in item.flags:
            parts.append(f"红旗 {flag.id}")
        gap_items.append(
            f'<div class="gap"><b>{_esc(item.challenge.source_id)}</b> — {_esc("；".join(parts))}</div>'
        )
    gap_html = "".join(gap_items) or "<p>全部挑战的必需交付物齐全、无红旗触发。</p>"
    orphan_html = "".join(f"<li><code>{_esc(_rel(report, path))}</code></li>" for path in report.mapping.orphans) or "<li>无</li>"
    note_html = "".join(f"<li>{_esc(note)}</li>" for note in report.mapping.notes)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>挑战交付验收报告 · {_esc(report.generated_at.strftime('%Y-%m-%d'))}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
<h1>挑战交付验收报告</h1>
<div class="meta">生成于 {_esc(_fmt_dt(report.generated_at))} ｜ 工具 submitgate {_esc(report.tool_version)}
{(' ｜ HEAD ' + _esc(report.git_head)) if report.git_head else ''} ｜ 课程记录 {_esc(str(report.course_root))}</div>

<div class="cards">
  <div class="kpi"><b>{summary['challenges']}</b><span>挑战总数</span></div>
  <div class="kpi"><b>{summary['passed']}</b><span>PASS</span></div>
  <div class="kpi"><b>{summary['failed']}</b><span>FAIL</span></div>
  <div class="kpi"><b>{summary['missing']}</b><span>缺失必需交付物</span></div>
  <div class="kpi"><b>{summary['flags']}</b><span>红旗触发</span></div>
  <div class="kpi"><b>{summary['score']}</b><span>可验证得分（非成绩）</span></div>
  <div class="kpi"><b>{summary['coverage']}</b><span>可验证维度</span></div>
</div>

<h2>一、总览</h2>
<table>
<tr><th>挑战</th><th>结论</th><th>交付目录</th><th>必需交付物</th><th>红旗</th><th>可验证分</th></tr>
{"".join(rows)}
</table>
<p><small class="muted">「可验证分」只统计能从文件系统核对的维度（合计 {report.max_score} 分，全部维度满分 {report.full_score} 分）。
不能核对的维度列为「需人工」，不按 0 分计入 —— 见各挑战卡片的维度条。</small></p>

<h2>二、缺口清单</h2>
{gap_html}

<h2>三、逐挑战明细</h2>
{''.join(cards)}

<h2>四、仓库里没有对应挑战记录的目录</h2>
<ul>{orphan_html}</ul>
{('<h2>映射说明</h2><ul>' + note_html + '</ul>') if report.mapping.notes else ''}

<h2>五、方法与边界</h2>
<ul>
<li><b>只做文件级事实判断</b>：文件名/路径匹配、字符与轮次统计、git 最后提交时间；不评价内容质量。</li>
<li><b>匹配规则</b>：平台写 <code>*X*</code> 按路径包含匹配；写 <code>X.md</code> 按文件名全等匹配。</li>
<li><b>维度分</b>是加权通过率，权重与证据都在「检查明细」里，可逐条反驳。</li>
<li><b>不能自动验证的维度</b>（如群内参与质量）标为「需人工」，不计 0 分、也不进分子分母。</li>
<li><b>红旗</b>照抄平台规则：命中即把对应维度封顶，不做加权稀释。</li>
<li><b>按时交付</b>只看 git 提交时间（clone 后文件 mtime 会被重置，不可信）。</li>
<li>本页 <code>PASS</code> 只说明「该有的证据都在」，不说明「写得好」。</li>
</ul>

<h2>六、复跑</h2>
<pre><code>python -m submitgate check --course &lt;课程记录目录&gt; --repo &lt;仓库根&gt; --out reports</code></pre>
</div>
</body>
</html>
"""
