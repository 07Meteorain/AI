"""接口层：命令行。

十三条命令，覆盖"用一次"和"维护系统"两类动作：

    用一次        ask / chat / capture / recall / task / skill / review
    维护系统      promote / evolve / metrics / trend / trace / doctor

设计原则：**每一次调用都要能回答"我刚才做了什么、记到哪了"**。
所以除了 ``--json`` 之外，所有命令的最后都会打印一行记忆水位。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..app import App
from ..config import Config
from ..evolve import compute, evolve_once, render_trend, trend
from ..loop.planner import Intent
from ..memory.promote import apply_proposal, collect_proposals
from ..skills.scaffold import create_skill
from ..util import ensure_utf8_stdio, table, truncate
from . import render


class CommandError(Exception):
    """用户输入问题（不是系统故障）。退出码 2。"""


# ---------------------------------------------------------------------------
# 公共
# ---------------------------------------------------------------------------
def _app(args: argparse.Namespace) -> App:
    config = Config.load(getattr(args, "root", None))
    if getattr(args, "no_write", False):
        config.write_memory = False
    return App(config)


def _emit(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _print_answer(result: Any, app: App, args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        _emit(result.to_dict())
        return
    print(render.header("回答"))
    print(result.answer)
    print()
    print(render.receipt(result, verbose=getattr(args, "verbose", False)))
    print(render.memory_bar(app.memory))


# ---------------------------------------------------------------------------
# 命令
# ---------------------------------------------------------------------------
def cmd_ask(args: argparse.Namespace) -> int:
    app = _app(args)
    text = " ".join(args.text).strip()
    if not text:
        raise CommandError("问点什么吧（brain ask \"…\"）")
    result = app.ask(text, session=args.session)
    _print_answer(result, app, args)
    return 0


def cmd_recall(args: argparse.Namespace) -> int:
    app = _app(args)
    query = " ".join(args.query).strip()
    if not query:
        raise CommandError("要检索什么？")
    intent = Intent("recall", query, query, 1.0, "命令行 recall")
    result = app.ask(query, session=args.session, force_intent=intent)
    if args.json:
        _emit(result.to_dict())
        return 0
    hits = app.memory.search(
        query, top_k=args.k, layers=[args.layer] if args.layer else None, touch=False, include_echo=args.echo
    )
    print(render.header(f"检索 · {truncate(query, 40)}"))
    print(render.hits(hits) if hits else "没有命中。")
    print()
    print(render.memory_bar(app.memory))
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    app = _app(args)
    text = " ".join(args.text).strip()
    if not text:
        raise CommandError("要记什么？")
    intent = Intent("capture", text, text, 1.0, "命令行 capture", {"layer": args.layer})
    result = app.ask(text, session=args.session, force_intent=intent)
    _print_answer(result, app, args)
    return 0


def cmd_task(args: argparse.Namespace) -> int:
    app = _app(args)
    action = args.action or "list"
    ctx = app.context()
    if action == "list":
        rows = app.tools.call("task.list", {"status": args.status or "open"}, ctx)
        if not rows.ok:
            raise CommandError(rows.error)
        data = rows.data or []
        print(render.header("任务"))
        print(table([[r["id"], r["title"], r["status"], r.get("due") or "-"] for r in data], ["id", "标题", "状态", "截止"]) if data else "没有任务。")
        return 0
    if action == "add":
        title = " ".join(args.value).strip()
        if not title:
            raise CommandError("任务名呢？")
        res = app.tools.call("task.add", {"title": title, "detail": title}, ctx)
        if not res.ok:
            raise CommandError(res.error)
        print(f"已建任务 `{res.data['id']}`：{res.data['title']}")
        return 0
    if action == "done":
        target = " ".join(args.value).strip()
        if not target:
            raise CommandError("要关掉哪个任务？（id 或标题前缀）")
        res = app.tools.call("task.done", {"id": target}, ctx)
        if not res.ok:
            raise CommandError(res.error)
        print(f"任务 {res.data['task']} 已完成，行动记录 `{res.data['action_record']}`")
        print(render.memory_bar(app.memory))
        return 0
    raise CommandError(f"未知动作：{action}")


def cmd_skill(args: argparse.Namespace) -> int:
    app = _app(args)
    action = args.action or "list"
    if action == "list":
        print(render.header("技能"))
        print(app.skills.table())
        if app.loader.warnings:
            print("\n警告：")
            for w in app.loader.warnings:
                print(f"  ! {w}")
        return 0
    if action == "show":
        if not args.name:
            raise CommandError("看哪个技能？")
        print(app.loader.show(args.name))
        return 0
    if action == "run":
        if not args.name:
            raise CommandError("跑哪个技能？")
        raw = " ".join(args.value).strip()
        payload: dict[str, Any]
        if raw.startswith("{"):
            try:
                payload = json.loads(raw)
            except ValueError as exc:
                raise CommandError(f"参数不是合法 JSON：{exc}") from exc
        else:
            payload = {"query": raw, "text": raw}
        ctx = app.context()
        result = app.skills.run(args.name, payload, ctx=ctx)
        if args.json:
            _emit({"skill": result.skill, "ok": result.ok, "outputs": result.outputs, "error": result.error, "ms": result.ms})
        else:
            print(render.header(f"技能 · {result.skill}"))
            print(result.summary())
            if result.outputs:
                print()
                _emit(result.outputs)
        return 0 if result.ok else 1
    if action == "new":
        if not args.name:
            raise CommandError("新技能叫什么？")
        info = create_skill(app.config, args.name, description=args.desc or "（待填写）")
        print(info["reason"])
        if info.get("path"):
            print(f"路径：{info['path']}")
        return 0 if info.get("ok") else 1
    raise CommandError(f"未知动作：{action}")


def cmd_review(args: argparse.Namespace) -> int:
    app = _app(args)
    intent = Intent("review", args.week or "", args.week or "周复盘", 1.0, "命令行 review")
    result = app.ask(args.week or "周复盘", session=args.session, force_intent=intent)
    _print_answer(result, app, args)
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    app = _app(args)
    proposals = collect_proposals(app.memory)
    if not proposals:
        print("没有需要沉淀的记录。")
        return 0
    print(render.header("沉淀提议"))
    applied = 0
    for proposal in proposals:
        changed = apply_proposal(app.memory, proposal) if args.apply else False
        applied += 1 if changed else 0
        print(proposal.line())
    print()
    print(f"{'已落盘' if args.apply else '只看不改（加 --apply 才写入）'}：{applied} 处")
    return 0


def cmd_evolve(args: argparse.Namespace) -> int:
    app = _app(args)
    report = evolve_once(
        app.config,
        app.memory,
        app.loader,
        app.skills,
        apply=args.apply,
        min_runs=args.min_runs,
    )
    if args.json:
        _emit(
            {
                "runs": report.runs,
                "patterns": report.patterns,
                "drafts": report.drafts,
                "aliases": report.aliases,
                "proposals": report.proposals,
                "applied": report.applied,
                "stale_skills": report.stale_skills,
                "metrics": report.metrics,
                "trend": report.trend,
                "dry_run": report.dry_run,
            }
        )
        return 0
    print(report.render())
    if not args.apply:
        print("\n提示：加 --apply 才会真的写文件。改了什么会记进 memory/db/evolution.jsonl。")
    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    app = _app(args)
    traces = app.traces.all()
    metrics = compute(app.config, app.memory, traces, app.skills)
    if args.json:
        _emit({"metrics": metrics.as_dict(), "trend": trend(traces)})
        return 0
    print(metrics.render())
    print()
    print(render_trend(trend(traces)))
    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    app = _app(args)
    data = trend(app.traces.all())
    if args.json:
        _emit(data)
        return 0
    print(render_trend(data))
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    app = _app(args)
    rows = app.traces.recent(args.n)
    if args.json:
        _emit(rows)
        return 0
    print(render.header(f"最近 {len(rows)} 次运行"))
    print(
        table(
            [
                [t.get("started", "")[:19], t.get("intent", ""), t.get("status", ""), len(t.get("steps") or []), truncate(str(t.get("input", "")), 34)]
                for t in rows
            ],
            ["时间", "意图", "状态", "步数", "输入"],
        )
        if rows
        else "还没有 trace。先 brain ask \"…\"。"
    )
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    app = _app(args)
    print(app.describe())
    print("输入内容回车即执行；/help 看提示，/quit 退出。")
    while True:
        try:
            line = input("\n你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            break
        if line == "/help":
            print("直接说话即可。命令：capture 记 …｜recall 找 …｜任务 …｜任务 完成 …｜技能 <名>｜复盘。")
            continue
        result = app.ask(line, session=args.session)
        print()
        print(result.answer)
        print()
        print(render.receipt(result, verbose=args.verbose))
    print("再见。记忆已保存。")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    app = _app(args)
    checks: list[tuple[str, bool, str]] = []

    checks.append(("Python ≥ 3.9", sys.version_info >= (3, 9), sys.version.split()[0]))

    try:
        probe = app.config.db_dir / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(("记忆目录可写", True, app.config.rel(app.config.home)))
    except OSError as exc:
        checks.append(("记忆目录可写", False, str(exc)))

    stats = app.memory.stats()
    total = stats["layers"]["total"]["count"]
    index_ok = stats["index_size"] == total
    checks.append(("KSTAR 索引一致", index_ok, f"索引 {stats['index_size']} / 记录 {total}"))

    probe_ctx = app.context(allow_write=True)
    tool_res = app.tools.call("time.now", {}, probe_ctx)
    checks.append(("工具可调用", tool_res.ok, f"{len(app.tools.specs())} 个工具；time.now → {tool_res.data.get('iso') if tool_res.ok else tool_res.error}"))

    skills = app.loader.load_all(force=True)
    broken = [s.name for s in skills if s.status == "broken"]
    checks.append(("技能可加载", not broken and not app.loader.warnings, f"{len(skills)} 个（可执行 {sum(1 for s in skills if s.executable)}）；警告 {len(app.loader.warnings)}"))

    result = app.ask("doctor 自检", session="doctor", allow_write=False, persist=False)
    checks.append(("循环可运行", result.trace.status == "ok", f"{len(result.trace.steps)} 步 / {result.trace.duration_ms:.0f}ms（不写记忆）"))

    checks.append(("trace 可读", True, f"{app.traces.count()} 条历史"))

    rows = [[("✓" if ok else "✗"), name, detail] for name, ok, detail in checks]
    print(render.header("自检"))
    print(table(rows, ["", "检查", "详情"]))
    print()
    print(app.describe())
    all_ok = all(ok for _, ok, _ in checks)
    print("\n结论：" + ("全部通过" if all_ok else "有检查未通过，见上表 ✗"))
    return 0 if all_ok else 1


def cmd_import_notes(args: argparse.Namespace) -> int:
    """把一个目录里的 .md 批量导入 K 层。批量导入是"第二大脑"最现实的第一步。"""

    from pathlib import Path

    app = _app(args)
    root = Path(args.dir)
    if not root.is_dir():
        raise CommandError(f"不是目录：{root}")
    files = sorted(root.rglob("*.md"))
    if not files:
        raise CommandError("目录里没有 .md 文件")
    created = 0
    for path in files[: args.limit]:
        text = path.read_text(encoding="utf-8", errors="replace")
        body = text
        title = path.stem
        if text.startswith("---"):
            from ..skills.model import parse_front_matter

            try:
                meta, body = parse_front_matter(text)
                title = str(meta.get("title") or title)
            except ValueError:
                pass
        rec = app.memory.write(
            "K",
            body.strip()[: args.max_chars],
            title=title,
            tags=["import"],
            source=f"import:{path.name}",
            importance=0.6,
            dedupe=True,
        )
        created += 1
        if args.verbose:
            print(f"  + {rec.id}  {title}")
    print(f"导入 {created} 篇（目录 {root}），K 层现有 {len(app.memory.all('K'))} 条。")
    return 0


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brain",
        description="第二大脑：五层架构的长期智能体（默认离线可跑）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", help="项目根目录（默认是本包所在目录）")
    parser.add_argument("--session", default="cli", help="会话名，用于把多次运行串起来")
    parser.add_argument("--no-write", action="store_true", help="只读模式：不写任何记忆")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--verbose", action="store_true", help="显示计划与更多细节")

    # 同一组开关也挂在每个子命令上：`brain recall x --json` 比
    # `brain --json recall x` 更符合直觉。SUPPRESS 防止子命令的默认值
    # 覆盖掉写在子命令前面的全局值。
    common = argparse.ArgumentParser(add_help=False)
    for flag, kwargs in (
        ("--root", {"default": argparse.SUPPRESS}),
        ("--session", {"default": argparse.SUPPRESS}),
        ("--no-write", {"action": "store_true", "default": argparse.SUPPRESS}),
        ("--json", {"action": "store_true", "default": argparse.SUPPRESS}),
        ("--verbose", {"action": "store_true", "default": argparse.SUPPRESS}),
    ):
        common.add_argument(flag, **kwargs)

    sub = parser.add_subparsers(dest="cmd")

    def _p(name: str, **kwargs: Any) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], **kwargs)

    p = _p("ask", help="问一句，走完整循环")
    p.add_argument("text", nargs="+")

    _p("chat", help="交互式会话")

    p = _p("capture", help="记一条（默认 S，可 --layer K）")
    p.add_argument("text", nargs="+")
    p.add_argument("--layer", default="", choices=["", "K", "S"])

    p = _p("recall", help="检索记忆")
    p.add_argument("query", nargs="+")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--layer", default="")
    p.add_argument("--echo", action="store_true", help="连'问句回声'记录一起显示")

    p = _p("task", help="任务（list/add/done）")
    p.add_argument("action", nargs="?", default="list", choices=["list", "add", "done"])
    p.add_argument("value", nargs="*")
    p.add_argument("--status", default="open")

    p = _p("skill", help="技能（list/show/run/new）")
    p.add_argument("action", nargs="?", default="list", choices=["list", "show", "run", "new"])
    p.add_argument("name", nargs="?")
    p.add_argument("value", nargs="*")
    p.add_argument("--desc", default="")

    p = _p("review", help="周复盘（走 weekly-review 技能）")
    p.add_argument("week", nargs="?", default="")

    p = _p("promote", help="跑一遍沉淀规则")
    p.add_argument("--apply", action="store_true")

    p = _p("evolve", help="进化周期：挖重复流程 → 技能草稿 / 同义词 / 沉淀")
    p.add_argument("--apply", action="store_true", help="真的落盘（默认只看）")
    p.add_argument("--min-runs", type=int, default=3, help="同一工作流至少重复几次才固化")

    _p("metrics", help="度量：运行、工具、记忆、技能")
    _p("trend", help="前后半段对比")
    p = _p("trace", help="最近运行")
    p.add_argument("-n", type=int, default=8)
    _p("doctor", help="五层自检")
    p = _p("import-notes", help="批量导入 .md 到 K 层")
    p.add_argument("dir")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--max-chars", type=int, default=4000)
    _p("version", help="版本")

    return parser


HANDLERS = {
    "ask": cmd_ask,
    "chat": cmd_chat,
    "capture": cmd_capture,
    "recall": cmd_recall,
    "task": cmd_task,
    "skill": cmd_skill,
    "review": cmd_review,
    "promote": cmd_promote,
    "evolve": cmd_evolve,
    "metrics": cmd_metrics,
    "trend": cmd_trend,
    "trace": cmd_trace,
    "doctor": cmd_doctor,
    "import-notes": cmd_import_notes,
}


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    if args.cmd == "version":
        from .. import __version__

        print(f"brain {__version__}")
        return 0
    handler = HANDLERS.get(args.cmd)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler(args)
    except CommandError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断（已完成的部分已写入记忆）", file=sys.stderr)
        return 130
