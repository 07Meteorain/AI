"""duolog.render —— 终端与 Markdown 渲染（契约 §8）。

为什么渲染要单独成层
--------------------
``MergeResult`` / ``Profile`` 是"事实"，终端表格和 PR 报告是"表达"。
把表达拆出来，算法模块就不必关心列宽、颜色和 80 列终端；反过来，
渲染层也不 import 算法模块——它只按契约字段做属性访问（鸭子类型），
因此主持人可以用 golden 数据单独渲染，也不会出现循环导入。

中文对齐是本模块的核心难点：一个汉字占两列、组合符占零列，用 ``len()``
算宽度会让表头整体错位，而且错位量随内容变化，极难排查。所以这里所有
列宽、截断与补白都走 ``display_width``。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping, Sequence
from typing import Any

__all__ = ["display_width", "render_terminal", "render_markdown"]

#: East Asian Width 中占两列的类别：Wide / Fullwidth
_WIDE_EAW = frozenset({"W", "F"})

#: 占零列的一般类别：非间距标记、包围标记、格式符（含 ZWJ）、控制符
_ZERO_WIDTH_CATEGORIES = frozenset({"Mn", "Me", "Cf", "Cc"})

#: 截断用的省略号（East Asian Width 为 Ambiguous，本项目按 1 列计）
_ELLIPSIS = "…"

#: 会干扰终端显示的控制字符映射（保留 \t \n \r，交给 _flatten 处理）
_UNSAFE_CONTROL_TRANSLATION = {
    code: " "
    for code in list(range(0x20)) + list(range(0x7F, 0xA0))
    if code not in (0x09, 0x0A, 0x0D)
}

#: 冲突裁决状态对应的终端颜色码
_CONFLICT_CODES = {"resolved": "36", "needs_review": "1;33"}


def _char_width(ch: str) -> int:
    """单个码点的显示宽度：组合符／控制符 0，宽字符 2，其余 1。"""
    if ch in ("\n", "\r"):
        return 0
    if unicodedata.combining(ch):
        return 0
    if unicodedata.category(ch) in _ZERO_WIDTH_CATEGORIES:
        return 0
    if unicodedata.east_asian_width(ch) in _WIDE_EAW:
        return 2
    return 1


def display_width(s: str) -> int:
    """返回字符串在等宽终端里占用的列数。

    为什么不用 ``len()``：一个汉字在终端里占两列，组合符（例如 ``e`` 后面
    跟 U+0301）占零列。用 ``len()`` 得到的宽度会让中文表头整体错位，且
    错位量随内容变化，是那种"看起来只是没对齐"却很难排查的 bug。
    这里按 East Asian Width 的 W/F 记 2、组合符记 0、换行不计，自己实现
    而不引入 ``wcwidth``，是为了守住"零第三方依赖"的硬约束。
    """
    total = 0
    for ch in s:
        total += _char_width(ch)
    return total


def _scrub(text: str) -> str:
    """把控制字符换成空格，防止日志正文向终端注入 ANSI/光标控制序列。

    契约要求 ``color=False`` 时输出里没有任何 ANSI 转义。渲染器自己可以做到
    不加，但正文里本来就带着 ESC 时也必须拦住，否则这条保证是假的。
    """
    if not any(ord(ch) < 0x20 or 0x7F <= ord(ch) < 0xA0 for ch in text):
        return text
    return text.translate(_UNSAFE_CONTROL_TRANSLATION)


def _flatten(value: Any) -> str:
    """把任意值压成单行文本：表格单元格一旦带换行，框线就会断裂。"""
    text = _scrub(str(value)).replace("\t", "    ")
    parts = [part.strip() for part in text.splitlines() if part.strip()]
    return " / ".join(parts)


def _truncate(text: str, limit: int) -> str:
    """按显示宽度截断并补省略号（不切断字符，也不误伤组合符）。"""
    if limit <= 0:
        return ""
    if display_width(text) <= limit:
        return text
    budget = max(0, limit - display_width(_ELLIPSIS))
    kept: list[str] = []
    used = 0
    for ch in text:
        width = _char_width(ch)
        if used + width > budget:
            break
        kept.append(ch)
        used += width
    return "".join(kept).rstrip() + _ELLIPSIS


def _pad(text: str, width: int, align: str = "left") -> str:
    """按**显示宽度**补空格，而不是按字符个数。"""
    gap = width - display_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def _render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    max_col: int,
    aligns: Sequence[str] | None = None,
    paint_cell: Callable[[int, int, str], str] | None = None,
) -> list[str]:
    """把二维文本画成框线表，列宽按 ``display_width`` 计算并受 ``max_col`` 限制。

    为什么每列独立截断：冲突理由可能是整段话，任它撑开会让 80 列终端自动
    换行，框线一换行整张表就散了。宁可截断加省略号，也保证表格几何完整。
    ``paint_cell`` 接收的是**已补白**的单元格文本，颜色只包在内容上，
    不会把转义序列算进宽度。
    """
    columns = len(headers)
    if columns == 0:
        return []
    cap = max(1, int(max_col))
    align_list = list(aligns) if aligns else []
    if len(align_list) < columns:
        align_list += ["left"] * (columns - len(align_list))

    grid = [[_flatten(cell) for cell in row] for row in rows]
    for row in grid:
        if len(row) != columns:
            raise ValueError("表格行的列数与表头不一致")

    widths: list[int] = []
    for idx in range(columns):
        width = display_width(_flatten(headers[idx]))
        for row in grid:
            width = max(width, display_width(row[idx]))
        widths.append(min(width, cap))

    def rule(left: str, middle: str, right: str) -> str:
        return left + middle.join("─" * (width + 2) for width in widths) + right

    head = [
        _pad(_truncate(_flatten(headers[idx]), widths[idx]), widths[idx], "center")
        for idx in range(columns)
    ]
    lines = [rule("┌", "┬", "┐"), "│ " + " │ ".join(head) + " │", rule("├", "┼", "┤")]

    for row_index, row in enumerate(grid):
        cells: list[str] = []
        for col_index in range(columns):
            text = _pad(
                _truncate(row[col_index], widths[col_index]),
                widths[col_index],
                align_list[col_index],
            )
            if paint_cell is not None:
                text = paint_cell(row_index, col_index, text)
            cells.append(text)
        lines.append("│ " + " │ ".join(cells) + " │")

    lines.append(rule("└", "┴", "┘"))
    return lines


class _Painter:
    """颜色开关的唯一出口。

    ``color=False`` 时所有方法都原样返回字符串。把判断集中在一个地方，
    就不会出现"某个新分支忘了关颜色"从而污染 ``--json`` 的事故。
    """

    def __init__(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def tone(self, text: str, code: str) -> str:
        if not self._enabled or not code:
            return text
        return "\x1b[" + code + "m" + text + "\x1b[0m"

    def bold(self, text: str) -> str:
        return self.tone(text, "1")

    def dim(self, text: str) -> str:
        return self.tone(text, "2")


def _stat(stats: Mapping[str, Any], key: str, default: int = 0) -> int:
    """从 stats 里安全取整数；缺失或类型不对时退回默认值，渲染不应抛异常。"""
    value = stats.get(key, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fmt_share(value: Any) -> str:
    """把 0~1 的占比渲染成百分数；保留一位小数是为了人读，不做四舍五入陷阱。"""
    try:
        return "{0:.1f}%".format(float(value) * 100.0)
    except (TypeError, ValueError):
        return "—"


def _fmt_tags(counts: Any, limit: int = 3) -> str:
    """把 ``{标签: 次数}`` 渲染成 ``SEL-1×2、SEL-2×1``。

    按次数降序、同次数按名称升序，保证同一份数据在任何机器上输出一致；
    超过 ``limit`` 类时折叠成"等 N 类"，N 是**剩余未展示**的类别数，
    不是总类别数——否则读者会把已展示的类别再算一遍。
    摘要与已展示项之间用空格而不是顿号：``决策×1、等 1 类`` 会被读成
    "决策"和"等 1 类"两个并列项，``决策×1 等 1 类`` 才是"还有 1 类"。
    """
    if not isinstance(counts, Mapping) or not counts:
        return "—"
    try:
        ordered = sorted(counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
    except (TypeError, ValueError):
        ordered = sorted(counts.items(), key=lambda kv: str(kv[0]))
    shown = "、".join(
        "{0}×{1}".format(name, ordered_value)
        for name, ordered_value in ordered[:limit]
    )
    if len(ordered) <= limit:
        return shown
    # 这里报的是"被折叠掉的剩余类别数"，不是总类别数：总类别数已在
    # 前面的条目里显示了一部分，再报总数会让读者以为还有那么多没显示。
    remainder = "等 {0} 类".format(len(ordered) - limit)
    return (shown + " " + remainder).strip() if shown else remainder


def _md_cell(value: Any) -> str:
    """转义 Markdown 表格单元格：``|`` 会切断列，换行会切断行。"""
    text = _scrub(str(value)).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("|", "\\|").replace("\n", "<br>")
    return text.strip()


def render_terminal(
    result: Any,
    prof: Any,
    *,
    color: bool = True,
    max_col: int = 40,
) -> str:
    """把合并结果与协作画像渲染成终端文本（概览 + 冲突清单 + 协作画像）。

    设计取向：先让人**扫一眼抓住重点**（指纹、统计、冲突、画像四块），
    再让人**逐条核对**（规则代号 + 中文理由）。表格用框线 + 显示宽度对齐，
    这是中文终端里唯一能保证列不歪的做法。
    ``color`` 由调用方决定而不是在模块内探测 tty，这样渲染函数保持纯函数：
    重定向到文件/管道时调用方传 ``False`` 就能拿到干净文本。
    ``max_col`` 是**单列**内容上限，不是整表宽度；长理由会被截断成单行。
    ``prof`` 允许为 ``None``（只渲染合并结果），方便算法模块未就位时先用
    golden 数据验收渲染层。
    """
    paint = _Painter(color)
    stats = getattr(result, "stats", {})
    if not isinstance(stats, Mapping):
        stats = {}
    items = list(getattr(result, "items", []) or [])
    conflicts = list(getattr(result, "conflicts", []) or [])
    fingerprint = str(getattr(result, "fingerprint", "") or "")

    lines: list[str] = []
    lines.append(paint.bold("duolog · 协作日志合并报告"))
    lines.append(paint.dim("─" * 36))
    lines.append("指纹  : " + (fingerprint or "（缺失）"))
    lines.append(
        "条目  : {0} 条（作者 {1} 人，原始条目 {2} 条）".format(
            _stat(stats, "total_items", len(items)),
            _stat(stats, "authors"),
            _stat(stats, "entries"),
        )
    )

    lines.append("")
    lines.append(paint.bold("概览"))
    pairs = [
        ("条目总数", _stat(stats, "total_items", len(items))),
        ("冲突条目", _stat(stats, "conflicts", len(conflicts))),
        ("单一来源", _stat(stats, "single")),
        ("双重确认", _stat(stats, "confirmed")),
        ("已裁决", _stat(stats, "resolved")),
        ("待复核", _stat(stats, "needs_review")),
        ("作者数", _stat(stats, "authors")),
        ("原始条目", _stat(stats, "entries")),
    ]
    half = (len(pairs) + 1) // 2
    overview_rows: list[list[str]] = []
    for index in range(half):
        left = pairs[index]
        right = pairs[index + half] if index + half < len(pairs) else ("", "")
        overview_rows.append([left[0], str(left[1]), right[0], str(right[1])])
    lines.extend(
        _render_table(
            ["指标", "数量", "指标", "数量"],
            overview_rows,
            max_col=max_col,
            aligns=["left", "right", "left", "right"],
        )
    )

    lines.append("")
    lines.append(paint.bold("冲突清单（{0} 条）".format(len(conflicts))))
    if not conflicts:
        lines.append("（无冲突：没有需要人工裁决的条目）")
    else:
        conflict_rows: list[list[str]] = []
        resolutions: list[str] = []
        for conflict in conflicts:
            resolution = str(getattr(conflict, "resolution", "") or "")
            resolutions.append(resolution)
            conflict_rows.append(
                [
                    str(getattr(conflict, "eid", "") or ""),
                    resolution or "—",
                    str(getattr(conflict, "rule", "") or "—"),
                    str(getattr(conflict, "note", "") or "—"),
                ]
            )

        def _paint_conflict(row_index: int, col_index: int, text: str) -> str:
            if col_index != 1 or row_index >= len(resolutions):
                return text
            return paint.tone(text, _CONFLICT_CODES.get(resolutions[row_index], ""))

        lines.extend(
            _render_table(
                ["事件", "裁决", "规则", "理由"],
                conflict_rows,
                max_col=max_col,
                aligns=["left", "left", "left", "left"],
                paint_cell=_paint_conflict,
            )
        )

    lines.append("")
    lines.append(paint.bold("协作画像"))
    if prof is None:
        lines.append("（未提供协作画像）")
    else:
        authors = tuple(getattr(prof, "authors", ()) or ())
        skill_tags = getattr(prof, "skill_tags", {}) or {}
        type_tags = getattr(prof, "type_tags", {}) or {}
        share = getattr(prof, "share", {}) or {}
        involvement: dict[str, int] = {}
        for item in items:
            for version in getattr(item, "versions", ()) or ():
                author = str(getattr(version, "author", "") or "")
                if author:
                    involvement[author] = involvement.get(author, 0) + 1
        profile_rows: list[list[str]] = []
        for author in authors:
            profile_rows.append(
                [
                    str(author),
                    str(involvement.get(author, 0)),
                    _fmt_share(share.get(author, 0.0)),
                    _fmt_tags(skill_tags.get(author, {})),
                    _fmt_tags(type_tags.get(author, {})),
                ]
            )
        lines.extend(
            _render_table(
                ["作者", "原始条目", "占比", "技能标签", "类型标签"],
                profile_rows,
                max_col=max_col,
                aligns=["left", "right", "right", "left", "left"],
            )
        )

        transfers = tuple(getattr(prof, "transfers", ()) or ())
        if transfers:
            lines.append("")
            lines.append(paint.bold("技能迁移"))
            for edge in transfers:
                skill = _scrub(str(getattr(edge, "skill", "") or ""))
                src = _scrub(str(getattr(edge, "src", "") or ""))
                dst = _scrub(str(getattr(edge, "dst", "") or ""))
                evidence = [
                    _scrub(str(x)) for x in (getattr(edge, "evidence", ()) or ())
                ]
                shown = "、".join(evidence[:6])
                if len(evidence) > 6:
                    shown += " 等 {0} 条".format(len(evidence))
                lines.append(
                    "  {0}  {1} → {2}  证据：{3}".format(skill, src, dst, shown or "—")
                )

    return "\n".join(lines)


def render_markdown(result: Any, prof: Any) -> str:
    """把合并结果与画像渲染成可直接贴进 PR 的 Markdown 报告。

    为什么不用终端框线：PR 是比例字体 + Markdown 渲染器，框线表会散架。
    这里用管道表，并把规则代号与中文理由并排列出，评审者不用回头翻契约；
    所有单元格里的 ``|`` 都会转义、正文换行压成 ``<br>``，保证表格不炸。
    输出是确定性的（不含时间戳），同一份合并结果永远得到同一份报告。
    """
    stats = getattr(result, "stats", {})
    if not isinstance(stats, Mapping):
        stats = {}
    items = list(getattr(result, "items", []) or [])
    conflicts = list(getattr(result, "conflicts", []) or [])
    fingerprint = str(getattr(result, "fingerprint", "") or "")

    lines: list[str] = []
    lines.append("# duolog 协作日志合并报告")
    lines.append("")
    lines.append("- 指纹：`{0}`".format(fingerprint or "（缺失）"))
    lines.append("- 合并条目：{0} 条".format(_stat(stats, "total_items", len(items))))
    lines.append(
        "- 作者：{0} 人；原始条目：{1} 条".format(
            _stat(stats, "authors"), _stat(stats, "entries")
        )
    )
    lines.append("")

    lines.append("## 概览")
    lines.append("")
    lines.append("| 指标 | 数量 |")
    lines.append("| --- | ---: |")
    overview = [
        ("条目总数", _stat(stats, "total_items", len(items))),
        ("单一来源", _stat(stats, "single")),
        ("双重确认", _stat(stats, "confirmed")),
        ("已裁决", _stat(stats, "resolved")),
        ("待复核", _stat(stats, "needs_review")),
        ("冲突条目", _stat(stats, "conflicts", len(conflicts))),
        ("作者数", _stat(stats, "authors")),
        ("原始条目", _stat(stats, "entries")),
    ]
    for label, value in overview:
        lines.append("| {0} | {1} |".format(label, value))
    lines.append("")

    lines.append("## 冲突清单")
    lines.append("")
    if not conflicts:
        lines.append("无冲突：所有条目都是单一来源或双重确认。")
    else:
        lines.append("| 事件 | 裁决 | 规则 | 参与版本 | 理由 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for conflict in conflicts:
            versions = tuple(getattr(conflict, "versions", ()) or ())
            version_text = "、".join(
                "{0}#{1}".format(
                    getattr(version, "author", ""), getattr(version, "clock", "")
                )
                for version in versions
            )
            lines.append(
                "| {0} | {1} | {2} | {3} | {4} |".format(
                    _md_cell(getattr(conflict, "eid", "")),
                    _md_cell(getattr(conflict, "resolution", "") or "—"),
                    _md_cell(getattr(conflict, "rule", "") or "—"),
                    _md_cell(version_text or "—"),
                    _md_cell(getattr(conflict, "note", "") or "—"),
                )
            )
    lines.append("")

    lines.append("## 协作画像")
    lines.append("")
    if prof is None:
        lines.append("（未提供协作画像）")
    else:
        authors = tuple(getattr(prof, "authors", ()) or ())
        skill_tags = getattr(prof, "skill_tags", {}) or {}
        type_tags = getattr(prof, "type_tags", {}) or {}
        share = getattr(prof, "share", {}) or {}
        involvement: dict[str, int] = {}
        for item in items:
            for version in getattr(item, "versions", ()) or ():
                author = str(getattr(version, "author", "") or "")
                if author:
                    involvement[author] = involvement.get(author, 0) + 1

        lines.append("| 作者 | 原始条目 | 占比 | 技能标签 | 类型标签 |")
        lines.append("| --- | ---: | ---: | --- | --- |")
        for author in authors:
            lines.append(
                "| {0} | {1} | {2} | {3} | {4} |".format(
                    _md_cell(author),
                    involvement.get(author, 0),
                    _md_cell(_fmt_share(share.get(author, 0.0))),
                    _md_cell(_fmt_tags(skill_tags.get(author, {}))),
                    _md_cell(_fmt_tags(type_tags.get(author, {}))),
                )
            )

        transfers = tuple(getattr(prof, "transfers", ()) or ())
        if transfers:
            lines.append("")
            lines.append("### 技能迁移")
            lines.append("")
            lines.append("| 技能 | 原拥有者 | 使用者 | 证据 |")
            lines.append("| --- | --- | --- | --- |")
            for edge in transfers:
                evidence = tuple(getattr(edge, "evidence", ()) or ())
                lines.append(
                    "| {0} | {1} | {2} | {3} |".format(
                        _md_cell(getattr(edge, "skill", "")),
                        _md_cell(getattr(edge, "src", "")),
                        _md_cell(getattr(edge, "dst", "")),
                        _md_cell("、".join(str(x) for x in evidence) or "—"),
                    )
                )

    review = [
        str(getattr(item, "eid", ""))
        for item in items
        if getattr(item, "status", "") == "needs_review"
    ]
    if review:
        lines.append("")
        lines.append("> **需要人工复核**：{0}".format("、".join(review)))

    return "\n".join(lines)
