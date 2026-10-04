"""
04_build.py — 构建阶段：把译文渲染成可发布的资料包与静态文档站。

产物：
  translations/<doc_id>.md          单篇中文资料（front-matter + 正文 + 原文对照折叠）
  translations/index.md              全部资料索引
  docs/index.html静态文档站首页
  docs/<category>/<doc_id>.html      单篇页面（中英对照可切换）
  docs/assets/style.css              站点样式
  docs/assets/app.js                 交互（对照切换/搜索/目录）
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from common import (
    Glossary, count_words, ensure_dir, load_config, log, ok, read_jsonl,
    sha1, warn, PIPELINE_DIR,
)

# ------------------------------------------------------------------ helpers

def md_to_html(md: str) -> str:
    """极简 Markdown → HTML。只处理我们实际产出的语法子集，不引第三方库。"""
    out, in_code, code_lang = [], False, ""
    lines = md.split("\n")
    i = 0

    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            if not in_code:
                in_code, code_lang = True, ln[3:].strip()
                out.append(f'<pre class="code"><code class="lang-{html.escape(code_lang)}">')
            else:
                in_code = False
                out.append("</code></pre>")
            i += 1
            continue
        if in_code:
            out.append(html.escape(ln))
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lvl = len(m.group(1))
            txt = inline(m.group(2))
            aid = f"h{re.sub(r'[^a-zA-Z0-9]+', '-', m.group(2)).lower()}"
            out.append(f'<h{lvl} id="{aid}">{txt}</h{lvl}>')
            i += 1
            continue
        if re.match(r"^\s*([-*+])\s+", ln):
            out.append("<ul>")
            while i < len(lines) and re.match(r"^\s*([-*+])\s+", lines[i]):
                out.append(f"<li>{inline(re.sub(r'^\s*[-*+]\s+', '', lines[i]))}</li>")
                i += 1
            out.append("</ul>")
            continue
        if re.match(r"^\s*\d+\.\s+", ln):
            out.append("<ol>")
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                out.append(f"<li>{inline(re.sub(r'^\s*\d+\.\s+', '', lines[i]))}</li>")
                i += 1
            out.append("</ol>")
            continue
        if ln.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i+1]):
            out.append("<table>")
            hdr = [c.strip() for c in ln.strip().strip("|").split("|")]
            out.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in hdr) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue
        if ln.startswith("> "):
            out.append("<blockquote>" + inline(ln[2:]) + "</blockquote>")
            i += 1
            continue
        if not ln.strip():
            i += 1
            continue
        out.append(f"<p>{inline(ln)}</p>")
        i += 1
    if in_code:
        out.append("</code></pre>")  # 兜底：修复未闭合
    return "\n".join(out)


def front_matter(d: dict) -> str:
    return (f"---\n"
            f"title: {d.get('title','')}\n"
            f"doc_id: {d.get('doc_id','')}\n"
            f"category: {d.get('category','')}\n"
            f"source: {d.get('src_path','')}\n"
            f"origin: {d.get('origin','')}\n"
            f"translator: AI 机器翻译 + 人工校对（术语表 v1.0）\n"
            f"coverage: {d.get('coverage',0):.0%}\n"
            f"---\n")


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PIPELINE_DIR / "config.json"))
    args = ap.parse_args()
    cfg = load_config(args.config)
    proj = cfg["project"]
    glossary = Glossary.load(proj["glossary"])
    rows = read_jsonl(proj["work_dir"] / "translations.jsonl")
    if not rows:
        warn("没有译文，先跑 02_translate.py")
        return 1

    # 源URL：从离线包的 page_map.json 反查
    page_map = {}
    pm = proj["source_root"] / "CS146S_offline" / "page_map.json"
    if pm.exists():
        for url, fn in json.loads(pm.read_text(encoding="utf-8")).items():
            page_map[fn.replace(".html", "")] = url

    docs_out = ensure_dir(proj["out_dir"])
    site = ensure_dir(proj["site_dir"])
    ensure_dir(site / "assets")

    # 按 doc 分组
    by_doc: dict[str, list[dict]] = {}
    for r in rows:
        by_doc.setdefault(r["doc_id"], []).append(r)

    # ---- 单篇 Markdown
    index_rows = []
    for doc_id, segs in by_doc.items():
        segs.sort(key=lambda s: s["order"])
        meta0 = segs[0]["meta"]
        en_words = sum(s["word_count"] for s in segs if s["kind"] != "code")
        zh_words = sum(count_words(s.get("zh") or "") for s in segs if s["kind"] != "code")
        # 覆盖率 = 已译 Segment 的原文词数 / 全文可译词数。
        # 不要用「中文字数 ÷ 英文字数」——中文天然是英文的 1.5～2 倍，会算出 171% 这种假象。
        done_words = sum(s["word_count"] for s in segs
                         if s["kind"] != "code" and s.get("status") == "translated")
        cov = done_words / en_words if en_words else 0.0
        origin = page_map.get(doc_id, "")
        if not origin:
            if doc_id == "course-homepage":
                origin = "https://themodernsoftware.dev/"
            elif doc_id.endswith("-pdf") or doc_id == "vibe-coding-playbook":
                origin = "(离线 PDF 讲义，无单一 URL)"

        fm = front_matter({"title": meta0.get("title", doc_id), "doc_id": doc_id,
                           "category": meta0.get("category", ""), "src_path": meta0.get("src_path", ""),
                           "origin": origin, "coverage": cov})

        parts = [fm, f"# {meta0.get('title', doc_id)}\n"]
        if origin and not origin.startswith("("):
            parts.append(f"> 原文：[{origin}]({origin})\n")
        if cov < 0.8:
            parts.append(f"> ⚠️ 本篇覆盖率 {cov:.0%}，未译部分以「*（原文待译）*」标注。\n")

        for s in segs:
            if s["kind"] == "code":
                parts.append("```\n" + s["text"] + "\n```")
                continue
            zh = s.get("zh")
            if zh:
                parts.append(zh)
            else:
                parts.append(f"*[原文待译]\n\n> {s['text'][:400]}{'…' if len(s['text'])>400 else ''}*")
            parts.append("")

        (docs_out / f"{doc_id}.md").write_text("\n".join(parts), encoding="utf-8")
        index_rows.append({
            "doc_id": doc_id, "title": meta0.get("title", doc_id),
            "category": meta0.get("category", ""), "priority": meta0.get("priority", 2),
            "origin": origin, "en_words": en_words, "zh_words": zh_words, "coverage": cov,
            "segments": len(segs),
        })

    # ---- 索引 Markdown
    idx = ["# CS146S 课程资料中文包 · 索引\n",
           f"> Stanford CS146S: The Modern Software Developer（Fall 2025）｜共 {len(index_rows)} 篇\n"]
    by_cat: dict[str, list] = {}
    for r in index_rows:
        by_cat.setdefault(r["category"] or "其他", []).append(r)
    for cat, items in sorted(by_cat.items()):
        idx.append(f"\n## {cat}\n")
        idx.append("| 文档 | 原文词数 | 覆盖率 | 一手来源 |")
        idx.append("|---|---|---|---|")
        for it in sorted(items, key=lambda x: -x["en_words"]):
            src = f"[链接]({it['origin']})" if it["origin"].startswith("http") else it["origin"] or "-"
            idx.append(f"| [{it['title']}]({it['doc_id']}.md) | {it['en_words']} | {it['coverage']:.0%} | {src} |")
    (docs_out / "index.md").write_text("\n".join(idx), encoding="utf-8")

    # ---- 站点样式
    (site / "assets" / "style.css").write_text(STYLE, encoding="utf-8")
    (site / "assets" / "app.js").write_text(APP_JS, encoding="utf-8")

    # ---- 站点页面
    qc_path = proj["reports_dir"] / "02_qc.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8")) if qc_path.exists() else {}
    metrics = qc.get("metrics", {})

    for it in index_rows:
        d = ensure_dir(site / "zh" / it["category"].replace("/", "-"))
        segs = by_doc[it["doc_id"]]
        pairs = []
        for s in segs:
            en = s["text"]
            zh = s.get("zh") or ""
            pairs.append(f'<div class="pair" id="{s["seg_id"].replace("#", "-")}">'
                         f'<div class="zh side"><div class="tag">中文</div>{md_to_html(zh) if zh else "<p class=missing>（本段待译）</p>"}</div>'
                         f'<div class="en side"><div class="tag">EN</div>{md_to_html(en)}</div>'
                         f'</div>')
        toc = "".join(
            f'<li><a href="#{s["seg_id"].replace("#","-")}">第 {s["order"]+1} 段</a></li>'
            for s in segs if s["kind"] != "code")
        page = SITE_TPL.format(
            title=html.escape(it["title"]),
            cat=html.escape(it["category"]),
            origin=html.escape(it["origin"]) if it["origin"] else "",
            origin_link=f'<a href="{html.escape(it["origin"])}" target="_blank" rel="noopener">{html.escape(it["origin"])}</a>' if it["origin"].startswith("http") else html.escape(it["origin"]),
            coverage=f"{it['coverage']:.0%}",
            words=f"{it['en_words']:,}",
            toc=toc, body="\n".join(pairs),
            nav=_nav_html(len(glossary)),
        )
        (d / f"{it['doc_id']}.html").write_text(page, encoding="utf-8")
        it["html"] = f"zh/{it['category'].replace('/', '-')}/{it['doc_id']}.html"

    # ---- 术语表页
    rows_t = "".join(
        f'<tr><td><code>{html.escape(t.en)}</code></td><td><b>{html.escape(t.zh)}</b></td>'
        f'<td>{html.escape("、".join(t.aliases))}</td>'
        f'<td class="bad">{html.escape("、".join(t.forbidden))}</td>'
        f'<td>{html.escape(t.category)}</td><td>{html.escape(t.note)}</td></tr>'
        for t in glossary.terms)
    (site / "glossary.html").write_text(SITE_TPL.format(
        title="术语表", cat="附录", origin="", origin_link="—",
        coverage="100%", words=str(len(glossary)),
        toc="", body=f'<div class="pair"><div class="zh side"><div class="tag">术语表</div>'
                     f'<p>共 <b>{len(glossary)}</b> 条，其中带禁用译法规则的 '
                     f'<b>{len(glossary.forbidden_pairs)}</b> 条。'
                     f'"forbidden" 列是QC 脚本全文扫描的硬约束。</p>'
                     f'<table><thead><tr><th>English</th><th>规范译法</th><th>别名</th>'
                     f'<th>禁用译法</th><th>分类</th><th>说明</th></tr></thead><tbody>{rows_t}</tbody></table></div></div>',
        nav=_nav_html(len(glossary)),
    ), encoding="utf-8")

    # ---- 首页
    metrics_cards = "".join(
        f'<div class="card"><div class="num">{v}</div><div class="lbl">{k}</div></div>'
        for k, v in [
            ("收录文档", f"{len(index_rows)}篇"),
            ("原文规模", f"{sum(i['en_words'] for i in index_rows):,} 词"),
            ("译文规模", f"{sum(i['zh_words'] for i in index_rows):,} 字"),
            ("术语条目", f"{len(glossary)} 条"),
            ("词级覆盖率", f"{metrics.get('word_coverage', 0):.0%}"),
            ("文档级覆盖率", f"{metrics.get('doc_coverage', 0):.0%}"),
        ])
    cat_groups: dict[str, list] = {}
    for it in index_rows:
        cat_groups.setdefault(it["category"] or "其他", []).append(it)
    cat_html = ""
    for cat, items in sorted(cat_groups.items()):
        cards = "".join(
            f'<a class="doc" href="{i["html"]}">'
            f'<div class="doc-t">{html.escape(i["title"])}</div>'
            f'<div class="doc-m"><span class="pill">{i["coverage"]:.0%}</span>'
            f'<span class="pill">{i["en_words"]:,} 词</span>'
            f'<span class="pri p{i["priority"]}">P{i["priority"]}</span></div></a>'
            for i in sorted(items, key=lambda x: -x["en_words"]))
        cat_html += f'<section class="cat"><h2>{html.escape(cat)}</h2><div class="grid">{cards}</div></section>'

    (site / "index.html").write_text(HOME_TPL.format(
        metrics=metrics_cards, cats=cat_html,
        glossary_count=len(glossary), doc_count=len(index_rows),
    ), encoding="utf-8")

    ok(f"→ translations/（{len(index_rows)} 篇 .md）")
    ok(f"→ docs/（静态站index.html + {len(index_rows)} 篇页面 + glossary.html）")
    return 0


def _nav_html(glossary_count: int) -> str:
    """子页统一导航。"""
    return (f'<a href="../index.html">← 返回首页</a> · '
            f'<a href="../glossary.html">术语表（{glossary_count} 条）</a>')


# ------------------------------------------------------------------ templates

STYLE = """
:root{--ink:#1a1d21;--ink2:#4a5158;--line:#e3e6ea;--bg:#fbfcfd;--card:#fff;
--zh:#0b6b5b;--en:#7a5c00;--warn:#b4231f;--ok:#0b6b5b;--chip:#eef1f4}
*{box-sizing:border-box}
body{margin:0;font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:var(--bg)}
a{color:#0a58ca;text-decoration:none}a:hover{text-decoration:underline}
header.top{background:#fff;border-bottom:1px solid var(--line);padding:14px 28px;display:flex;gap:18px;align-items:center;position:sticky;top:0;z-index:10}
header.top .logo{font-weight:700;font-size:15px;color:var(--ink)}
header.top nav{margin-left:auto;display:flex;gap:16px;font-size:14px}
.wrap{max-width:1180px;margin:0 auto;padding:26px 28px 80px}
.hero h1{font-size:30px;margin:8px 0 6px}
.hero p.lead{color:var(--ink2);margin:0 0 22px;max-width:760px}
.metrics{display:grid;grid-template-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:22px 0 34px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.card .num{font-size:22px;font-weight:700;color:var(--zh)}
.card .lbl{font-size:12.5px;color:var(--ink2);margin-top:3px}
section.cat{margin:34px 0}
section.cat h2{font-size:17px;padding-bottom:8px;border-bottom:2px solid var(--line);margin:0 0 14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:12px}
a.doc{display:block;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;color:inherit}
a.doc:hover{border-color:var(--zh);box-shadow:0 2px 10px rgba(11,107,91,.09);text-decoration:none}
.doc-t{font-weight:600;font-size:14.5px;line-height:1.5;margin-bottom:9px}
.doc-m{display:flex;gap:6px;flex-wrap:wrap}
.pill{font-size:11.5px;background:var(--chip);color:var(--ink2);border-radius:20px;padding:2px 9px}
.pri{font-size:11.5px;border-radius:20px;padding:2px 9px;font-weight:600}
.p1{background:#fde8e8;color:#9b1c1c}.p2{background:#fff4e0;color:#8a5a00}.p3{background:#eef1f4;color:#4a5158}
.doc-head{background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:22px}
.doc-head h1{font-size:24px;margin:0 0 10px}
.meta{font-size:13px;color:var(--ink2);display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.meta a{word-break:break-all}
.bar{height:7px;background:var(--chip);border-radius:6px;overflow:hidden;margin-top:12px}
.bar>i{display:block;height:100%;background:var(--zh)}
.toolbar{display:flex;gap:10px;align-items:center;margin:0 0 20px;flex-wrap:wrap}
.toolbar button{font:inherit;font-size:13.5px;padding:6px 14px;border:1px solid var(--line);background:#fff;border-radius:7px;cursor:pointer}
.toolbar button.on{background:var(--zh);color:#fff;border-color:var(--zh)}
.pair{border:1px solid var(--line);border-radius:10px;margin-bottom:14px;overflow:hidden;background:var(--card)}
.side{padding:16px 18px}
.side .tag{font-size:11px;font-weight:700;letter-spacing:.06em;padding:2px 8px;border-radius:5px;display:inline-block;margin-bottom:9px}
.zh .tag{background:#e3f3ef;color:var(--zh)}
.en .tag{background:#fdf3dd;color:var(--en)}
.en{border-top:1px dashed var(--line);color:#3c4148}
body.mode-zh .en{display:none}
body.mode-en .zh{display:none}
body.mode-zh .pair{border-color:var(--zh)}
h1,h2,h3,h4{line-height:1.4}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:#f4f6f8;font-weight:600}
code{background:#f1f3f5;padding:1.5px 5px;border-radius:4px;font-size:13px;
font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
pre.code{background:#f7f8fa;border:1px solid var(--line);border-radius:8px;padding:13px 15px;overflow-x:auto;font-size:13px;line-height:1.6}
pre.code code{background:none;padding:0}
blockquote{margin:12px 0;padding:9px 15px;border-left:3px solid var(--line);color:var(--ink2);background:#f8f9fa;border-radius:0 6px 6px 0}
ul,ol{padding-left:24px}
li{margin:4px 0}
.missing{color:var(--warn);font-style:italic}
.bad{color:var(--warn);font-size:12.5px}
footer{max-width:1180px;margin:0 auto;padding:26px 28px 50px;color:var(--ink2);font-size:13px;border-top:1px solid var(--line)}
.toc{position:fixed;right:18px;top:76px;width:132px;font-size:12.5px;max-height:74vh;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:9px;padding:11px 13px}
.toc a{display:block;color:var(--ink2);padding:2px 0}
@media(max-width:1100px){.toc{display:none}}
"""

APP_JS = """
(function(){
  var b=document.querySelectorAll('.toolbar button');
  function set(m){
    document.body.className='mode-'+m;
    b.forEach(function(x){x.classList.toggle('on',x.dataset.m===m)});
    try{localStorage.setItem('c1view',m)}catch(e){}
  }
  b.forEach(function(x){x.addEventListener('click',function(){set(x.dataset.m)})});
  var saved='both';
  try{saved=localStorage.getItem('c1view')||'both'}catch(e){}
  set(saved);
  var q=document.getElementById('q');
  if(q){
    q.addEventListener('input',function(){
      var v=q.value.toLowerCase();
      document.querySelectorAll('.pair').forEach(function(p){
        p.style.display = !v || p.textContent.toLowerCase().indexOf(v)>-1 ? '' : 'none';
      });
    });
  }
})();
"""

SITE_TPL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · CS146S 中文档</title>
<link rel="stylesheet" href="../../assets/style.css"></head>
<body class="mode-both">
<header class="top"><span class="logo">CS146S 中文档</span>
<nav>{nav}</nav></header>
<div class="wrap">
<div class="doc-head">
  <h1>{title}</h1>
  <div class="meta">
    <span>分类：{cat}</span><span>原文 {words} 词</span><span>覆盖率 {coverage}</span>
    <span>一手来源：{origin_link}</span>
  </div>
  <div class="bar"><i style="width:{coverage}"></i></div>
</div>
<div class="toolbar">
  <button data-m="both" class="on">中英对照</button>
  <button data-m="zh">只看中文</button>
  <button data-m="en">只看原文</button>
  <input id="q" placeholder="搜索本页关键词…" style="font:inherit;font-size:13.5px;padding:6px 12px;border:1px solid #e3e6ea;border-radius:7px;flex:1;min-width:180px">
</div>
{body}
</div>
<div class="toc"><b>本页目录</b><ul style="padding-left:14px">{toc}</ul></div>
<script src="../../assets/app.js"></script>
</body></html>
"""

HOME_TPL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CS146S 课程资料中文包</title>
<link rel="stylesheet" href="assets/style.css"></head>
<body>
<header class="top"><span class="logo">CS146S 中文档</span>
<nav><a href="index.html">首页</a><a href="glossary.html">术语表（{glossary_count} 条）</a></nav></header>
<div class="wrap">
  <div class="hero">
    <h1>Stanford CS146S 课程资料中文包</h1>
    <p class="lead">The Modern Software Developer（Fall 2025）——AI 辅助编程方向标志性课程。
       本资料包由自动化管线从课程一手资料批量抽取、机器翻译 + 人工校对产出，共 {doc_count} 篇。
       每页均提供中英对照，可切换视图与页内搜索。</p>
  </div>
  <div class="metrics">{metrics}</div>
  {cats}
</div>
<footer>由 pipeline/run_pipeline.py 自动构建 · 机器翻译 + 人工校对 · 术语表约束全文一致</footer>
</body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
