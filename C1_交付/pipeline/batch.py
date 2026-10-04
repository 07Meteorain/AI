"""
batch.py — 批量翻译辅助工具（人/AI 协同的粘合层）。

管线内部以 sha1 指纹为缓存键，人和 AI 都不该手算指纹。这个工具把这件事包起来：

    # 1) 导出待译批次（按文档分组，附该批命中的术语约束）
    python batch.py export --docs a,b --out ../work/batch_a.json
    # 2) 翻译，把译文写进 batch_a.json 的 translations 字段
    #    {"seg_id#0001": "中文译文……", ...}
    # 3) 回填缓存（自动算指纹、写 cache/translations/*.json）
    python batch.py import --file ../work/batch_a.json

这样做的价值：分段 → 术语注入 → 译文回填 → 指纹计算全是脚本干的，
人和 AI 只负责「把英文变成中文」这一件事，不可能因为算错指纹而丢译文。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (
    Glossary, ensure_dir, load_config, log, ok, read_jsonl, sha1, warn, PIPELINE_DIR,
)


def load_segments(work_dir: Path) -> list[dict]:
    rows = read_jsonl(work_dir / "translations.jsonl")
    if not rows:
        rows = read_jsonl(work_dir / "segments.jsonl")
    return rows


def cmd_export(args) -> int:
    cfg = load_config()
    proj = cfg["project"]
    glossary = Glossary.load(proj["glossary"])
    rows = load_segments(proj["work_dir"])

    want = {d.strip() for d in args.docs.split(",") if d.strip()} if args.docs else None
    picked = [r for r in rows
              if r["kind"] != "code"
              and (want is None or r["doc_id"] in want)
              and (args.include_done is False or r.get("status") != "translated")]

    items, missing = [], []
    for r in picked:
        low = r["text"].lower()
        hit = [t.en for t in glossary.terms
               if any((k or "").lower() in low for k in [t.en, *t.aliases])]
        items.append({
            "seg_id": r["seg_id"],
            "doc_id": r["doc_id"],
            "title": r["meta"].get("title", ""),
            "category": r["meta"].get("category", ""),
            "priority": r["meta"].get("priority", 2),
            "order": r["order"],
            "kind": r["kind"],
            "words": r["word_count"],
            "source": r["text"],
        })

    out = {
        "_meta": {
            "generated_by": "batch.py export",
            "docs": sorted({i["doc_id"] for i in items}),
            "segments": len(items),
            "words": sum(i["words"] for i in items),
            "glossary": glossary.glossary_prompt_block([t for t in
                {e for i in items for e in
                 [x.en for x in glossary.terms
                  if any((k or "").lower() in i["source"].lower() for k in [x.en, *x.aliases])]}
            ]),
            "instruction": "把每条 source 翻译为简体中文，译文写入同结构的 translations 字典（key 为 seg_id）。",
        },
        "items": items,
        "translations": {},
    }
    ensure_dir(Path(args.out).parent)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    ok(f"导出 {len(items)} 个 Segment / {out['_meta']['words']} 词 → {args.out}")
    if not items:
        warn("没有匹配到待译 Segment（检查 --docs 或是否已全部翻译）")
    return 0


def cmd_import(args) -> int:
    cfg = load_config()
    proj = cfg["project"]
    cache = ensure_dir(proj["cache_dir"])
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    tr = data.get("translations") or {}
    items = {i["seg_id"]: i for i in data.get("items", [])}
    if not tr:
        warn("translations 为空，未回填任何内容")
        return 1

    rows = {r["seg_id"]: r for r in load_segments(proj["work_dir"])}
    ok_n = miss = 0
    problems = []
    for seg_id, zh in tr.items():
        if seg_id not in items:
            miss += 1
            problems.append(f"{seg_id}: 不在批次 items 中（可能原文已变更，需重新 export）")
            continue
        if seg_id not in rows:
            miss += 1
            problems.append(f"{seg_id}: 不在当前 segments 中")
            continue
        zh = (zh or "").strip()
        if not zh:
            miss += 1
            problems.append(f"{seg_id}: 译文为空")
            continue
        r = rows[seg_id]
        fp = r.get("fingerprint") or sha1(r["text"])
        (cache / f"{fp}.json").write_text(json.dumps({
            "seg_id": seg_id, "doc_id": r["doc_id"], "fingerprint": fp,
            "zh": zh, "meta": {"source": args.file, "batch": Path(args.file).stem},
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        ok_n += 1

    ok(f"回填 {ok_n} 条译文 → cache/translations/（失败 {miss}）")
    for p in problems[:20]:
        warn(p)
    if len(problems) > 20:
        warn(f"… 另有 {len(problems)-20} 条问题")
    return 0 if miss == 0 else 2


def cmd_status(args) -> int:
    cfg = load_config()
    proj = cfg["project"]
    rows = load_segments(proj["work_dir"])
    tr = [r for r in rows if r["kind"] != "code"]
    done = [r for r in tr if r.get("status") == "translated"]
    import collections
    agg = collections.defaultdict(lambda: [0, 0, 0])
    for r in tr:
        a = agg[(r["meta"].get("priority", 2), r["doc_id"])]
        a[0] += 1
        a[1] += r["word_count"]
        if r.get("status") == "translated":
            a[2] += r["word_count"]
    for (p, d), (n, w, dw) in sorted(agg.items()):
        flag = "✔" if dw >= w * 0.8 else ("◐" if dw else " ")
        print(f"{flag} P{p} {d:<42} {dw:>6}/{w:<6} 词")
    print(f"\n合计 {len(done)}/{len(tr)} Segment，"
          f"{sum(r['word_count'] for r in done):,}/{sum(r['word_count'] for r in tr):,} 词")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="导出待译批次")
    e.add_argument("--docs", help="逗号分隔的 doc_id；省略则导出全部未译")
    e.add_argument("--out", required=True)
    e.add_argument("--include-done", action="store_true", help="连已译的一起导出")
    e.set_defaults(func=cmd_export)

    i = sub.add_parser("import", help="回填译文到缓存")
    i.add_argument("--file", required=True)
    i.set_defaults(func=cmd_import)

    s = sub.add_parser("status", help="查看翻译进度")
    s.set_defaults(func=cmd_status)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
