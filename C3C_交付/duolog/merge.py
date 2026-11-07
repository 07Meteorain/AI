"""duolog.merge —— 确定性合并与冲突裁决（SEL-1）。

为什么需要这一层
----------------
两位协作者各自维护自己的逻辑时钟，同一件事用同一个事件编号（eid）记录。
同一个 eid 可能只有一方记录（单版本），也可能双方都记录并且措辞一致
（双重确认），还可能双方各执一词（真冲突）。本模块把这几类情况显式区分：

- ``single``        只有一方记录，照原样采纳；
- ``confirmed``     多方记录且规范化正文一致，取最长原始正文以保留细节；
- ``resolved``      真冲突但能按 R1/R2/R4 规则裁决；
- ``needs_review``  真冲突且规则也拿不准，宁可交人复核，也不替人做决定。

为什么必须与输入顺序无关
------------------------
两份日志在命令行里的先后、``parse_log`` 返回的顺序都会影响"谁先被看到"，
如果实现偷偷依赖这个顺序，同一组数据换个输入顺序就会得到不同的指纹，
"可复现"就无从谈起。因此这里先按 ``eid_key`` 给全部条目排序，再分组、
再裁决，最后用排好序的 ``to_dict`` 结果算指纹。

标签语义（契约 §3.1，v1.3）
---------------------------
``MergedItem.tags`` 不是简单并集：**技能标签**是可叠加的参与证据，始终取并集；
**类型标签**是互斥语义，只看终裁版本（R1/R2/R4 取 winner 的类型，R3 与
single/confirmed 才取并集）。理由见 :func:`_merged_tags`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from duolog.model import TAG_TYPE, TYPE_DECISION, Entry, eid_key, fingerprint_of

__all__ = ["Conflict", "MergedItem", "MergeResult", "merge"]

_TYPE_PREFIX = TAG_TYPE + ":"

#: R1 认的"强语义标记"：带 ``类型:决策`` 的版本优先于时钟。
_DECISION_TAG = _TYPE_PREFIX + TYPE_DECISION


def _version_key(entry: Entry) -> Tuple[str, int, int, str, str]:
    """版本内部排序键：先作者、再逻辑时钟，最后用行号/正文兜底。

    契约要求 ``versions`` 按 ``(author, clock)`` 排序，是为了让互检的人
    能快速定位"谁在第几条写的"。额外的 ``line``/``text`` 只是为了在
    同一作者重复 eid 这种坏数据上仍然保持全序，避免排序结果随输入漂移。
    """
    return (entry.author, entry.clock, entry.line, entry.text, entry.eid)


def _longest_key(entry: Entry) -> Tuple[int, str, int, int, str]:
    """R0/R4 取"最长原始正文"时的排序键：长度降序，其余升序做确定性兜底。

    正文长度相同时必须有个固定选择，否则同一组条目换个输入顺序就会
    选中不同的原始写法（规范化后虽然相等，但空白差异会进入指纹）。
    """
    return (-len(entry.text), entry.author, entry.clock, entry.line, entry.text)


def _lines(text: str) -> List[str]:
    """把规范化正文拆成行序列；空正文视为零行。

    为什么空正文要当成零行而不是 ``[""]``：零行的"每一行"约束为空集，
    这样"空正文"才会被任何非空正文包含；否则空串会变成一个永远匹配不上
    的占位行，把 R4 变成永远不命中。
    """
    return text.split("\n") if text else []


def _is_line_subsequence(needle: List[str], haystack: List[str]) -> bool:
    """判断 ``needle`` 的每一行是否按顺序**整行**出现在 ``haystack`` 中。

    为什么不用 ``text in longer_text``：子串判断会让 ``实现`` 命中
    ``实现细节``，把"补充细节"误判成"同一句话的包含关系"；整行比较才符合
    "另一方的每一行按顺序整体出现"的语义，行序也才有意义。
    """
    if not needle:
        return True
    index = 0
    for line in haystack:
        if line == needle[index]:
            index += 1
            if index == len(needle):
                return True
    return False


def _pick_r4_winner(versions: Tuple[Entry, ...]) -> Optional[Entry]:
    """找出 R4 的终裁版本：其规范化正文按行完整包含其它所有版本。

    单看两个版本时，就是"一方行序列严格包含另一方"。多版本时要求同一个
    版本覆盖所有其它版本；只要有一个版本没被覆盖，就说明还存在独立说法，
    R4 不应该替人把独立说法吞掉（宁可落到 R3 交给人工）。
    多个候选必然共享同一规范化正文（互相包含 ⇒ 行序列相同），取原始正文
    最长者只是为了保留细节，不改变语义。
    """
    line_lists = [_lines(version.norm_text) for version in versions]
    candidates: List[Entry] = []
    for index, version in enumerate(versions):
        covers_all = True
        strict = False
        for other_index, other in enumerate(versions):
            if index == other_index:
                continue
            if _is_line_subsequence(line_lists[other_index], line_lists[index]):
                if other.norm_text != version.norm_text:
                    strict = True
            else:
                covers_all = False
                break
        if covers_all and strict:
            candidates.append(version)
    if not candidates:
        return None
    return sorted(candidates, key=_longest_key)[0]


def _merged_tags(
    versions: Tuple[Entry, ...], winner: Optional[Entry]
) -> Tuple[str, ...]:
    """按契约 §3.1 合并标签：技能并集，类型跟终裁版本。

    为什么不能一律取并集：``类型:决策`` 与 ``类型:实现`` 是互斥语义，
    R1 裁决给决策方后仍保留另一方的类型，会让同一次事件同时属于两类，
    下游 ``type_tags`` 分布统计直接作废（v1.3 修复的正是这个 bug）。
    技能标签相反——两人在同一件事上都用到 SEL-1 是叠加关系，丢掉反而
    漏计迁移证据。没有 winner（R3 / single / confirmed）时才让类型取并集。
    """
    tags = set()
    for version in versions:
        for tag in version.tags:
            if not tag.startswith(_TYPE_PREFIX):
                tags.add(tag)

    if winner is None:
        type_sources: Tuple[Entry, ...] = versions
    else:
        type_sources = (winner,)
    for version in type_sources:
        for tag in version.tags:
            if tag.startswith(_TYPE_PREFIX):
                tags.add(tag)
    return tuple(sorted(tags))


@dataclass(frozen=True)
class Conflict:
    """一次真冲突及其裁决依据。

    只有命中 R1/R2/R4/R3 的条目才会生成 ``Conflict``；R0 是双重确认，
    不算冲突。``winner`` 为 ``None`` 表示工具拒绝替人裁决（R3），此时
    ``resolution`` 为 ``needs_review``，CLI 的 ``--strict`` 应当据此返回
    非零退出码；R1/R2/R4 的 ``winner`` 一定非空。
    """

    eid: str
    versions: Tuple[Entry, ...]      # 参与冲突的原始条目，按 (author, clock) 排序
    winner: Optional[Entry]          # None 表示无法裁决
    rule: str                        # R1-决策优先 / R2-时钟较新 / R4-补充合并 / R3-无法裁决
    resolution: str                  # "resolved" | "needs_review"
    note: str                        # 一句话人读理由，中文


@dataclass
class MergedItem:
    """同一个 eid 合并之后的唯一条目。

    ``tags`` 按契约 §3.1 合并：技能标签始终取并集（技能是可叠加的参与
    证据），类型标签只看终裁版本（R1/R2/R4 取 winner 自己的类型；
    R3 / single / confirmed 取并集）。类型是互斥语义，一律取并集会让一次
    事件同时属于两类，下游类型分布统计失真。
    ``versions`` 不进入 JSON，但保留在对象上，供互检与渲染层追溯原文。
    """

    eid: str
    authors: Tuple[str, ...]         # 已排序、去重
    tags: Tuple[str, ...]            # 技能并集 + 终裁类型（见 §3.1），已排序、去重
    text: str                        # 合并后的最终正文
    status: str                      # "single" | "confirmed" | "resolved" | "needs_review"
    versions: Tuple[Entry, ...]      # 参与合并的原始条目，按 (author, clock) 排序
    rule: str                        # 触发规则代号；无冲突时用 ""

    def to_dict(self) -> dict:
        """按契约 §5 给出 JSON 形状。

        故意不输出 ``versions``：原始证据体积大，且属于内部追溯信息；
        ``--json`` 的消费者只需要最终结论。键名与契约逐字对齐，
        排序层不要依赖这里的键顺序（指纹走的是 ``canonical_json``）。
        """
        return {
            "eid": self.eid,
            "authors": list(self.authors),
            "tags": list(self.tags),
            "status": self.status,
            "rule": self.rule,
            "text": self.text,
        }


@dataclass
class MergeResult:
    """一次合并的完整结果：条目、冲突清单、指纹与统计。

    ``fingerprint`` 在构造时由排序后的条目计算一次并冻结；如果调用方
    事后原地重排 ``items``，指纹不会跟着变，所以调用方只应读取、不应修改。
    """

    items: List[MergedItem]
    conflicts: List[Conflict]
    fingerprint: str
    stats: Dict[str, int]

    def to_dict(self) -> dict:
        """按契约 §5 输出整个结果，``--json`` 可直接 ``json.dumps``。

        ``stats`` 复制一份再输出，避免调用方改到内部状态；``items`` 的顺序
        就是计算指纹时的顺序，这里绝不重排，否则展示顺序会和指纹脱节。
        """
        return {
            "version": 1,
            "fingerprint": self.fingerprint,
            "stats": dict(self.stats),
            "items": [item.to_dict() for item in self.items],
        }


def _merge_one(eid: str, versions: Tuple[Entry, ...]) -> Tuple[MergedItem, Optional[Conflict]]:
    """裁决单个 eid 的全部版本，返回 (MergedItem, 冲突或 None)。

    规则顺序严格按契约 §3：R0 双重确认 → R1 决策优先 → R2 时钟较新 →
    R4 补充合并 → R3 无法裁决。先判 R0 是因为"正文完全一致"根本不该进入
    冲突清单；R1 排在 R2 前，是因为时钟只是各人自记的逻辑值，不可跨人
    比较，决策标记才是强证据；R4 排在 R2 后，是因为"更完整"是内容层面的
    弱证据，不能推翻"时钟严格较新"这条已经成立的形式证据。
    """
    authors = tuple(sorted({v.author for v in versions}))

    # 单版本：没有分歧，也没有裁决可言。
    if len(versions) == 1:
        only = versions[0]
        return (
            MergedItem(
                eid=eid,
                authors=authors,
                tags=_merged_tags(versions, None),
                text=only.text,
                status="single",
                versions=versions,
                rule="",
            ),
            None,
        )

    # R0：规范化正文全同 → 双重确认。取最长原始正文，尽量保留细节。
    if len({v.norm_text for v in versions}) == 1:
        longest = sorted(versions, key=_longest_key)[0]
        return (
            MergedItem(
                eid=eid,
                authors=authors,
                tags=_merged_tags(versions, None),
                text=longest.text,
                status="confirmed",
                versions=versions,
                rule="R0",
            ),
            None,
        )

    # R1：恰好一个版本带 类型:决策。
    decision_makers = [v for v in versions if v.has_tag(_DECISION_TAG)]
    if len(decision_makers) == 1:
        winner = decision_makers[0]
        note = (
            "只有 %s 的版本带「%s」标签；决策是强语义证据，优先于时钟。"
            % (winner.author, _DECISION_TAG)
        )
        return (
            MergedItem(
                eid=eid,
                authors=authors,
                tags=_merged_tags(versions, winner),
                text=winner.text,
                status="resolved",
                versions=versions,
                rule="R1-决策优先",
            ),
            Conflict(
                eid=eid,
                versions=versions,
                winner=winner,
                rule="R1-决策优先",
                resolution="resolved",
                note=note,
            ),
        )

    # R2：最大 clock 严格大于其它所有版本。两人时钟不共享，所以只是弱证据。
    clocks = sorted((v.clock for v in versions), reverse=True)
    if len(clocks) >= 2 and clocks[0] > clocks[1]:
        newest = clocks[0]
        winner = next(v for v in versions if v.clock == newest)
        note = (
            "%s 的 clock=%d 严格大于其他版本；逻辑时钟跨人不可比，只能算弱证据。"
            % (winner.author, winner.clock)
        )
        return (
            MergedItem(
                eid=eid,
                authors=authors,
                tags=_merged_tags(versions, winner),
                text=winner.text,
                status="resolved",
                versions=versions,
                rule="R2-时钟较新",
            ),
            Conflict(
                eid=eid,
                versions=versions,
                winner=winner,
                rule="R2-时钟较新",
                resolution="resolved",
                note=note,
            ),
        )

    # R4：一方规范化正文按行完整包含其它所有版本 → 补充合并。
    r4_winner = _pick_r4_winner(versions)
    if r4_winner is not None:
        winner_lines = _lines(r4_winner.norm_text)
        covered = sorted(
            {
                other.author
                for other in versions
                if other is not r4_winner
                and _is_line_subsequence(_lines(other.norm_text), winner_lines)
            }
        )
        note = (
            "%s 的正文按行完整包含了 %s 的正文，属于补充而非反驳，取信息更完整者。"
            % (r4_winner.author, "、".join(covered) or "其他版本")
        )
        return (
            MergedItem(
                eid=eid,
                authors=authors,
                tags=_merged_tags(versions, r4_winner),
                text=r4_winner.text,
                status="resolved",
                versions=versions,
                rule="R4-补充合并",
            ),
            Conflict(
                eid=eid,
                versions=versions,
                winner=r4_winner,
                rule="R4-补充合并",
                resolution="resolved",
                note=note,
            ),
        )

    # R3：规则都拿不准。保留双方原话，按作者名排序列出，交给人工复核。
    merged_text = "\n".join(
        "【%s】%s" % (v.author, v.text) for v in sorted(versions, key=_version_key)
    )
    note = (
        "%d 个版本正文不一致，且没有唯一决策标记、也没有严格最新的时钟、"
        "也没有一方按行完整包含另一方；工具不替人裁决，按作者分栏保留原话等待复核。"
        % len(versions)
    )
    return (
        MergedItem(
            eid=eid,
            authors=authors,
            tags=_merged_tags(versions, None),
            text=merged_text,
            status="needs_review",
            versions=versions,
            rule="R3-无法裁决",
        ),
        Conflict(
            eid=eid,
            versions=versions,
            winner=None,
            rule="R3-无法裁决",
            resolution="needs_review",
            note=note,
        ),
    )


def merge(entries: Sequence[Entry]) -> MergeResult:
    """把两位作者的日志条目确定性合并成 :class:`MergeResult`。

    纯函数：不修改传入的 ``entries``，同样的条目多重集合无论以什么顺序
    传进来，``items`` 顺序、``fingerprint``、``stats`` 都完全相同。
    做法是先用 ``eid_key`` 给 eid 排序再逐个 eid 裁决，最后按
    ``(eid_key(eid), authors)`` 复排一次，让"合并顺序"与"展示顺序"一致。

    空输入是合法输入（两人都还没写日志），此时指纹固定、统计全为 0，
    调用方不需要为"空"写特例。
    """
    raw = list(entries)

    # 先聚合全部版本，再按 eid_key 排序处理，彻底摆脱输入顺序的影响。
    grouped: Dict[str, List[Entry]] = {}
    for entry in raw:
        grouped.setdefault(entry.eid, []).append(entry)

    items: List[MergedItem] = []
    conflicts: List[Conflict] = []
    for eid in sorted(grouped, key=eid_key):
        versions = tuple(sorted(grouped[eid], key=_version_key))
        item, conflict = _merge_one(eid, versions)
        items.append(item)
        if conflict is not None:
            conflicts.append(conflict)

    # 契约 §4 明确要求按 (eid_key(eid), authors) 排序后再算指纹。
    items.sort(key=lambda item: (eid_key(item.eid), item.authors))
    conflicts.sort(key=lambda conflict: eid_key(conflict.eid))

    stats: Dict[str, int] = {
        "total_items": len(items),
        "single": sum(1 for item in items if item.status == "single"),
        "confirmed": sum(1 for item in items if item.status == "confirmed"),
        "resolved": sum(1 for item in items if item.status == "resolved"),
        "needs_review": sum(1 for item in items if item.status == "needs_review"),
        "conflicts": len(conflicts),
        "authors": len({entry.author for entry in raw}),
        "entries": len(raw),
    }

    payload = {"version": 1, "items": [item.to_dict() for item in items]}
    return MergeResult(
        items=items,
        conflicts=conflicts,
        fingerprint=fingerprint_of(payload),
        stats=stats,
    )
