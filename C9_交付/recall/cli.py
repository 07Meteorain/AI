"""Recall 命令行入口。

命令的职责边界：
- `build` 只负责「笔记 → 候选 → 库」，不碰复习状态；
- `review` 只负责「今天该复习什么 → 记录评分」；
- `web` 只是库的一个只读导出；
- `sample` / `apply` 是审核闭环的两端。

这样每个命令都可以单独测试，出问题时也容易定位是哪一段坏了。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import __version__
from .audit import KIND_LABELS, render_audit_markdown, sample_cards
from .doctor import diagnose_path, render_report
from .generate import Options, build_deck
from .model import Card
from .scheduler import (
    GRADE_LABELS,
    State,
    build_queue,
    days_until,
    parse_date,
    review,
    today_iso,
)
from .store import (
    apply_decisions,
    connect as _store_connect,
    export_payload,
    get_meta,
    list_cards,
    next_due_preview,
    record_review,
    set_meta,
    stats as store_stats,
    states_for,
    upsert_cards,
)
from .web import render_site


# 命令结束后统一关闭连接。Windows 上未关闭的 SQLite 文件会锁住临时目录，
# 这既是测试里的真实故障，也是用户删库/搬库时会遇到的坑。
_OPEN_CONNECTIONS: list = []


def connect(path: str):
    conn = _store_connect(path)
    _OPEN_CONNECTIONS.append(conn)
    return conn


def _close_connections() -> None:
    while _OPEN_CONNECTIONS:
        conn = _OPEN_CONNECTIONS.pop()
        try:
            conn.close()
        except Exception:
            pass


class UserError(Exception):
    """可预期的用户错误：打印一句话，退出码 1。"""


REASON_LABELS = {
    "low-confidence": "置信度低于阈值",
    "prompt-length": "问题过长/过短",
    "answer-length": "答案过长/过短",
    "format": "含 URL/图片/表格残留",
    "boilerplate": "模板或导航文本",
    "too-thin": "有效内容过少",
    "duplicate-prompt": "问题重复",
    "duplicate-answer": "长答案重复",
}


def _split_kinds(value: str) -> tuple:
    return tuple(part.strip() for part in (value or "").split(",") if part.strip())


def _write_json(path: str, payload: object) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _read_json(path: str) -> object:
    if not os.path.isfile(path):
        raise UserError("找不到文件：{}".format(path))
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except ValueError as exc:
        raise UserError("不是合法 JSON：{}（{}）".format(path, exc))


# ---------------------------------------------------------------- build


def cmd_build(args: argparse.Namespace) -> int:
    if not os.path.exists(args.path):
        raise UserError("找不到笔记路径：{}".format(args.path))
    opts = Options(
        min_confidence=args.min_confidence,
        max_per_section=args.max_per_section,
        max_per_file=args.max_per_file,
        kinds=_split_kinds(args.kinds),
        include_gist=args.include_gist,
    )
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    result = build_deck(args.path, opts, generated=generated)
    if not result.cards:
        raise UserError(
            "没有抽到任何卡片。检查 Markdown 是否有标题层级、定义列表或「问：…答：…」。"
            "也可以降低 --min-confidence 到 0.5。"
        )

    conn = connect(args.db)
    inserted, updated = upsert_cards(conn, result.cards)
    set_meta(conn, "built_at", generated)
    set_meta(conn, "source_root", os.path.abspath(args.path))

    if args.out:
        _write_json(args.out, export_payload(conn))

    summary = {
        "files": result.stats.files,
        "sections": result.stats.sections,
        "words": result.stats.words,
        "candidates": result.stats.candidates,
        "accepted": result.stats.accepted,
        "inserted": inserted,
        "updated": updated,
        "by_kind": result.stats.by_kind,
        "rejected": result.stats.rejected,
        "db": os.path.abspath(args.db),
        "out": os.path.abspath(args.out) if args.out else "",
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print("扫描 {} 篇笔记 / {} 节 / {:,} 字".format(
        result.stats.files, result.stats.sections, result.stats.words
    ))
    print("候选 {} → 通过 {}（质量门拦下 {}）".format(
        result.stats.candidates,
        result.stats.accepted,
        sum(result.stats.rejected.values()),
    ))
    if result.stats.rejected:
        parts = []
        for reason, count in sorted(result.stats.rejected.items(), key=lambda kv: -kv[1]):
            parts.append("{} {}".format(REASON_LABELS.get(reason, reason), count))
        print("  拦截原因：" + " · ".join(parts))
    print("新增 {} 张 / 更新 {} 张；库中共 {} 张".format(
        inserted, updated, store_stats(conn)["total"]
    ))
    print("按类型：" + " · ".join(
        "{} {}".format(KIND_LABELS.get(k, k), v) for k, v in sorted(result.stats.by_kind.items(), key=lambda kv: -kv[1])
    ))
    print("数据库：{}".format(os.path.abspath(args.db)))
    if args.out:
        print("卡组 JSON：{}".format(os.path.abspath(args.out)))
    print("下一步：`python -m recall stats` 看总量，`python -m recall review` 开始复习。")
    return 0


# ---------------------------------------------------------------- stats


def cmd_stats(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    data = store_stats(conn, args.today or today_iso())
    forecast = next_due_preview(conn, args.today or today_iso(), 7)
    data["forecast"] = [[day, count] for day, count in forecast]
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print("卡组：{} 张（可复习 {} / 候选 {} / 已剔除 {}）".format(
        data["total"], data["approved"], data["candidate"], data["rejected"]
    ))
    print("今天（{}）：到期 {} · 新卡 {} · 已复习 {}".format(
        data["today"], data["due"], data["new"], data["reviewed_today"]
    ))
    if data["suspended"]:
        print("已暂停（leech）：{} 张".format(data["suspended"]))
    if data["by_kind"]:
        print("\n按类型：")
        width = max(len(KIND_LABELS.get(k, k)) for k in data["by_kind"])
        for kind, count in data["by_kind"].items():
            print("  {:<{}}  {}".format(KIND_LABELS.get(kind, kind), width, count))
    print("\n未来 7 天到期：")
    max_count = max([count for _, count in forecast] + [1])
    for day, count in forecast:
        bar = "█" * int(round(count / max_count * 24)) if count else ""
        print("  {}  {:>3}  {}".format(day, count, bar))
    return 0


# ---------------------------------------------------------------- review


def _parse_script(value: str) -> List[int]:
    parts = [part.strip() for part in (value or "").split(",") if part.strip()]
    grades: List[int] = []
    for part in parts:
        try:
            grade = int(part)
        except ValueError:
            raise UserError("--script 里只能写 1–4，收到 {!r}".format(part))
        if grade not in (1, 2, 3, 4):
            raise UserError("--script 里的评分必须是 1–4，收到 {}".format(grade))
        grades.append(grade)
    return grades


def cmd_review(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    today_text = args.today or today_iso()
    try:
        today_date = parse_date(today_text)
    except ValueError:
        raise UserError("--today 需要 YYYY-MM-DD 格式，收到 {!r}".format(today_text))

    all_cards = list_cards(conn)
    if not all_cards:
        raise UserError("数据库里没有卡片。先运行 `python -m recall build <笔记目录>`。")
    queue = build_queue(
        all_cards,
        states_for(conn),
        today_date,
        limit=args.limit,
        new_limit=args.new_limit,
        include_candidates=args.include_candidates,
    )
    if not queue:
        print("今天没有到期卡片。{} 张卡都已排到未来；明天再来。".format(len(all_cards)))
        return 0

    script = _parse_script(args.script) if args.script else []
    if script and len(script) < len(queue):
        raise UserError(
            "--script 只有 {} 个评分，但队列有 {} 张卡；请补足或调小 --limit".format(
                len(script), len(queue)
            )
        )
    interactive = sys.stdin.isatty() and not args.json
    if not script and not interactive:
        raise UserError("非交互环境请用 --script 4,3,4（或用 --json 只取摘要）")

    tally = {1: 0, 2: 0, 3: 0, 4: 0}
    reviewed = 0
    for index, (card, is_new) in enumerate(queue, 1):
        if not args.json:
            print()
            print("─" * 66)
            print("[{}/{}] {} · {} · {}:{}".format(
                index,
                len(queue),
                "新卡" if is_new else "到期",
                KIND_LABELS.get(card.kind, card.kind),
                card.source,
                card.line,
            ))
            print()
            print(card.prompt)
            print()

        if script:
            grade = script[index - 1]
            if not args.json:
                print("答案：{}".format(card.answer))
                print()
                print("评分：{} {}".format(grade, GRADE_LABELS[grade]))
        else:
            try:
                reply = input("按回车显示答案（q 退出）… ")
            except EOFError:
                reply = "q"
            if reply.strip().lower() == "q":
                print("已退出本轮。")
                break
            print()
            print("答案：{}".format(card.answer))
            print()
            while True:
                try:
                    raw = input("评分 1-4（1 忘记 / 2 困难 / 3 记得 / 4 简单）：").strip()
                except EOFError:
                    raw = "q"
                if raw.lower() == "q":
                    grade = 0
                    break
                if raw in ("1", "2", "3", "4"):
                    grade = int(raw)
                    break
                print("请输入 1–4。")
            if grade == 0:
                break

        current = states_for(conn, [card.id]).get(card.id) or State()
        new_state = review(current, grade, today_date)
        record_review(conn, card.id, grade, new_state, today_date.isoformat())
        tally[grade] += 1
        reviewed += 1

    forecast = next_due_preview(conn, today_text, 7)
    summary = {
        "reviewed": reviewed,
        "tally": {str(k): v for k, v in tally.items()},
        "today": today_text,
        "forecast": [[day, count] for day, count in forecast],
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print()
    print("=" * 66)
    print("本轮复习 {} 张：忘记 {} · 困难 {} · 记得 {} · 简单 {}".format(
        reviewed, tally[1], tally[2], tally[3], tally[4]
    ))
    tomorrow = forecast[1][1] if len(forecast) > 1 else 0
    print("明天到期 {} 张；未来 7 天累计 {} 张。".format(
        tomorrow, sum(count for _, count in forecast)
    ))
    if tally[1]:
        print("有 {} 张被标为「忘记」，明天会优先回来。".format(tally[1]))
    return 0


# ---------------------------------------------------------------- sample / apply


def cmd_sample(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    status = None if args.status == "all" else args.status
    cards = list_cards(conn, status=status)
    if not cards:
        raise UserError("没有可抽样的卡片（status={}）。".format(args.status))
    sampled = sample_cards(cards, n=args.n, seed=args.seed, kinds=_split_kinds(args.kinds))
    markdown = render_audit_markdown(
        sampled,
        title=args.title,
        seed=args.seed,
        generated=get_meta(conn, "built_at", ""),
    )
    if args.out:
        directory = os.path.dirname(os.path.abspath(args.out))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        print("抽样 {} 张 → {}".format(len(sampled), os.path.abspath(args.out)))
    else:
        print(markdown)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    payload = _read_json(args.decisions)
    if not isinstance(payload, dict):
        raise UserError("决定文件应是对象，例如 {\"approved\": [...], \"rejected\": [...]}")
    approved = payload.get("approved") or []
    rejected = payload.get("rejected") or []
    if not isinstance(approved, list) or not isinstance(rejected, list):
        raise UserError("approved / rejected 必须是 id 数组")
    conn = connect(args.db)
    result = apply_decisions(conn, approved, rejected)
    print("写回完成：保留 {} 张 · 剔除 {} 张 · 未找到 {} 个 id".format(
        result["approved"], result["rejected"], result["missing"]
    ))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- web / export


def cmd_web(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    data = store_stats(conn)
    if data["approved"] == 0:
        print("警告：数据库里没有 status=approved 的卡，页面会是空的。", file=sys.stderr)
    result = render_site(conn, args.out, status="approved", title=args.title)
    print("已生成离线复习页：{}".format(os.path.abspath(result["index"])))
    print("{} 张卡 · 双击 index.html 即可使用（数据存本机 localStorage）".format(result["cards"]))
    if args.open:
        try:
            os.startfile(os.path.abspath(result["index"]))  # type: ignore[attr-defined]
        except AttributeError:
            print("当前平台不支持自动打开，请手动打开上面的路径。")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    if args.format == "json":
        payload = export_payload(conn, status=None if args.status == "all" else args.status)
        if args.out:
            _write_json(args.out, payload)
            print("已导出 {} 张 → {}".format(len(payload["cards"]), os.path.abspath(args.out)), file=sys.stderr)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    cards = list_cards(conn, status=None if args.status == "all" else args.status)
    fields = ["id", "kind", "status", "prompt", "answer", "source", "line", "confidence"]
    output = open(args.out, "w", encoding="utf-8-sig", newline="") if args.out else sys.stdout
    try:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for card in cards:
            writer.writerow({field: getattr(card, field) for field in fields})
    finally:
        if args.out:
            output.close()
    if args.out:
        print("已导出 {} 张 → {}".format(len(cards), os.path.abspath(args.out)), file=sys.stderr)
    return 0


# ---------------------------------------------------------------- selfcheck


def _check(condition: bool, label: str, detail: str = "") -> bool:
    print("{} {}".format("PASS" if condition else "FAIL", label) + (" — " + detail if detail and not condition else ""))
    return condition


def cmd_selfcheck(args: argparse.Namespace) -> int:
    ok = True

    # 1. SM-2 手算对照：连续「记得」→ 1 / 6 / 15 / 38 天
    state = State()
    intervals = []
    day = date(2026, 1, 1)
    for _ in range(4):
        state = review(state, 3, day)
        intervals.append(state.interval)
        day = date.fromordinal(day.toordinal() + 1)
    ok &= _check(intervals == [1, 6, 15, 38], "SM-2 间隔序列 = 1/6/15/38", str(intervals))
    ok &= _check(abs(state.ef - 2.5) < 1e-9, "「记得」不改变 EF", str(state.ef))

    # 2. 忘记 → 次数清零、间隔回 1、EF 下降、lapse +1
    lapsed = review(State(ef=2.5, reps=3, interval=15), 1, date(2026, 1, 10))
    ok &= _check(
        lapsed.reps == 0 and lapsed.interval == 1 and lapsed.lapses == 1 and lapsed.ef < 2.5,
        "忘记会把间隔重置为 1 天",
        str(lapsed),
    )

    # 3. leech：第 8 次遗忘暂停
    leech = State(ef=2.5, reps=0, interval=1, lapses=7, due="2026-01-01")
    leech = review(leech, 1, date(2026, 1, 2))
    ok &= _check(leech.suspended and leech.lapses == 8, "第 8 次遗忘触发 leech 暂停", str(leech))

    # 4. 存储往返
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        conn = connect(db)
        try:
            card = Card(
                id="test-card-1",
                kind="definition",
                prompt="什么是测试？",
                answer="验证某个断言是否成立的过程。",
                source="demo.md",
                heading="测试",
                line=3,
                confidence=0.8,
            )
            card2 = Card(
                id="test-card-2",
                kind="cloze",
                prompt="填空：间隔重复的关键是____。",
                answer="在遗忘前复习",
                source="demo.md",
                heading="间隔重复",
                line=9,
                confidence=0.7,
            )
            upsert_cards(conn, [card, card2])
            updated = review(State(), 3, date(2026, 1, 1))
            record_review(conn, card.id, 3, updated, "2026-01-01")
            data = store_stats(conn, "2026-01-02")
            ok &= _check(data["due"] == 1 and data["reviewed_today"] == 0, "存储与到期统计", str(data))

            # 5. 构建与站点渲染
            examples = Path(__file__).resolve().parent.parent / "examples" / "notes"
            built = None
            if examples.is_dir():
                built = build_deck(str(examples), Options(), generated="selfcheck")
                ok &= _check(len(built.cards) >= 15, "示例笔记可抽出 ≥15 张卡", str(len(built.cards)))
                ok &= _check(all(c.source and c.line for c in built.cards), "每张卡都有来源与行号")
                site = os.path.join(tmp, "site")
                rendered = render_site(conn, site)
                deck_js = Path(site, "deck.js").read_text(encoding="utf-8")
                ok &= _check(
                    rendered["cards"] >= 1 and deck_js.startswith("window.RECALL_DECK"),
                    "离线站点渲染",
                    str(rendered),
                )
            else:
                ok &= _check(False, "示例笔记目录存在", str(examples))

            decision = apply_decisions(conn, rejected=[card2.id])
            ok &= _check(decision["rejected"] == 1, "审核决定写回", str(decision))

            # 6. 审核清单
            markdown = render_audit_markdown(built.cards[:3]) if built else ""
            ok &= _check(markdown.startswith("# ") and "| 1 |" in markdown, "抽样审核清单可生成")
        finally:
            conn.close()

    if not ok:
        print("SELF-CHECK FAILED")
        return 1
    print("SELF-CHECK OK（全部检查通过）")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    print("Recall {}（零第三方依赖，Python 3.9+）".format(__version__))
    return 0


# ---------------------------------------------------------------- doctor


def cmd_doctor(args: argparse.Namespace) -> int:
    opts = Options(min_confidence=args.min_confidence, include_gist=args.include_gist)
    try:
        diagnoses = diagnose_path(args.path, opts)
    except FileNotFoundError:
        raise UserError("找不到笔记路径：{}".format(args.path))
    if not diagnoses:
        raise UserError("没有找到 Markdown 笔记。")

    report = render_report(diagnoses)
    if args.out:
        directory = os.path.dirname(os.path.abspath(args.out))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
    if args.json:
        print(json.dumps([d.to_dict() for d in diagnoses], ensure_ascii=False, indent=2))
        return 0

    print("诊断 {} 篇笔记：".format(len(diagnoses)))
    for item in sorted(diagnoses, key=lambda d: -d.score):
        print("  {:>3} 分  {:>3} 张  {}".format(item.score, item.cards, item.source))
    average = sum(d.score for d in diagnoses) // max(1, len(diagnoses))
    total_cards = sum(d.cards for d in diagnoses)
    print("\n平均可出卡性 {} 分；预计可出 {} 张卡。".format(average, total_cards))
    low = [d for d in diagnoses if d.issues]
    if low:
        print("\n最值得改的 3 处：")
        shown = 0
        for item in sorted(low, key=lambda d: d.score):
            for issue in item.issues[:2]:
                print("  · {}：{}".format(item.source, issue))
                shown += 1
                if shown >= 3:
                    break
            if shown >= 3:
                break
    if args.out:
        print("\n完整报告：{}".format(os.path.abspath(args.out)))
    return 0


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recall",
        description="Recall（回响）：把 Markdown 笔记编译成可审核、可复习的卡片。",
    )
    parser.add_argument("--debug", action="store_true", help="内部错误时打印完整堆栈")
    sub = parser.add_subparsers(dest="command", required=True)

    common_db = argparse.ArgumentParser(add_help=False)
    common_db.add_argument("--db", default="recall.db", help="SQLite 路径（默认 recall.db）")

    p_build = sub.add_parser("build", help="扫描 Markdown，生成/更新卡组")
    p_build.add_argument("path", help="笔记目录或单个 .md 文件")
    p_build.add_argument("--out", default="", help="另存一份卡组 JSON")
    p_build.add_argument("--min-confidence", type=float, default=0.55, help="低于该置信度的候选直接丢弃（默认 0.55）")
    p_build.add_argument("--max-per-section", type=int, default=6, help="每节最多几张（默认 6）")
    p_build.add_argument("--max-per-file", type=int, default=40, help="每篇最多几张（默认 40）")
    p_build.add_argument("--kinds", default="", help="只保留这些类型，逗号分隔：heading-question,term-list,definition,explicit-qa,cloze,gist")
    p_build.add_argument("--include-gist", action="store_true", help="额外生成低置信度的「章节概述」卡")
    p_build.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    p_build.add_argument("--db", default="recall.db", help="SQLite 路径（默认 recall.db）")
    p_build.set_defaults(func=cmd_build)

    p_stats = sub.add_parser("stats", help="看卡组、到期与新卡")
    p_stats.add_argument("--db", default="recall.db")
    p_stats.add_argument("--today", default="", help="覆盖今天的日期（测试用）")
    p_stats.add_argument("--json", action="store_true")
    p_stats.set_defaults(func=cmd_stats)

    p_review = sub.add_parser("review", help="开始一轮复习")
    p_review.add_argument("--db", default="recall.db")
    p_review.add_argument("--limit", type=int, default=20, help="本轮最多几张（默认 20）")
    p_review.add_argument("--new-limit", type=int, default=20, help="本轮最多引入几张新卡（默认 20）")
    p_review.add_argument("--script", default="", help="非交互评分，如 4,3,4,1")
    p_review.add_argument("--today", default="", help="覆盖今天的日期（测试用）")
    p_review.add_argument("--include-candidates", action="store_true", help="连 candidate 一起复习")
    p_review.add_argument("--json", action="store_true", help="只输出 JSON 摘要（不打印卡片）")
    p_review.set_defaults(func=cmd_review)

    p_doctor = sub.add_parser("doctor", help="诊断笔记结构，解释为什么出不了卡")
    p_doctor.add_argument("path", help="笔记目录或单个 .md 文件")
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.add_argument("--out", default="", help="把完整报告写到 Markdown 文件")
    p_doctor.add_argument("--min-confidence", type=float, default=0.55)
    p_doctor.add_argument("--include-gist", action="store_true")
    p_doctor.set_defaults(func=cmd_doctor)

    p_sample = sub.add_parser("sample", help="随机抽样，生成可逐条打勾的审核清单")
    p_sample.add_argument("--db", default="recall.db")
    p_sample.add_argument("--n", type=int, default=30)
    p_sample.add_argument("--seed", type=int, default=7)
    p_sample.add_argument("--status", default="approved", choices=["approved", "candidate", "rejected", "all"])
    p_sample.add_argument("--kinds", default="")
    p_sample.add_argument("--title", default="Recall 抽样审核")
    p_sample.add_argument("--out", default="", help="写到文件（默认打印）")
    p_sample.set_defaults(func=cmd_sample)

    p_apply = sub.add_parser("apply", help="把 Web 导出的审核决定写回数据库")
    p_apply.add_argument("decisions", help="decisions.json 路径")
    p_apply.add_argument("--db", default="recall.db")
    p_apply.add_argument("--json", action="store_true")
    p_apply.set_defaults(func=cmd_apply)

    p_web = sub.add_parser("web", help="导出离线复习页（file:// 直接打开）")
    p_web.add_argument("--db", default="recall.db")
    p_web.add_argument("--out", default="site")
    p_web.add_argument("--title", default="Recall")
    p_web.add_argument("--open", action="store_true", help="生成后自动打开（Windows）")
    p_web.set_defaults(func=cmd_web)

    p_export = sub.add_parser("export", help="导出 JSON / CSV")
    p_export.add_argument("--db", default="recall.db")
    p_export.add_argument("--format", choices=["json", "csv"], default="json")
    p_export.add_argument("--status", default="approved", choices=["approved", "candidate", "rejected", "all"])
    p_export.add_argument("--out", default="")
    p_export.set_defaults(func=cmd_export)

    p_self = sub.add_parser("selfcheck", help="不依赖外部文件的自检")
    p_self.set_defaults(func=cmd_selfcheck)

    p_version = sub.add_parser("version", help="版本信息")
    p_version.set_defaults(func=cmd_version)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except UserError as exc:
        print("错误：{}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        if getattr(args, "debug", False):
            traceback.print_exc()
        else:
            print("内部错误：{}（加 --debug 看堆栈）".format(exc), file=sys.stderr)
        return 2
    finally:
        _close_connections()


if __name__ == "__main__":
    sys.exit(main())
