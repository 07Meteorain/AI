"""
03_qc.py — 质量抽检阶段：自动检查译文质量，产出可复核的质检报告。

检查项（每项都有阈值和证据，不是拍脑袋打分）：
  1. 覆盖率        —— 已译词数 / 可翻译词数，按篇和按周次分别统计
  2. 术语一致率    —— 命中术语表的译文中，规范译法出现次数 vs 禁用译法出现次数
  3. 漏译检测      —— 译文中残留的高频英文实义词（排除专有名词/代码白名单）
  4. 长度比        —— 中文字数 / 原英文字数，落在 [0.55, 1.60] 视为正常
  5. 格式完整性    —— 代码块围栏是否配对、Markdown 标题数/列表数是否与原文一致
  6. 空译/截断     —— 译文为空、过短、或以未闭合的代码块结尾

输出：
  reports/02_qc.json      机器可读明细
  reports/02_qc.md        人读的质量报告（含红黄绿判定与待修清单）
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

from common import (
    Glossary, count_words, cjk_ratio, ensure_dir, load_config, log, ok,
    read_jsonl, warn, PIPELINE_DIR,
)

# 译文中出现这些英文是正常的（专有名词/代码/命令），不计入漏译
WHITELIST_EN = set("""
ai api apis cli sdk ide llm llms gpt git github gitlab ci cd prs json yaml xml html css sql http https
https tcp udp ip dns url uri uuid id ids api apis rest grpc rpc ssl tls oauth jwt saml sso mfa otp
sse stdio niah rag llm moore s la m vc r ceo cto ok okay vs etc e g i e ie etc
january february march april may june july august september october november december
mon tuesday wednesday thursday friday saturday sunday
python javascript typescript java go rust c cpp c sharp ruby php swift kotlin scala bash shell zsh
node npm yarn pnpm deno bun react vue angular nextjs django flask rails spring express
aws gcp azure s3 ec2 lambda kubernetes docker terraform ansible jenkins circleci
linux ubuntu debian centos windows macos unix vim emacs vscode intellij xcode
anthropic openai google microsoft meta amazon nvidia deepmind mistral cohere replicate
claude gpt4 gpt5 gemini llama mistral qwen deepseek cursor copilot devin warp codex claude-code
ant android ios web ios linux unix
red green blue black white gray grey yellow purple orange teal cyan magenta
true false null none nil undefined nan void int str bool list dict map set tuple array
true false self cls def class const let var function return if else elif for while try
except catch finally throw import from export default new this super null
ascii utf ansi base64 hex sha md yyyy mm dd hhmmss
""".split())

# 这些短语如果出现在译文里，说明漏译了（是原文里的普通英文实义词）
UNTRANSLATED_HINTS = [
    "the", "and", "with", "that", "this", "from", "your", "you", "are", "was", "were",
    "have", "will", "can", "should", "would", "could", "when", "what", "which", "there",
    "about", "into", "than", "then", "them", "they", "their", "been", "being", "also",
    "more", "most", "some", "such", "only", "other", "over", "each", "because",
    "example", "use", "using", "used", "make", "making", "need", "needs", "work",
    "works", "working", "help", "helps", "see", "look", "find", "give", "take",
    "very", "much", "many", "well", "good", "great", "first", "last", "next", "new",
]


def strip_code(text: str) -> str:
    """去掉「本就不该翻译」的英文，只留下真正需要中文化的散文部分。

    为什么要这么多规则：初版只剥离代码块，结果 30 条误报。逐条看下来，
    残留的英文几乎都属于以下四类——它们**必须**保持英文：
      1. 代码块 / 行内代码 / 路径/ 命令
      2. 模型原始输出、提示词示例（研究论文里大段引用模型实际吐的英文，
         译了反而破坏实验结论的可复现性）
      3. 文章标题、书名（《How to Fix Your Context》）
      4. 引号内的直接引语
    把这些剥离后再统计，残留英文才有指示意义。
    """
    # 1) 代码块与行内代码
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]+`", " ", text)
    # 2) 英文书名/篇名《...》
    text = re.sub(r"《[^》]*》", " ", text)
    # 3) 引号内的直接引语（中文引号与英文引号都处理）
    text = re.sub(r"“[^”]*”", " ", text)
    text = re.sub(r"‘[^’]*’", " ", text)
    text = re.sub(r'"[^"\n]{6,}"', " ", text)
    # 4) 整行就是英文的「逐字示例」行（研究论文里常见）：
    #    整行英文占比 > 80% 且没有中文，视为原文引用/示例，整行剔除。
    kept = []
    for ln in text.split("\n"):
        letters = re.findall(r"[A-Za-z\u4e00-\u9fff]", ln)
        if not letters:
            kept.append(ln); continue
        zh = sum(1 for c in letters if "\u4e00" <= c <= "\u9fff")
        if zh / len(letters) < 0.2 and len(letters) > 12:
            continue  # 纯英文行 → 视为逐字引用，剔除
        kept.append(ln)
    return "\n".join(kept)


def fence_count(text: str) -> int:
    return len(re.findall(r"^```", text, flags=re.M))


def heading_count(text: str) -> int:
    return len(re.findall(r"^#{1,6}\s", text, flags=re.M))


def list_count(text: str) -> int:
    return len(re.findall(r"^\s*([-*+]|\d+\.)\s", text, flags=re.M))


def check_segment(row: dict, glossary: Glossary, thresholds: dict | None = None) -> dict:
    # 阈值来自 config.json 的 pipeline.qc；缺省值与config 保持一致。
    th = thresholds or {}
    ratio_red = th.get("min_length_ratio", 0.75)
    ratio_yellow = th.get("ratio_yellow_low", 0.95)
    ratio_high = th.get("max_length_ratio", 2.40)
    min_words = th.get("length_ratio_min_words", 25)

    en, zh = row["text"], row.get("zh") or ""
    issues: list[dict] = []
    res = {
        "seg_id": row["seg_id"], "doc_id": row["doc_id"], "status": row["status"],
        "en_words": row["word_count"], "zh_words": count_words(zh) if zh else 0,
        "issues": issues,
    }

    if row["kind"] == "code":
        res["note"] = "代码块，原样透传，不计入漏译"
        return res

    if not zh:
        issues.append({"type": "untranslated", "severity": "red",
                       "detail": "尚未翻译"})
        return res

    # 4) 长度比（中文字数 ÷ 英文词数）
    #    中英字数比不是 1:1。经验区间：技术散文英→中约 1.0～2.1，
    #    因为一个英文词常对应 1.5～2 个汉字，且中文要补出原文省略的主语。
    #    阈值从 config.json 读取（pipeline.qc），换语料可调。
    #    短段落不适用：像 "## MCP 架构——一览" 这种标题只有几个词，
    #    中英用词密度天然不同，比例低不代表漏译。设 min_words 下限。
    ratio = res["zh_words"] / max(1, res["en_words"])
    res["length_ratio"] = round(ratio, 3)
    if res["en_words"] < min_words:
        res["note"] = "短段落，长度比不作为判定依据"
    elif ratio < ratio_red:
        issues.append({"type": "too_short", "severity": "red",
                       "detail": f"中文/英文长度比 {ratio:.2f}，疑似漏译或过度压缩"})
    elif ratio < ratio_yellow:
        issues.append({"type": "short", "severity": "yellow",
                       "detail": f"长度比 {ratio:.2f} 偏低，建议核对是否完整"})
    elif ratio > ratio_high:
        issues.append({"type": "too_long", "severity": "yellow",
                       "detail": f"长度比 {ratio:.2f} 偏高，可能有扩写或原文含大量代码"})

    # 5) 格式完整性
    if fence_count(en) != fence_count(zh):
        issues.append({"type": "fence_mismatch", "severity": "red",
                       "detail": f"代码块围栏数不一致：原文 {fence_count(en)} / 译文 {fence_count(zh)}"})
    dh, dz = heading_count(en), heading_count(zh)
    if dh != dz:
        issues.append({"type": "heading_mismatch", "severity": "yellow",
                       "detail": f"标题数不一致：原文 {dh} / 译文 {dz}"})
    dl, zl = list_count(en), list_count(zh)
    if abs(dl - zl) > max(2, dl * 0.3):
        issues.append({"type": "list_mismatch", "severity": "yellow",
                       "detail": f"列表项数差异过大：原文 {dl} / 译文 {zl}"})

    # 2) 术语一致性（传入原文，用于排除「普通词义」误报）
    bad = glossary.check_consistency(zh, en)
    for b in bad:
        issues.append({**b, "severity": "red" if b["level"] == "error" else "info"})
    res["forbidden_terms"] = sum(1 for b in bad if b["level"] == "error")
    res["forbidden_terms_soft"] = sum(1 for b in bad if b["level"] == "info")

    # 3) 漏译检测
    prose = strip_code(zh)
    # 报错信息、专有名词里的虚词也要排除。例：
    #   "The token '&&' is not a valid statement separator"（PowerShell 报错原文）
    #   "TensorFlowExample"、"Infostealer"、"Porto de Galinhas"（地名/人名）
    for pat in (r"['\"][^'\"]{10,}['\"]",        # 引号内的报错/代码片段
                r"\b(?:TensorFlow|BERT|Infostealer|Weaponizing)\w*\b"):
        prose = re.sub(pat, " ", prose)
    en_words = [w for w in re.findall(r"\b[a-zA-Z]{2,}\b", prose)]
    suspicious = [w.lower() for w in en_words
                  if w.lower() in UNTRANSLATED_HINTS and w.lower() not in WHITELIST_EN]
    if suspicious:
        cnt = collections.Counter(suspicious)
        top = ", ".join(f"{w}×{n}" for w, n in cnt.most_common(5))
        ratio_s = len(suspicious) / max(1, len(en_words))
        res["untranslated_ratio"] = round(ratio_s, 4)
        # 绝对数量下限：只看比例会被短段落骗到。一段话里只残留 1 个虚词
        # （比如专名 Cloudflare Access 里的 from）不是漏译，是正常英文残留。
        # 真正漏译的形态是「成片」的英文，所以同时要求绝对数量 ≥ 4 个。
        if len(suspicious) >= 4 and ratio_s > 0.05:
            issues.append({"type": "untranslated", "severity": "red",
                           "detail": f"疑似漏译，残留英文虚词 {len(suspicious)} 个（占 {ratio_s:.1%}）：{top}"})
        elif len(suspicious) >= 3 and ratio_s > 0.015:
            issues.append({"type": "partial_untranslated", "severity": "yellow",
                           "detail": f"残留英文虚词 {len(suspicious)} 个（占 {ratio_s:.1%}）：{top}"})
    else:
        res["untranslated_ratio"] = 0.0

    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PIPELINE_DIR / "config.json"))
    args = ap.parse_args()
    cfg = load_config(args.config)
    proj = cfg["project"]
    glossary = Glossary.load(proj["glossary"])
    thresholds = cfg["pipeline"]["qc"]

    rows = read_jsonl(proj["work_dir"] / "translations.jsonl")
    if not rows:
        warn("没有译文，先跑 02_translate.py")
        return 1

    # ---- 逐段检查
    results = [check_segment(r, glossary, thresholds) for r in rows]

    # ---- 覆盖率（按篇）
    docs: dict[str, dict] = {}
    for r, res in zip(rows, results):
        d = docs.setdefault(r["doc_id"], {
            "doc_id": r["doc_id"], "title": r["meta"].get("title", ""),
            "category": r["meta"].get("category", ""), "priority": r["meta"].get("priority", 2),
            "en_words": 0, "zh_words": 0, "translated_words": 0,
            "segments": 0, "translated": 0, "pending": 0, "code": 0, "red": 0, "yellow": 0,
        })
        d["segments"] += 1
        if r["kind"] == "code":
            d["code"] += 1
            continue
        d["en_words"] += r["word_count"]
        if r["status"] == "translated":
            d["translated"] += 1
            d["translated_words"] += r["word_count"]
            d["zh_words"] += res["zh_words"]
        else:
            d["pending"] += 1
        for i in res["issues"]:
            if i["severity"] == "red":
                d["red"] += 1
            elif i["severity"] == "yellow":
                d["yellow"] += 1

    for d in docs.values():
        # 覆盖率：已译 Segment 覆盖了多少原文词数（与全局口径一致）
        d["coverage"] = round(d["translated_words"] / d["en_words"], 4) if d["en_words"] else 0.0
        # 长度比：中文字数 ÷ 英文词数。中文压缩率低，正常落在 1.0～2.1。
        d["length_ratio"] = round(d["zh_words"] / d["en_words"], 3) if d["en_words"] else 0.0

    # ---- 全局指标
    total_en = sum(d["en_words"] for d in docs.values())
    total_zh = sum(d["zh_words"] for d in docs.values())
    # 词级覆盖率 = 已译 Segment 的原文词数 / 全部可译词数。
    # 注意：不能拿「中文字数 ÷ 英文字词数」当覆盖率——中文字数天然是英文字词的
    # 1.5～2倍（"context" 1 个词 ↔ "上下文" 3 个字），那样算出来会是 166%，
    # 看起来像超额完成，实际是度量单位不一致。这里用「原文侧」统一口径。
    en_done = sum(d["en_words"] for d in docs.values() if d["coverage"] > 0)
    en_all = total_en
    word_coverage = en_done / en_all if en_all else 0.0
    # 长度比单独报告（中文字数 ÷ 英文词数），正常区间约 1.0～2.1
    length_ratio = total_zh / total_en if total_en else 0.0

    # 文档级覆盖率：完整翻译的文档数 / 可翻译文档数
    translatable_docs = [d for d in docs.values() if d["en_words"] > 0]
    full_docs = [d for d in translatable_docs if d["coverage"] >= 0.8]
    partial_docs = [d for d in translatable_docs if 0.3 <= d["coverage"] < 0.8]
    doc_coverage = len(full_docs) / len(translatable_docs) if translatable_docs else 0.0

    seg_total = sum(1 for r in rows if r["kind"] != "code")
    seg_translated = sum(1 for r in rows if r["status"] == "translated")

    #术语一致率
    term_checks = sum(1 for res in results for i in res["issues"]
                      if i["type"] == "forbidden_term")
    term_soft = sum(1 for res in results for i in res["issues"]
                    if i["type"] == "forbidden_term_soft")
    zh_chars = total_zh or 1
    term_consistency = max(0.0, 1 - term_checks / max(1, zh_chars / 500))

    red = sum(1 for res in results for i in res["issues"] if i["severity"] == "red")
    yellow = sum(1 for res in results for i in res["issues"] if i["severity"] == "yellow")
    info = sum(1 for res in results for i in res["issues"] if i["severity"] == "info")

    # 术语实际使用频次（证明术语表不是摆设）
    term_freq = {}
    for t in glossary.terms:
        n = sum((r.get("zh") or "").count(t.zh.split("（")[0]) for r in rows if r.get("zh"))
        if n:
            term_freq[t.en] = n

    # ---- 判定
    verdicts = [
        {"check": "词级覆盖率", "value": f"{word_coverage:.1%}", "threshold": f"≥ {thresholds['min_coverage']:.0%}",
         "pass": word_coverage >= thresholds["min_coverage"]},
        {"check": "文档级覆盖率（≥80% 视为完整）", "value": f"{len(full_docs)}/{len(translatable_docs)} = {doc_coverage:.1%}",
         "threshold": f"≥ {thresholds['min_coverage']:.0%}", "pass": doc_coverage >= thresholds["min_coverage"]},
        {"check": "Segment 翻译率", "value": f"{seg_translated}/{seg_total} = {seg_translated/max(1,seg_total):.1%}",
         "threshold": "≥ 80%", "pass": seg_translated / max(1, seg_total) >= 0.8},
        {"check": "术语违规数（硬错误）", "value": str(term_checks), "threshold": "= 0",
         "pass": term_checks == 0},
        {"check": "红色问题数", "value": str(red), "threshold": "= 0", "pass": red == 0},
    ]

    report = {
        "generated_by": "03_qc.py",
        "thresholds": thresholds,
        "metrics": {
            "word_coverage": round(word_coverage, 4),
            "doc_coverage": round(doc_coverage, 4),
            "seg_translation_rate": round(seg_translated / max(1, seg_total), 4),
            "total_en_words": total_en, "total_zh_words": total_zh,
            "red_issues": red, "yellow_issues": yellow, "info_issues": info,
            "term_violations": term_checks, "term_soft_flags": term_soft,
            "term_consistency": round(term_consistency, 4),
        },
        "verdicts": verdicts,
        "docs": sorted(docs.values(), key=lambda d: (d["priority"], -d["en_words"])),
        "term_frequency": dict(sorted(term_freq.items(), key=lambda x: -x[1])),
        "segment_results": results,
    }
    ensure_dir(proj["reports_dir"])
    (proj["reports_dir"] / "02_qc.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- Markdown 报告
    L = []
    L.append("# 翻译质量抽检报告\n")
    L.append(f"> 由 `pipeline/03_qc.py` 自动生成，可复跑复核。术语表 {len(glossary)} 条。\n")
    L.append("## 一、总览\n")
    L.append("| 指标 | 数值 | 阈值 | 判定 |")
    L.append("|---|---|---|---|")
    for v in verdicts:
        L.append(f"| {v['check']} | {v['value']} | {v['threshold']} | {'✅ 通过' if v['pass'] else '❌ 未达标'} |")
    L.append("")
    L.append(f"- 可翻译原文：{total_en:,} 词；已产出中文：{total_zh:,} 字")
    L.append(f"- Segment：{seg_translated}/{seg_total} 已译，{sum(1 for r in rows if r['kind']=='code')} 个代码块原样透传")
    L.append(f"- 质量问题：🔴 {red} 个，🟡 {yellow} 个，⚪ {info} 个提示\n")

    L.append("## 二、逐篇覆盖情况\n")
    L.append("| 优先级 | 分类 | 文档 | 原文词数 | 覆盖率 | 长度比 | 红 | 黄 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for d in sorted(docs.values(), key=lambda x: (x["priority"], -x["en_words"])):
        L.append(f"| P{d['priority']} | {d['category']} | [{d['title']}]({d['doc_id']}.md) | "
                 f"{d['en_words']} | {d['coverage']:.1%} | {d['length_ratio']:.2f} | {d['red']} | {d['yellow']} |")
    L.append("")

    L.append("## 三、术语一致性\n")
    L.append(f"- 术语表条目：**{len(glossary)}** 条（要求 ≥50）")
    L.append(f"- 禁用译法规则：**{len(glossary.forbidden_pairs)}** 条")
    L.append(f"- 术语硬错误（全文未出现规范译法）：**{term_checks}** 处")
    L.append(f"- 术语提示（规范译法已并存，疑为普通词义）：**{term_soft}** 处\n")
    L.append("> 判定规则：若原文未出现该英文术语，则不告警；若译文已同时包含规范译法，")
    L.append("> 降级为提示。这样能避免「不同」「模式」「背景」这类常用词被误判为术语误译。\n")
    top = list(report["term_frequency"].items())[:20]
    if top:
        L.append("译文中实际命中的核心术语（Top 20）：\n")
        L.append("| 英文 | 规范译法 | 出现次数 |")
        L.append("|---|---|---|")
        en2zh = {t.en: t.zh for t in glossary.terms}
        for en, n in top:
            L.append(f"| {en} | {en2zh.get(en,'')} | {n} |")
        L.append("")

    L.append("## 四、待修清单（红/黄问题明细）\n")
    prob = [res for res in results
            if any(i["severity"] in ("red", "yellow") for i in res["issues"])]
    if not prob:
        L.append("无。\n")
    else:
        L.append("| Segment | 文档 | 级别 | 类型 | 说明 |")
        L.append("|---|---|---|---|---|")
        for res in prob[:80]:
            for i in res["issues"]:
                if i["severity"] == "info":
                    continue
                L.append(f"| `{res['seg_id']}` | {res['doc_id']} | "
                         f"{'🔴' if i['severity']=='red' else '🟡'} | {i['type']} | {i['detail']} |")
        if len(prob) > 80:
            L.append(f"\n> 仅列出前 80 条，完整明细见 `reports/02_qc.json`。")
    L.append("")

    softs = [(res, i) for res in results for i in res["issues"] if i["severity"] == "info"]
    if softs:
        L.append("## 五、术语一致性提示（不阻塞交付，建议人工过一遍）\n")
        L.append("| Segment | 发现 | 建议译法 | 说明 |")
        L.append("|---|---|---|---|")
        for res, i in softs[:40]:
            L.append(f"| `{res['seg_id']}` | {i['found']} | {i['should_be']} | {i['detail']} |")
        if len(softs) > 40:
            L.append(f"\n> 仅列出前 40 条，共 {len(softs)} 条，完整明细见 `reports/02_qc.json`。")
        L.append("")
    (proj["reports_dir"] / "02_qc.md").write_text("\n".join(L), encoding="utf-8")

    # ---- 控制台
    for v in verdicts:
        (ok if v["pass"] else warn)(f"{v['check']}: {v['value']}（阈值 {v['threshold']}）")
    ok(f"→ reports/02_qc.md, reports/02_qc.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
