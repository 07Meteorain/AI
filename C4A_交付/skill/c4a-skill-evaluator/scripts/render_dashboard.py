#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_dashboard.py — 把 evaluation.json 渲染成交互式HTML 仪表板（Level 4 可视化）

输入：reports/evaluation.json（评审器产出）
输出：reports/Meteorain_C4A_评审仪表板.html（单文件，无外部依赖，双击即开）

为什么要有它：
    Markdown 报告适合逐条核对，Excel 适合筛选，但都不适合"一眼看到全班分布"。
    这份 HTML 把四条件达成度、完整性缺口、排名做成可视化，
    老师在群里发一个链接，全班同学立刻知道自己在哪一格。

用法：
    python render_dashboard.py reports/evaluation.json -o reports/dashboard.html
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path

CRITERIA_ORDER = [("reusable", "可复用"), ("executable", "可执行"),
                ("verifiable", "可验证"), ("clear_io", "IO 明确")]
GRADE_COLORS = {"✅": "#16a34a", "⚠️": "#d97706", "❌": "#dc2626"}

TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>C4 提交自动评审仪表板</title>
<style>
  :root {{
    --bg:#f6f7f9; --card:#ffffff; --line:#e3e6ea; --ink:#1a1d21;
    --muted:#6b7280; --brand:#2f5496; --ok:#16a34a; --warn:#d97706; --bad:#dc2626;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px 20px; background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
    line-height:1.6; }}
  .wrap {{ max-width:1080px; margin:0 auto; }}
  header {{ margin-bottom:24px; }}
  h1 {{ margin:0 0 6px; font-size:26px; letter-spacing:-.3px; }}
  .sub {{ color:var(--muted); font-size:14px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
    padding:22px; margin-bottom:18px; }}
  h2 {{ margin:0 0 16px; font-size:17px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
  .kpi .n {{ font-size:28px; font-weight:650; letter-spacing:-.5px; }}
  .kpi .l {{ color:var(--muted); font-size:13px; margin-top:2px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th,td {{ padding:10px 12px; text-align:left; border-bottom:1px solid var(--line);
    vertical-align:middle; }}
  th {{ color:var(--muted); font-weight:600; font-size:12.5px;
    text-transform:uppercase; letter-spacing:.4px; }}
  tbody tr:last-child td {{ border-bottom:none; }}
  .bar {{ height:9px; background:#eceff3; border-radius:5px; overflow:hidden;
    min-width:110px; }}
  .bar > span {{ display:block; height:100%; border-radius:5px; }}
  .g {{ font-weight:650; }}
  .chips {{ display:flex; gap:5px; flex-wrap:wrap; }}
  .chip {{ font-size:12px; padding:2px 9px; border-radius:20px; color:#fff;
    white-space:nowrap; }}
  details {{ margin-top:12px; }}
  summary {{ cursor:pointer; color:var(--brand); font-size:13.5px; }}
  .ev {{ font-family:ui-monospace,Consolas,monospace; font-size:12px; color:var(--muted);
    margin-top:5px; }}
  footer {{ color:var(--muted); font-size:12.5px; text-align:center; padding:18px 0; }}
  .tag {{ display:inline-block; font-size:11.5px; padding:1px 8px; border-radius:20px;
    border:1px solid var(--line); color:var(--muted); }}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>C4 提交自动评审仪表板</h1>
  <div class="sub">由 <code>c4a_evaluator.py</code> 自动生成 · {ts}</div>
</header>

<div class="kpis">{kpis}</div>

<div class="card">
  <h2>四条件班级达成度</h2>
  <table><thead><tr>
    <th>条件</th><th>平均达成度</th><th>分布</th><th>评级构成</th>
  </tr></thead><tbody>{dims}</tbody></table>
</div>

<div class="card">
  <h2>综合排名</h2>
  <table><thead><tr>
    <th>#</th><th>作者</th><th>完整性</th><th>质量分</th><th>综合分</th>
    <th>四条件评级</th><th>置信度</th>
  </tr></thead><tbody>{ranking}</tbody></table>
</div>

<div class="card">
  <h2>逐作者明细</h2>
  {details}
</div>

<div class="card">
  <h2>五必须文件完整性矩阵</h2>
  <table><thead><tr><th>作者</th>{slot_head}</tr></thead>
  <tbody>{matrix}</tbody></table>
</div>

<footer>
  本仪表板所有结论均可追溯到具体文件与行号；标有 low 置信度的条目建议人工复核。<br>
  排名仅作参考——C4 的评分核心是「被使用次数」，不是机器打分。
</footer>
</div>
</body>
</html>
"""


def _chip(grade: str, score: float | None = None) -> str:
    t = f"{grade} {score:.0%}" if score is not None else grade
    return f'<span class="chip" style="background:{GRADE_COLORS.get(grade, "#6b7280")}">{t}</span>'


def render(data: dict) -> str:
    authors = data["authors"]
    ranked = sorted(authors.items(), key=lambda kv: -kv[1]["composite_score"])
    n = len(ranked) or 1
    avg_q = sum(v["quality_score"] for v in authors.values()) / n
    complete = sum(1 for v in authors.values() if v["completeness_score"] >= 0.8)
    need_review = sum(1 for v in authors.values() if v["confidence"] == "low")

    kpis = f"""
    <div class="kpi"><div class="n">{len(ranked)}</div><div class="l">提交人数</div></div>
    <div class="kpi"><div class="n">{complete}</div><div class="l">完整提交（≥80%）</div></div>
    <div class="kpi"><div class="n">{avg_q:.0%}</div><div class="l">平均质量分</div></div>
    <div class="kpi"><div class="n" style="color:var(--warn)">{need_review}</div>
      <div class="l">需人工复核</div></div>
    <div class="kpi"><div class="n" style="font-size:16px;padding-top:8px">
      {html.escape(data['meta']['level_reached'])}</div><div class="l">达成级别</div></div>
    """

    # 四条件班级均分
    dims = ""
    for cid, label in CRITERIA_ORDER:
        vals = [(next((c for c in v["criteria"] if c["id"] == cid), None))
                for v in authors.values()]
        vals = [c for c in vals if c]
        if not vals:
            continue
        scores = [c["score"] for c in vals]
        avg = sum(scores) / len(scores)
        dist = "".join(_chip(g) for g in ("✅", "⚠️", "❌")
                       for _ in range(sum(1 for c in vals if c["grade"] == g)))
        color = GRADE_COLORS["✅"] if avg >= .7 else (
            GRADE_COLORS["⚠️"] if avg >= .35 else GRADE_COLORS["❌"])
        dims += f"""<tr>
          <td><strong>{label}</strong></td>
          <td><div style="display:flex;align-items:center;gap:10px">
            <div class="bar"><span style="width:{avg*100:.0f}%;background:{color}"></span></div>
            <b>{avg:.0%}</b></div></td>
          <td>{sum(1 for c in vals if c['grade']=='✅')} ✅ /
              {sum(1 for c in vals if c['grade']=='⚠️')} ⚠️ /
              {sum(1 for c in vals if c['grade']=='❌')} ❌</td>
          <td><div class="chips">{dist}</div></td></tr>"""

    # 排名
    ranking = ""
    for i, (name, v) in enumerate(ranked, 1):
        chips = "".join(_chip(c["grade"], c["score"])
                        for c in v["criteria"] if c["id"] in dict(CRITERIA_ORDER))
        cc = v["completeness_score"]
        qc = v["quality_score"]
        ccolor = GRADE_COLORS["✅"] if cc >= .8 else (
            GRADE_COLORS["⚠️"] if cc >= .5 else GRADE_COLORS["❌"])
        conf_color = {"high": "var(--ok)", "medium": "var(--muted)",
                      "low": "var(--bad)"}[v["confidence"]]
        ranking += f"""<tr>
          <td>{i}</td><td><strong>{html.escape(name)}</strong></td>
          <td><div style="display:flex;align-items:center;gap:8px">
            <div class="bar" style="min-width:80px"><span style="width:{cc*100:.0f}%;background:{ccolor}"></span></div>
            <span>{cc:.0%}</span></div></td>
          <td>{qc:.0%}</td><td><strong>{v['composite_score']:.2f}</strong></td>
          <td><div class="chips">{chips}</div></td>
          <td><span class="tag" style="color:{conf_color};border-color:{conf_color}">
            {v['confidence']}</span></td></tr>"""

    # 逐作者明细（含证据）
    details = ""
    for name, v in ranked:
        rows = ""
        for c in v["criteria"]:
            for it in c["items"]:
                mark = "✅" if it["satisfied"] else "❌"
                color = GRADE_COLORS["✅"] if it["satisfied"] else GRADE_COLORS["❌"]
                rows += f"""<tr><td>{it['id']}</td><td>{html.escape(it['name'])}</td>
                  <td class="g" style="color:{color}">{mark}</td>
                  <td>{it['weight']}</td>
                  <td><span class="tag">{it['confidence']}</span></td>
                  <td style="color:var(--muted);font-size:12.5px">
                    {html.escape(it['detail'][:150])}</td></tr>"""
        sug = "".join(f"<li>{html.escape(s)}</li>" for s in v["suggestions"])
        flags = (f'<p style="color:var(--bad);font-size:13px">🚩 '
                 f'{html.escape("；".join(v["flags"]))}</p>') if v["flags"] else ""
        details += f"""<details {'open' if name==ranked[0][0] else ''}>
      <summary><strong>{html.escape(name)}</strong> — 综合 {v['composite_score']:.2f}
        （完整性 {v['completeness_score']:.0%} / 质量 {v['quality_score']:.0%}，
        置信度 {v['confidence']}）</summary>
      {flags}
      <table><thead><tr><th>项</th><th>检查内容</th><th>结果</th><th>权重</th>
        <th>置信度</th><th>判定依据</th></tr></thead><tbody>{rows}</tbody></table>
      <p style="font-size:13.5px;margin-bottom:4px"><strong>下一步行动：</strong></p>
      <ol style="font-size:13.5px">{sug}</ol>
    </details>"""

    # 完整性矩阵
    first = ranked[0][1]["completeness"]
    slot_head = "".join(f"<th>{html.escape(first[k]['label'])}</th>" for k in first)
    matrix = ""
    for name, v in ranked:
        cells = ""
        for k, d in v["completeness"].items():
            color = GRADE_COLORS[d["status"]]
            cells += (f'<td style="text-align:center" title="{html.escape(d["reason"])}">'
                      f'<span class="g" style="color:{color}">{d["status"]}</span></td>')
        matrix += (f'<tr><td><strong>{html.escape(name)}</strong></td>'
                   f'{cells}<td style="text-align:center"><b>'
                   f'{v["completeness_score"]:.0%}</b></td></tr>')

    return TPL.format(
        ts=datetime.now().strftime("%Y-%m-%d %H:%M"),
        kpis=kpis, dims=dims, ranking=ranking, details=details,
        slot_head=slot_head, matrix=matrix,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("-o", "--out", default="dashboard.html")
    args = ap.parse_args()
    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    Path(args.out).write_text(render(data), encoding="utf-8")
    print(f"HTML 仪表板已生成: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())