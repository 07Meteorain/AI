"""duolog.explain —— 单事件溯源（契约 §8.1）。

为什么需要"溯源"而不是再加一张汇总表
------------------------------------
``merge`` 给的是结论，``render`` 给的是概览；但一个结论一旦被质疑，
读者需要的是**原始证据链**：这件事两个人各自怎么写的、按哪条规则裁的、
为什么是这个人赢。把 ``MergedItem.versions``（合并时已经按作者、时钟
排好序）原样摊开，才能让人自己复核，而不是要求他相信工具。

为什么所有宽度都走 ``render.display_width``
------------------------------------------
中文、组合符在终端里不是"一个字符一列"。这个模块只做一件事：把若干行
文本装进固定宽度的框里；如果宽度算错，整个框就会歪。渲染层的
``display_width`` 已经处理了 East Asian Width 与组合符，这里直接复用，
不另写一套（契约 §8.1 明确要求），也避免两套宽度规则在同一个终端里打架。

为什么先计算行、最后统一加边框
------------------------------
所有内容先按"内部可用宽度"折行，再由 ``_box`` 统一补白、加边框。这样
无论文本多长、是否含中文/控制字符，每一行的显示宽度都严格相等，测试
可以机械地校验"每行 display_width 相同"，不用逐个字段算。
"""

from __future__ import annotations

from typing import Any, List

from duolog.render import display_width

__all__ = ["explain", "explain_dict"]

#: 整个框的显示宽度（含左右边框）；72 列对 80 列终端留有余量。
_BOX_WIDTH = 72

#: 边框内部可用宽度：左右各 "│ " / " │" 共 4 列。
_INNER_WIDTH = _BOX_WIDTH - 4

#: 不允许出现在行首的标点（行首禁则）。中英文都列上，避免"中文断好了、
#: 英文标点却挂到下一行"的半吊子实现。
_FORBIDDEN_LINE_START = frozenset("，。、；：！？）〕〉》」』】”’…,.;:!?)]}")


def _clean_text(value: Any) -> str:
    """把任意值压成可安全打印的文本：控制字符转空格，制表符展开。

    日志正文是用户输入，里面可能混着 ESC 等控制字符；契约要求 explain
    的输出不含 ANSI，所以这里必须在进入排版前就把它们变成空格。
    换行保留，交给 ``_wrap`` 按段落处理。
    """
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    cleaned: List[str] = []
    for ch in text:
        code = ord(ch)
        if ch == "\n":
            cleaned.append(ch)
        elif code < 0x20 or 0x7F <= code < 0xA0:
            cleaned.append(" ")
        else:
            cleaned.append(ch)
    return "".join(cleaned)


def _wrap(text: Any, limit: int) -> List[str]:
    """按**显示宽度**折行，并做行首禁则处理。

    按字符逐个累加宽度，中文占两列、组合符占零列，因此不会出现"按
    ``len()`` 折行导致中文行超出框宽"的经典错误。空段落保留为空行。

    行首禁则采用**下移**而不是**上并**：折行点本来就已经贴着列宽上限，
    把标点并回上一行必然超宽；把上一行末尾的字符一起下移，标点就能跟住
    前文，且新行从更靠前的字符开始，仍由同一 ``display_width`` 规则继续
    贪心填充，任何一行都不会超过 ``limit``。移动后如果新行首仍是禁则
    标点，就继续向前多移一个字，直到行首不是禁则标点为止。
    """
    width_limit = max(1, int(limit))
    lines: List[str] = []
    for paragraph in _clean_text(text).split("\n"):
        paragraph = paragraph.rstrip()
        if not paragraph:
            lines.append("")
            continue
        start = 0
        while start < len(paragraph):
            used = 0
            end = start
            while end < len(paragraph):
                char_width = display_width(paragraph[end])
                if used + char_width > width_limit:
                    break
                used += char_width
                end += 1
            if end == start:
                # limit 连当前首字符的宽度都放不下（如 limit=1、首字是汉字）。
                # 此时无论如何都必须吐出这个字符并前进，否则 start 永远不动，
                # 会从"行宽超标"退化成死循环。
                lines.append(paragraph[start])
                start += 1
                continue
            if end >= len(paragraph):
                lines.append(paragraph[start:])
                break
            # 原折行点会让下一行以禁则标点开头：把上一行末尾的字一起下移。
            break_at = end
            while break_at > start and paragraph[break_at] in _FORBIDDEN_LINE_START:
                break_at -= 1
            if break_at == start:
                # 极端情况：本行开头本身就是禁则标点（文档以标点开头）。
                # 此时无法在不空行、不超宽的前提下满足禁则，保留原折点，
                # 避免死循环；limit 过窄的情况已在上面的 end == start 分支
                # 无条件吐出字符并前进。
                break_at = end
            lines.append(paragraph[start:break_at])
            start = break_at
    return lines or [""]


def _fit(text: str, width: int) -> str:
    """把文本截到不超过 ``width`` 显示列；极窄宽度下的兜底，正常不会触发。"""
    if display_width(text) <= width:
        return text
    kept: List[str] = []
    used = 0
    for ch in text:
        char_width = display_width(ch)
        if used + char_width > width:
            break
        kept.append(ch)
        used += char_width
    return "".join(kept)


def _pad(text: str, width: int) -> str:
    """按显示宽度补空格，保证每行在框里严格等宽。"""
    gap = width - display_width(text)
    return text + " " * gap if gap > 0 else text


def _emit(lines: List[str], text: Any, first_prefix: str = "", cont_prefix: str = "") -> None:
    """把一段文本折行后追加到 ``lines``，首行与续行可用不同缩进。"""
    if not cont_prefix:
        cont_prefix = first_prefix
    limit = _INNER_WIDTH - max(display_width(first_prefix), display_width(cont_prefix))
    for index, chunk in enumerate(_wrap(text, max(1, limit))):
        prefix = first_prefix if index == 0 else cont_prefix
        lines.append(prefix + chunk)


def _blank(lines: List[str]) -> None:
    """插入一个空行；``_box`` 会把它补成等宽的空行，不会破坏框线。"""
    lines.append("")


def _box(lines: List[str]) -> str:
    """给内容加固定宽度边框，返回不含末尾换行的纯文本。"""
    framed = ["┌" + "─" * (_BOX_WIDTH - 2) + "┐"]
    for line in lines:
        framed.append("│ " + _pad(_fit(line, _INNER_WIDTH), _INNER_WIDTH) + " │")
    framed.append("└" + "─" * (_BOX_WIDTH - 2) + "┘")
    return "\n".join(framed)


def _find_item(result: Any, eid: str) -> Any:
    """按 eid 找合并条目；找不到返回 ``None``（由调用方决定怎么提示）。"""
    target = str(eid)
    for item in getattr(result, "items", ()) or ():
        if str(getattr(item, "eid", "")) == target:
            return item
    return None


def _find_conflict(result: Any, eid: str) -> Any:
    """按 eid 找冲突记录；单版本/双重确认没有 Conflict，返回 ``None``。"""
    target = str(eid)
    for conflict in getattr(result, "conflicts", ()) or ():
        if str(getattr(conflict, "eid", "")) == target:
            return conflict
    return None


def _sorted_versions(versions: Any) -> List[Any]:
    """按 merge 的版本顺序 ``(author, clock, line, text, eid)`` 重排。

    ``MergedItem.versions`` 按契约本来就排好序；这里再排一次，是为了让
    手工构造的 result 也得到与 ``merge`` 相同的展示顺序，避免"同一份
    证据换个构造方式就换一个顺序"。
    """

    def key(version: Any) -> tuple:
        return (
            str(getattr(version, "author", "")),
            int(getattr(version, "clock", 0) or 0),
            int(getattr(version, "line", 0) or 0),
            str(getattr(version, "text", "")),
            str(getattr(version, "eid", "")),
        )

    return sorted(tuple(versions or ()), key=key)


def _winner_author(conflict: Any) -> str | None:
    """取终裁胜者的作者名；``winner is None``（R3）时返回 ``None``。

    只有 R1/R2/R4 会产生 winner；R0 是双方确认、single 只有一方，都不算
    "谁赢了"，因此也返回 ``None``——``winner`` 表达的是"裁决结果"，
    不是"这条事件是谁写的"。
    """
    if conflict is None:
        return None
    winner = getattr(conflict, "winner", None)
    if winner is None:
        return None
    author = str(getattr(winner, "author", "") or "")
    return author or None


def _verdict_line(item: Any, conflict: Any) -> str:
    """生成"终裁"一行：有人赢就写名字，否则写清为什么没有赢家。"""
    winner = _winner_author(conflict)
    rule = str(getattr(item, "rule", "") or "")
    if winner is not None:
        return "终裁：{0} 的版本胜出（{1}）".format(winner, rule or "规则见上")
    status = str(getattr(item, "status", "") or "")
    if status == "needs_review":
        return "终裁：无（needs_review，待人工复核）"
    if status == "confirmed":
        return "终裁：无（双重确认，版本间无分歧）"
    if status == "single":
        return "终裁：无（单一来源，唯一版本即结论）"
    return "终裁：无"


def _reason(item: Any, conflict: Any) -> str:
    """生成"终裁理由"：优先用 merge 写好的中文 note，缺省时按状态解释。"""
    if conflict is not None:
        note = str(getattr(conflict, "note", "") or "").strip()
        if note:
            return note
    status = str(getattr(item, "status", "") or "")
    rule = str(getattr(item, "rule", "") or "")
    count = len(tuple(getattr(item, "versions", ()) or ()))
    if status == "single":
        return "只有一条原始条目，直接采纳，不需要裁决。"
    if status == "confirmed":
        return "{0} 条版本的规范化正文一致，按 R0 取最长原始正文，不做裁决。".format(count)
    if rule:
        return "命中规则 {0}，但合并结果里没有裁决说明，请核对数据。".format(rule)
    return "无额外裁决说明。"


def explain_dict(result: Any, eid: str) -> dict | None:
    """把单个事件的溯源信息整理成可直接 ``json.dumps`` 的字典。

    为什么 versions 只给 ``author/clock/tags/text`` 而不再嵌套 Entry：
    这是给人复核的最小证据集，字段太多反而淹没重点；``tags`` 保持原始
    条目自己的顺序（不排序），因为它就是日志里写下的样子。
    eid 不存在返回 ``None``，让 CLI 能明确区分"没找到"（退出码 1）与
    "读文件/用法错误"（退出码 2）。
    """
    item = _find_item(result, eid)
    if item is None:
        return None

    versions = []
    for version in _sorted_versions(getattr(item, "versions", ()) or ()):
        versions.append(
            {
                "author": str(getattr(version, "author", "") or ""),
                "clock": int(getattr(version, "clock", 0) or 0),
                "tags": [str(tag) for tag in (getattr(version, "tags", ()) or ())],
                "text": str(getattr(version, "text", "") or ""),
            }
        )

    return {
        "eid": str(getattr(item, "eid", "") or ""),
        "status": str(getattr(item, "status", "") or ""),
        "rule": str(getattr(item, "rule", "") or ""),
        "winner": _winner_author(_find_conflict(result, eid)),
        "text": str(getattr(item, "text", "") or ""),
        "versions": versions,
    }


def explain(result: Any, eid: str) -> str:
    """把一个事件的全部原始版本、命中规则、终裁理由摊开成人读文本。

    输出是一个固定宽度的框：每一行（含边框）的 ``display_width`` 都等于
    ``_BOX_WIDTH``，因此终端里不会出现"中文把表格撑歪"的情况。框内布局
    依次是：事件/状态/规则 → 原始版本（含标签与正文）→ 终裁 → 理由 →
    合并正文。找不到 eid 时返回一段说明文字而不是抛异常，方便 CLI 之外
    的调用方（例如自检）安全地展示。
    """
    item = _find_item(result, eid)
    if item is None:
        return _box(
            [
                "未找到事件：{0}".format(eid),
                "",
                "请确认 eid 是否正确；可用 merge 子命令查看全部事件编号。",
            ]
        )

    conflict = _find_conflict(result, eid)
    versions = _sorted_versions(getattr(item, "versions", ()) or ())
    status = str(getattr(item, "status", "") or "")
    rule = str(getattr(item, "rule", "") or "") or "（无）"

    lines: List[str] = []
    _emit(lines, "事件：{0}".format(getattr(item, "eid", "") or ""))
    _emit(lines, "状态：{0}    命中规则：{1}".format(status, rule))
    _blank(lines)
    _emit(lines, "原始版本（{0} 条，按作者、时钟排序）".format(len(versions)))
    for index, version in enumerate(versions, start=1):
        tags = "、".join(str(tag) for tag in (getattr(version, "tags", ()) or ()))
        header = "[{0}] {1}  clock={2}  标签：{3}".format(
            index,
            getattr(version, "author", "") or "",
            getattr(version, "clock", 0),
            tags or "（无标签）",
        )
        _emit(lines, header, first_prefix="  ", cont_prefix="    ")
        _emit(lines, getattr(version, "text", "") or "", first_prefix="      ")
        if index < len(versions):
            _blank(lines)

    _blank(lines)
    _emit(lines, _verdict_line(item, conflict))
    _emit(lines, "理由：" + _reason(item, conflict), cont_prefix="  ")
    _blank(lines)
    _emit(lines, "合并正文：")
    _emit(lines, getattr(item, "text", "") or "", first_prefix="  ")
    return _box(lines)
