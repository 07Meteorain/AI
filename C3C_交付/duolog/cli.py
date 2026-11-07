"""duolog.cli —— 命令行入口（契约 §9）。

为什么把退出码集中在一处
------------------------
``0 / 1 / 2`` 是给 CI 和主持人脚本用的**接口**，不是给人看的提示。
把它写成 ``main() -> int``、每条分支都显式 return，比散落的 ``sys.exit()``
更容易测试，也避免"打印了错误却退出 0"这种最伤自动化的 bug。

为什么 ``--json`` 与终端渲染互斥
--------------------------------
JSON 是给机器消费的：stdout 里多一行中文表头就会解析失败。所以 ``--json``
时 stdout **只**写 JSON，所有解析告警都走 stderr；终端渲染根本不执行。

``--out`` 与 ``--report`` 的分工
--------------------------------
``--out`` 写的是"合并后的 Markdown 日志"（能被 ``parse_log`` 再次读回，
形成闭环）；``--report`` 写的才是给人看的报告（``render_markdown`` 的结果）。
两者形状不同，不要混用。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from duolog.analyze import profile as build_profile
from duolog.explain import explain, explain_dict
from duolog.merge import merge
from duolog.model import ParseIssue, parse_log
from duolog.render import render_markdown, render_terminal

__all__ = ["main", "build_parser"]

#: selfcheck 内置样例 A（不依赖任何外部文件）。刻意覆盖 R0/R1/R2/R3 四种裁决。
_SELFCHECK_A = """# 协作者日志 · Aster

## E-001 | 1 | 类型:分工,技能:SEL-1
契约冻结：Aster 负责 merge/analyze，Bramble 负责 render/cli。

## E-003 | 2 | 类型:决策,技能:SEL-1
冲突裁决顺序：R1 决策优先 → R2 时钟较新 → R3 无法裁决。

## E-005 | 2 | 类型:实现
指纹必须先把条目按 eid_key 排序再算。

## E-007 | 4 | 类型:互检
审 render.py：中文列宽必须用显示宽度计算。

## E-009 | 5 | 类型:评审
发布前是否跑 --strict，我倾向跑。
"""

#: selfcheck 内置样例 B。与 A 组合后：E-001/E-007 双重确认，E-003 决策优先，
#: E-005 时钟较新，E-009 无法裁决。
_SELFCHECK_B = """# 协作者日志 · Bramble

## E-001 | 1 | 类型:分工,技能:SEL-2
契约冻结：Aster 负责 merge/analyze，Bramble 负责 render/cli。

## E-003 | 2 | 类型:实现
冲突直接取时钟最大者就行，不必分级。

## E-007 | 2 | 类型:互检
审 render.py：中文列宽必须用显示宽度计算。

## E-005 | 3 | 类型:实现
排序键直接用 eid_key，别再另造一套，指纹同理。

## E-009 | 5 | 类型:评审
发布前不用 --strict，样例里没有 needs_review。
"""

#: selfcheck 使用的技能归属（与契约 §7 的示例一致）
_SELFCHECK_OWNERS = {"SEL-1": "Aster", "SEL-2": "Bramble"}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 主入口：解析参数、分派子命令、返回进程退出码。

    为什么返回 ``int`` 而不是直接 ``sys.exit``：``main`` 可以被测试直接调用，
    ``__main__.py`` 只负责把返回值交给 ``sys.exit``，职责单一，行为不会分叉。
    """
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        # argparse 对 --help 会以 0 退出、对用法错误以 2 退出；
        # 这里把 SystemExit 翻译成返回值，让 main() 对调用方始终是"总函数"。
        return exc.code if isinstance(exc.code, int) else 0
    command = getattr(args, "command", None)
    if command == "merge":
        return _run_merge(args)
    if command == "explain":
        return _run_explain(args)
    if command == "selfcheck":
        return _run_selfcheck()
    parser.print_help(sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    """构造参数解析器。

    单独抽成函数，是为了让宿主与测试能拿到同一份参数定义（例如 ``--help``
    快照），避免测试自己另造一套参数而与真实 CLI 漂移。
    """
    parser = argparse.ArgumentParser(
        prog="duolog",
        description="把两份协作日志按事件编号确定性合并，并输出协作画像。",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="子命令", required=True)

    merge_parser = subparsers.add_parser(
        "merge", help="合并两份日志", description="合并两份日志并输出结果。"
    )
    merge_parser.add_argument("--a", required=True, metavar="PATH", help="协作者 A 的日志")
    merge_parser.add_argument("--b", required=True, metavar="PATH", help="协作者 B 的日志")
    merge_parser.add_argument("--author-a", default="A", metavar="NAME", help="A 的作者名（默认 A）")
    merge_parser.add_argument("--author-b", default="B", metavar="NAME", help="B 的作者名（默认 B）")
    merge_parser.add_argument(
        "--out", metavar="PATH", help="写合并后的 Markdown 日志（可被再次解析，形成闭环）"
    )
    merge_parser.add_argument("--report", metavar="PATH", help="写 render_markdown 报告")
    merge_parser.add_argument(
        "--json", action="store_true", help="把 MergeResult.to_dict() 以 JSON 写到 stdout"
    )
    merge_parser.add_argument("--no-color", action="store_true", help="禁用终端颜色")
    merge_parser.add_argument(
        "--strict", action="store_true", help="存在 needs_review 时以退出码 1 失败"
    )
    merge_parser.add_argument(
        "--skill-owner",
        action="append",
        default=None,
        metavar="技能=作者",
        help="指定技能原拥有者，可重复；默认 SEL-1→A、SEL-2→B",
    )
    merge_parser.set_defaults(command="merge")

    explain_parser = subparsers.add_parser(
        "explain",
        help="溯源单个事件",
        description="摊开一个事件的全部原始版本、命中规则与终裁理由。",
    )
    explain_parser.add_argument("--a", required=True, metavar="PATH", help="协作者 A 的日志")
    explain_parser.add_argument("--b", required=True, metavar="PATH", help="协作者 B 的日志")
    explain_parser.add_argument(
        "--eid", required=True, metavar="EID", help="要溯源的事件编号，例如 E-003"
    )
    explain_parser.add_argument(
        "--author-a", default="A", metavar="NAME", help="A 的作者名（默认 A）"
    )
    explain_parser.add_argument(
        "--author-b", default="B", metavar="NAME", help="B 的作者名（默认 B）"
    )
    explain_parser.add_argument(
        "--json", action="store_true", help="把 explain_dict() 以 JSON 写到 stdout"
    )
    explain_parser.add_argument(
        "--no-color",
        action="store_true",
        help="兼容 merge 的通用参数；explain 输出本来就不含 ANSI，此开关不改变结果",
    )
    explain_parser.set_defaults(command="explain")

    selfcheck_parser = subparsers.add_parser(
        "selfcheck", help="零参数自检", description="用内置样例跑通解析→合并→渲染。"
    )
    selfcheck_parser.set_defaults(command="selfcheck")
    return parser


def _load_entries(pairs: Sequence[tuple[str, str]]) -> tuple[list, bool] | None:
    """读取并解析若干 ``(路径, 作者)`` 日志，统一打印解析告警。

    为什么抽成函数：merge 与 explain 必须对"文件读不了"和"解析出现 error"
    做出完全一致的判定（退出码 2 vs 1）。各写一份循环，迟早会出现"改了
    merge 忘了 explain"的接口漂移。

    为什么读失败时先打印已累积的 ParseIssue：两个输入里前一个的坏表头，
    往往比后一个文件不存在更接近问题根因。如果读到第二个文件失败就直接
    return，前面已经解析出的告警会被静默吞掉，用户只能看到一个次要错误。
    因此这里先 flush 告警、再报读文件失败，最后才返回 ``None``。
    """
    entries: list = []
    problems: list[tuple[str, ParseIssue]] = []
    read_errors: list[str] = []
    has_error = False

    for path, author in pairs:
        text, read_error = _read_text_quiet(path)
        if read_error is not None:
            read_errors.append(read_error)
            break
        parsed, issues = parse_log(text, author)
        entries.extend(parsed)
        for issue in issues:
            problems.append((path, issue))
            if issue.level == "error":
                has_error = True

    for path, issue in problems:
        print(
            "duolog: {0}:{1}: [{2}] {3}".format(path, issue.line, issue.level, issue.message),
            file=sys.stderr,
        )
    for read_error in read_errors:
        print(read_error, file=sys.stderr)

    if read_errors:
        return None
    return entries, has_error


def _run_merge(args: argparse.Namespace) -> int:
    """执行 merge 子命令；返回值就是进程退出码。"""
    if not args.author_a.strip() or not args.author_b.strip():
        print("duolog: --author-a/--author-b 不能为空", file=sys.stderr)
        return 2

    loaded = _load_entries(((args.a, args.author_a), (args.b, args.author_b)))
    if loaded is None:
        return 2
    entries, has_error = loaded

    if has_error:
        # 解析出 error 时宁可中止：基于残缺条目录出的报告看起来"完整"，
        # 反而会误导人，也会把不完整的 --out 日志带进下一轮闭环。
        print("duolog: 解析出现 error，已中止（未写任何输出文件）", file=sys.stderr)
        return 1

    owners = _resolve_skill_owners(args)
    if owners is None:
        return 2

    result = merge(entries)
    prof = build_profile(result.items, owners)

    try:
        if args.out:
            _write_text(args.out, _render_merged_log(result))
        if args.report:
            _write_text(args.report, render_markdown(result, prof))
    except OSError as exc:
        print("duolog: 无法写入输出文件：{0}".format(exc), file=sys.stderr)
        return 2

    if args.json:
        # 只在 --json 下写 JSON，绝不调用 render_terminal，保证 stdout 无 ANSI。
        payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        _write_stdout(payload + "\n")
    else:
        use_color = (not args.no_color) and sys.stdout.isatty()
        _write_stdout(render_terminal(result, prof, color=use_color) + "\n")

    needs_review = int(result.stats.get("needs_review", 0))
    if args.strict and needs_review > 0:
        print(
            "duolog: --strict 且存在 {0} 条 needs_review".format(needs_review),
            file=sys.stderr,
        )
        return 1
    return 0


def _run_explain(args: argparse.Namespace) -> int:
    """执行 explain 子命令：解析 → 合并 → 摊开单个事件的证据链。

    先用 ``explain_dict`` 判断 eid 是否存在：``explain()`` 的契约返回 str，
    没地方表达"找不到"。把存在性检查放在 CLI 层，既能给出退出码 1，又能
    把错误写到 stderr，让 stdout（尤其是 ``--json``）保持干净。
    """
    if not args.author_a.strip() or not args.author_b.strip():
        print("duolog: --author-a/--author-b 不能为空", file=sys.stderr)
        return 2

    loaded = _load_entries(((args.a, args.author_a), (args.b, args.author_b)))
    if loaded is None:
        return 2
    entries, has_error = loaded
    if has_error:
        print("duolog: 解析出现 error，已中止（未输出溯源结果）", file=sys.stderr)
        return 1

    result = merge(entries)
    payload = explain_dict(result, args.eid)
    if payload is None:
        print("duolog: 未找到事件 {0}".format(args.eid), file=sys.stderr)
        return 1

    if args.json:
        # 与 merge --json 用同一套序列化参数，机器消费端不用区分来源。
        _write_stdout(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        _write_stdout(explain(result, args.eid) + "\n")
    return 0


def _run_selfcheck() -> int:
    """零参数自检：内置两段日志 → 解析 → 合并 → 画像 → 两种渲染。

    它不读任何文件，因此可以在任何工作目录下跑；任何一步抛出异常都算失败，
    并用退出码 1 明确告诉调用方"这套环境跑不通"，而不是糊里糊涂打印 ok。
    """
    try:
        entries = []
        for text, author in ((_SELFCHECK_A, "Aster"), (_SELFCHECK_B, "Bramble")):
            parsed, issues = parse_log(text, author)
            for issue in issues:
                if issue.level == "error":
                    raise RuntimeError("内置样例解析失败：{0}".format(issue))
            entries.extend(parsed)

        result = merge(entries)
        prof = build_profile(result.items, _SELFCHECK_OWNERS)
        terminal = render_terminal(result, prof, color=False)
        markdown = render_markdown(result, prof)
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 - 自检要把任何失败都翻译成退出码 1
        print("selfcheck: failed: {0}".format(exc), file=sys.stderr)
        return 1

    if not result.items or not result.fingerprint:
        print("selfcheck: failed: 合并结果为空", file=sys.stderr)
        return 1
    if "\x1b" in terminal or "\x1b" in markdown or "\x1b" in payload:
        print("selfcheck: failed: color=False 时检测到 ANSI 转义", file=sys.stderr)
        return 1

    print("selfcheck: ok {0}".format(result.fingerprint))
    return 0


def _resolve_skill_owners(args: argparse.Namespace) -> dict[str, str] | None:
    """解析 ``--skill-owner``，补上契约约定的默认归属。

    默认值跟随 ``--author-a/--author-b``，因为契约 §0 规定 SEL-1 归 A、
    SEL-2 归 B；作者名一改，归属也应跟着改，否则迁移边会算空。
    格式错误返回 ``None``，由调用方转成退出码 2。
    """
    owners = {"SEL-1": args.author_a, "SEL-2": args.author_b}
    for spec in args.skill_owner or []:
        if "=" not in spec:
            print(
                "duolog: --skill-owner 需要 技能=作者 形式，收到 {0!r}".format(spec),
                file=sys.stderr,
            )
            return None
        skill, author = spec.split("=", 1)
        skill = skill.strip()
        author = author.strip()
        if not skill or not author:
            print("duolog: --skill-owner 的技能名与作者名都不能为空", file=sys.stderr)
            return None
        owners[skill] = author
    return owners


def _render_merged_log(result: Any) -> str:
    """把合并结果写成能被 ``parse_log`` 再次读回的 Markdown 日志（``--out``）。

    为什么 header 里的 clock 取参与版本的**最大值**：合并后的条目不再属于
    单一作者，也没有单一逻辑时钟；取最大值只是为了让重读时 header 合法。
    这个 clock 不参与任何语义判断，换个值也只会改变重读后的 clock 字段。
    """
    lines: list[str] = [
        "# duolog 合并日志",
        "",
        "<!-- 由 duolog 生成；本文件可被 parse_log 再次读回。 -->",
        "<!-- fingerprint: {0} -->".format(getattr(result, "fingerprint", "") or ""),
        "",
    ]
    for item in getattr(result, "items", []) or []:
        versions = tuple(getattr(item, "versions", ()) or ())
        clock = 1
        if versions:
            clock = max(int(getattr(version, "clock", 1)) for version in versions)
        clock = max(1, clock)
        tags = ",".join(str(tag) for tag in (getattr(item, "tags", ()) or ()))
        lines.append(
            "## {0} | {1} | {2}".format(
                getattr(item, "eid", ""), clock, tags
            )
        )
        lines.append(str(getattr(item, "text", "") or ""))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _read_text_quiet(path: str) -> tuple[str | None, str | None]:
    """读 UTF-8 文本；失败时返回 ``(None, 人读错误)``，打印时机交给调用方。

    为什么不让它直接 ``print``：``_load_entries`` 需要先打印已经解析出的
    ParseIssue，再报"这个文件读不了"。如果读取时立刻打印，读文件错误会
    盖在坏表头前面，顺序正好反了。``_read_text`` 保留原来的即时打印语义，
    供需要"读一个文件立刻报错"的调用方使用。
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read(), None
    except OSError as exc:
        return None, "duolog: 无法读取输入文件 {0}: {1}".format(path, exc)
    except UnicodeDecodeError as exc:
        return None, "duolog: 输入文件不是合法 UTF-8（{0}）：{1}".format(path, exc)


def _read_text(path: str) -> str | None:
    """读 UTF-8 文本；失败时打印原因并返回 ``None``（调用方转成退出码 2）。"""
    text, read_error = _read_text_quiet(path)
    if read_error is not None:
        print(read_error, file=sys.stderr)
    return text


def _write_text(path: str, text: str) -> None:
    """以 UTF-8 + LF 写文件。

    固定换行符是为了让同一输入在不同平台得到相同字节；``--out`` 的相对路径
    由当前工作目录解析（直接交给 ``open``），不写死任何绝对路径。
    """
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _write_stdout(text: str) -> None:
    """写 stdout；终端编码容不下某些字符时用替换字符兜底，避免整份报告丢失。"""
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.write(text.encode(encoding, "replace").decode(encoding, "replace"))
    sys.stdout.flush()
