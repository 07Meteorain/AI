#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""question_lint.py —— 群内提问质量检查器（C3 挑战配套工具）

把"高质量提问六要素"从主观感觉变成可机械检查的清单，
让"先自查、再提问"变成一个 30 秒就能跑完的动作。

用法:
    python question_lint.py 草稿.md
    python question_lint.py 草稿.md --json
    python question_lint.py 草稿.md --rewrite        # 打印改写骨架
    python question_lint.py 草稿.md --min 70         # 低于阈值退出码 2
    python question_lint.py --batch cases/           # 批量扫描目录
    python question_lint.py --selftest               # 内置样例自检

零第三方依赖，Python 3.9+。
"""

import argparse
import json
import re
import sys
from pathlib import Path

FENCE = chr(96) * 3

ELEMENTS = [
    ("context", "上下文（环境 / 版本 / 目标）", 20),
    ("attempts", "已尝试方案（≥2 条，含结果）", 20),
    ("blocker", "具体卡点（错误码 / 异常 / 定位到行）", 15),
    ("evidence", "证据（日志 / 代码块 / 复现步骤 / 截图）", 20),
    ("expectation", "期望 vs 实际", 10),
    ("question", "可回答的具体提问", 15),
]

RATING = [
    (85, "A", "思考驱动者级：群友只需读一遍就能动手"),
    (70, "B", "高质量：可以发，但如果能补上最后一块会更好"),
    (55, "C", "可回答，但每题都要对方反问 1-2 轮"),
    (40, "D", "半成品：先自查再发"),
    (0, "E", "甩问题：这类帖子的实际回复率通常低于 20%"),
]

NEGATIVE_RULES = [
    ("emotion", r"(救命|急急急|在线等|求求|大佬们|崩溃了|搞了一晚上|心态炸了)", 5,
     "情绪词替代了信息：把'救命'换成一个可检索的现象描述"),
    ("vague", r"(报错了|有报错|一直报错|跑不起来|不行了)(?!.*(日志|错误码|traceback|Traceback|退出码))", 5,
     "'报错'没有下文：贴上完整错误块的第一行 + 最后一行"),
    ("empty", None, 10, "正文过短（< 80 字），信息量不足以支撑一次回答"),
    ("punctuation", r"[!！]{2,}|[?？]{2,}", 5, "连续感叹号/问号，属于情绪宣泄而非信息"),
]

ATTEMPT_VERBS = r"(试过|尝试过|试了|已经试过|查过|搜过|改过|换过|用过|排查过|排除过|看过|读过|对比过|重装过|降级过|升级过)"
RESULT_WORDS = r"(结果|还是|仍然|依旧|依然|无变化|没有变|报同样的错|成功了|不行|失败)"

CONTEXT_ENV = r"(Windows\s*\d+|win10|win11|macos|ubuntu|linux|centos|python\s*[0-9]|node\s*v?[0-9]|npm\s*[0-9]|java\s*[0-9]|cuda\s*[0-9]|torch\s*[0-9]|版本|系统|环境|依赖)"
CONTEXT_GOAL = r"(目标|想要|希望|目的|需求|我在做|我正在做|我要实现|为了)"

BLOCKER_ERR = r"(0x[0-9A-Fa-f]{4,8}|[A-Za-z_]+Error|Exception|Traceback|退出码|exit code|错误码|segment fault|ModuleNotFound|Cannot find|undefined|stack trace)"
BLOCKER_LOC = r"(第\s*\d+\s*行|line\s*\d+|:\d+:\d+|[A-Za-z_]+\.(py|js|ts|java|cpp|c|go|rs):\d+|函数|方法|接口|调用栈)"

EXPECT = r"(期望|预期|本来应该|应该输出|按理说|应当)"
ACTUAL = r"(实际|但|可是|然而|结果|却|反而)"


def _hit(pattern, text):
    return re.search(pattern, text, re.IGNORECASE | re.MULTILINE) is not None


def _count_lines_with(pattern, text):
    n = 0
    for line in text.splitlines():
        if re.search(pattern, line, re.IGNORECASE):
            n += 1
    return n


def check_context(text):
    env = _hit(CONTEXT_ENV, text)
    goal = _hit(CONTEXT_GOAL, text)
    ratio = 0.5 * env + 0.5 * goal
    notes = []
    notes.append("环境/版本：已写" if env else "环境/版本：缺（系统 + 语言/工具版本）")
    notes.append("目标：已写" if goal else "目标：缺（你想让它做什么）")
    return ratio, notes


def _attempt_items(text):
    """列表项只要"动作 + 结果"齐了，也算一次尝试。

    v1 只认动词（试过/查过/…），把 "1. stdio:inherit -> 仍然 0x…" 这种
    写法全漏掉，good_01 因此少拿 20 分。列表项是更常见的写法。
    """
    n = 0
    for line in text.splitlines():
        s = line.strip()
        if not re.match(r"^(\d+[.)]\s+|[-*+]\s+)", s):
            continue
        has_result = re.search(RESULT_WORDS, s, re.I) or ("→" in s) or ("->" in s) or ("status=" in s)
        if has_result:
            n += 1
    return n


def check_attempts(text):
    n = max(_count_lines_with(ATTEMPT_VERBS, text), _attempt_items(text))
    has_result = _hit(RESULT_WORDS, text)
    ratio = min(n / 2.0, 1.0) * 0.7 + (0.3 if (has_result and n > 0) else 0.0)
    notes = []
    notes.append("已尝试条目：%d 条%s" % (n, "" if n >= 2 else "（建议 ≥2 条）"))
    notes.append("尝试结果：已写" if has_result else "尝试结果：缺（每条尝试后发生了什么）")
    return min(ratio, 1.0), notes


def check_blocker(text):
    err = _hit(BLOCKER_ERR, text)
    loc = _hit(BLOCKER_LOC, text)
    ratio = 0.6 * err + 0.4 * loc
    notes = []
    notes.append("错误标识：已写" if err else "错误标识：缺（错误码 / 异常类型 / 报错原文）")
    notes.append("定位信息：已写" if loc else "定位信息：缺（文件:行 / 函数名 / 调用栈帧）")
    return ratio, notes


def check_evidence(text):
    fence = FENCE in text
    repro = _hit(r"(复现|最小复现|重现|repro)", text)
    shot = _hit(r"(!\[|截图|screen shot|screenshot|\.png|\.jpg)", text)
    hits = sum([fence, repro, shot])
    ratio = min(hits / 2.0, 1.0)
    notes = []
    notes.append("代码/日志块：%s" % ("有" if fence else "无"))
    notes.append("复现步骤：%s" % ("有" if repro else "无"))
    notes.append("截图引用：%s" % ("有" if shot else "无"))
    return ratio, notes


def check_expectation(text):
    e = _hit(EXPECT, text)
    a = _hit(ACTUAL, text)
    ratio = 0.5 * e + 0.5 * a if (e or a) else 0.0
    notes = []
    notes.append("期望结果：%s" % ("已写" if e else "缺"))
    notes.append("实际结果：%s" % ("已写" if a else "缺"))
    return ratio, notes


def check_question(text):
    qs = [q for q in re.split(r"[?？\n]", text) if q.strip()]
    asks = [q for q in qs
            if len(q.strip()) >= 8
            and re.search(r"(怎么|如何|为什么|为何|是否|能否|哪里|哪个|能不能|该不该)", q)
            and not re.match(r"^\s*(那)?(我)?(该)?(怎么办|怎么回事|怎么弄|如何是好)\s*$", q.strip())]
    open_q = _hit(r"[?？]", text)
    if open_q and asks:
        ratio = 1.0
        note = "具体提问：有（%d 处可回答的问句）" % len(asks)
    elif open_q:
        ratio = 0.4
        note = "具体提问：只有'怎么办'式的开放问句，建议改成二选一或 yes/no"
    else:
        ratio = 0.0
        note = "具体提问：全文没有问号，读者不知道你想要什么"
    return ratio, [note]


CHECKS = {
    "context": check_context,
    "attempts": check_attempts,
    "blocker": check_blocker,
    "evidence": check_evidence,
    "expectation": check_expectation,
    "question": check_question,
}


def lint(text):
    text = text.replace("\r\n", "\n")
    result = {
        "chars": len(re.sub(r"\s", "", text)),
        "elements": [],
        "negatives": [],
        "score": 0,
        "rating": "",
    }
    total = 0
    for key, label, weight in ELEMENTS:
        ratio, notes = CHECKS[key](text)
        got = round(weight * ratio, 1)
        total += got
        result["elements"].append({
            "key": key, "label": label, "weight": weight,
            "got": got, "ratio": round(ratio, 3), "notes": notes,
        })

    for name, pattern, penalty, why in NEGATIVE_RULES:
        if name == "empty":
            triggered = result["chars"] < 80
        else:
            triggered = bool(re.search(pattern, text, re.IGNORECASE))
        if triggered:
            total -= penalty
            result["negatives"].append({"name": name, "penalty": penalty, "why": why})

    total = max(0.0, min(100.0, round(total, 1)))
    result["score"] = total
    for thr, grade, desc in RATING:
        if total >= thr:
            result["rating"] = grade
            result["rating_desc"] = desc
            break
    return result


def rewrite_hints(res):
    hints = []
    missing = [e for e in res["elements"] if e["ratio"] < 0.8]
    template = {
        "context": "【环境】Windows 11 / Python 3.12.4 / 项目：xxx\n【目标】我想让 xxx 做到 yyy",
        "attempts": "【已尝试】1) xxx → 结果：yyy  2) xxx → 结果：yyy",
        "blocker": "【卡点】完整报错第一行 + 最后一行；发生在 file.py:第 42 行",
        "evidence": "【复现】1) ... 2) ... 3) 观察到的输出；附最小复现代码块 / 截图",
        "expectation": "【期望】应该输出 A\n【实际】输出 B（或直接崩溃）",
        "question": "【求助】是 A 配错了还是 B 本身不支持？若你遇到过，最小改法是哪个？",
    }
    for e in missing:
        hints.append("%s 还差 %.0f 分 → 补一行：%s" % (e["label"], e["weight"] * (1 - e["ratio"]), template[e["key"]].split("\n")[0]))
    for n in res["negatives"]:
        hints.append("负向信号 %s（-%d 分）：%s" % (n["name"], n["penalty"], n["why"]))
    return hints


def render(res, path_label):
    lines = []
    lines.append("=== 提问体检报告：%s ===" % path_label)
    lines.append("得分 %.1f / 100    评级 %s（%s）    正文字数 %d" % (
        res["score"], res["rating"], res.get("rating_desc", ""), res["chars"]))
    lines.append("")
    for e in res["elements"]:
        lines.append("[%s] %-28s %4.1f/%2d  %s" % (
            "✓" if e["ratio"] >= 0.8 else ("~" if e["ratio"] > 0 else "×"),
            e["label"], e["got"], e["weight"], "；".join(e["notes"])))
    lines.append("")
    if res["negatives"]:
        for n in res["negatives"]:
            lines.append("[!] 负向信号：%s（-%d）%s" % (n["name"], n["penalty"], n["why"]))
    else:
        lines.append("[!] 负向信号：无")
    hints = rewrite_hints(res)
    if hints:
        lines.append("")
        lines.append("--- 改写建议 ---")
        for h in hints:
            lines.append("  · " + h)
    return "\n".join(lines)


def selftest():
    bad = "救命！我的代码报错了，大佬们怎么办？？？"
    good = Path(__file__).with_name("cases").joinpath("good_01.md")
    ok = True
    rb = lint(bad)
    print("内置坏样例得分：%.1f（应 < 40）" % rb["score"])
    ok = ok and rb["score"] < 40
    if good.exists():
        rg = lint(good.read_text(encoding="utf-8"))
        print("仓库好样例得分：%.1f（应 >= 85）" % rg["score"])
        ok = ok and rg["score"] >= 85
    else:
        print("未找到 cases/good_01.md，跳过好样例检查")
    print("自检：%s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def _force_utf8():
    """Windows 下重定向到文件时默认用 GBK 编码，遇到 ✓ / ✗ 会直接崩。

    这个 bug 是打包时把输出写进 demo_output.txt 才暴露的：
    同一段代码在终端里正常，重定向到文件就 UnicodeEncodeError。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _force_utf8();
    ap = argparse.ArgumentParser(description="群内提问质量检查器（C3）")
    ap.add_argument("drafts", nargs="*", help="草稿文件（.md/.txt），留空则读 stdin")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--rewrite", action="store_true", help="打印改写骨架")
    ap.add_argument("--min", type=int, default=0, help="低于该分数时退出码 2")
    ap.add_argument("--batch", metavar="DIR", help="批量扫描目录下所有 .md")
    ap.add_argument("--selftest", action="store_true", help="运行内置自检")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    files = []
    if args.batch:
        files = sorted(Path(args.batch).glob("*.md"))
        if not files:
            print("目录下没有 .md 文件：%s" % args.batch, file=sys.stderr)
            return 1
    elif args.drafts:
        files = [Path(p) for p in args.drafts]
    else:
        text = sys.stdin.read()
        res = lint(text)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(render(res, "<stdin>"))
        return 0 if res["score"] >= args.min else 2

    exit_code = 0
    payload = []
    for f in files:
        if not f.exists():
            print("文件不存在：%s" % f, file=sys.stderr)
            exit_code = 1
            continue
        res = lint(f.read_text(encoding="utf-8"))
        res["file"] = str(f)
        payload.append(res)
        if res["score"] < args.min:
            exit_code = 2
        if not args.json:
            print(render(res, str(f)))
            if args.rewrite:
                print("\n--- 改写骨架 ---")
                print("\n".join("  " + h for h in rewrite_hints(res)) or "  （无需改写）")
            print()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
