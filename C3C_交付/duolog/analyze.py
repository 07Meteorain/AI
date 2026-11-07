"""duolog.analyze —— 协作画像与技能迁移分析。

为什么单独一层
--------------
``merge`` 只回答"同一事件最终是什么"；本模块回答"谁在哪类事情上留下了
多少痕迹、技能有没有从拥有者流向另一个人"。画像的每个数字都只由**原始
条目**（``item.versions``）支撑，不使用合并后的标签并集——这是契约 v1.2
统一后的口径；技能拥有者即使一条没写也会出现在 ``authors`` 里，保证
"谁在这个队里"不被日志数量悄悄抹掉。

为什么计数按"条目"而不是"字数"
------------------------------
日志是事件粒度的，一条记录就是一次可追溯的协作动作；按字数会让
"写得多"压过"做得对"，也会因合并正文的截取方式而漂移。所以所有
计数与占比的分母都是条目数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

from duolog.merge import MergedItem
from duolog.model import TAG_SKILL, TAG_TYPE, eid_key

__all__ = ["Profile", "TransferEdge", "profile"]

_SKILL_PREFIX = TAG_SKILL + ":"
_TYPE_PREFIX = TAG_TYPE + ":"


@dataclass(frozen=True)
class TransferEdge:
    """一条"技能迁移"证据：某项技能被非拥有者使用了。

    ``evidence`` 收集全部 eid 而不是只留一个：同一对人有多次迁移时，
    互检需要看到完整证据链；用元组是为了让这条边不可变、可安全共享。
    """

    src: str                     # 技能原拥有者
    dst: str                     # 使用该技能的人
    skill: str                   # 形如 "SEL-1"
    evidence: Tuple[str, ...]    # 支撑该迁移的 eid，按 eid_key 排序

    def to_dict(self) -> dict:
        """给出可 JSON 化的边表示（``Profile.to_dict`` 复用）。"""
        return {
            "src": self.src,
            "dst": self.dst,
            "skill": self.skill,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class Profile:
    """两位协作者的整体画像。

    所有按人统计的数字都来自**原始条目**（``item.versions``），这是契约
    v1.2 统一后的口径：``skill_tags`` / ``type_tags`` 只统计某人自己写下
    的那条日志带的标签，``transfers`` 同理，``share`` 的分母也是原始条目
    总数。这样画像、迁移边、占比三者互相自洽，不会出现"有计数、无迁移边"
    这种让人先怀疑工具的裂缝。

    ``authors`` 额外并入 ``skill_owner`` 里的非空作者名：队里有人一条都
    没写时，他仍应出现在画像里（``share`` 为 0.0），而不是悄悄消失。
    """

    authors: Tuple[str, ...]                 # 已排序
    skill_tags: Dict[str, Dict[str, int]]    # author -> skill -> 条目数
    type_tags: Dict[str, Dict[str, int]]     # author -> 类型 -> 条目数
    transfers: Tuple[TransferEdge, ...]      # 按 (skill, src, dst) 排序
    share: Dict[str, float]                  # author -> 条目占比，保留 4 位小数

    def to_dict(self) -> dict:
        """按契约 §7 输出可直接 ``json.dumps`` 的结构。

        内部字典按键排序后再输出，保证同一份输入得到同样的字节顺序；
        ``share`` 只做展示用的格式化交给渲染层，这里保持 float 原值。
        """
        return {
            "authors": list(self.authors),
            "skill_tags": {
                author: _sorted_bucket(self.skill_tags.get(author, {}))
                for author in self.authors
            },
            "type_tags": {
                author: _sorted_bucket(self.type_tags.get(author, {}))
                for author in self.authors
            },
            "transfers": [edge.to_dict() for edge in self.transfers],
            "share": {author: self.share.get(author, 0.0) for author in self.authors},
        }


def _sorted_bucket(bucket: Mapping[str, int]) -> Dict[str, int]:
    """把一个 ``标签值 -> 次数`` 的字典按键排序后转成普通 dict。"""
    return {name: bucket[name] for name in sorted(bucket)}


def _normalized_owners(skill_owner: Mapping[str, str]) -> Dict[str, str]:
    """把技能归属表规范化为"技能名、作者名都已去首尾空白"的映射。

    为什么在入口统一处理：``profile`` 是契约公开 API，调用方可能直接传
    ``{"SEL-1": " Aster "}``（CLI 会 strip，但库调用与测试夹具不一定）。
    不规范化会同时坏两件事：``author != owner`` 把 ``" Aster "`` 与
    ``"Aster"`` 当成两个人，产生"自己迁移给自己"的伪边；``authors`` 里
    也会多出一个带空格的幽灵作者，把 ``share`` 拆成两个键。
    空名字无法表示归属，直接丢弃，等价于"该技能没有配置拥有者"。
    """
    normalized: Dict[str, str] = {}
    for skill, owner in (skill_owner or {}).items():
        skill_name = str(skill).strip()
        owner_name = "" if owner is None else str(owner).strip()
        if skill_name and owner_name:
            normalized[skill_name] = owner_name
    return normalized


def profile(items: Sequence[MergedItem], skill_owner: Mapping[str, str]) -> Profile:
    """根据合并结果与技能归属表，生成协作画像。

    ``skill_owner`` 形如 ``{"SEL-1": "Aster", "SEL-2": "Bramble"}``。
    每一条原始条目 ``v`` 只记到 ``v.author`` 名下（契约 v1.2）：标签计数
    看 ``v.tags``，迁移边在 ``v.author != owner`` 且 ``v.has_tag("技能:"+S)``
    时记 ``src=owner, dst=v.author``，证据是 ``v.eid``。只认本人亲手写下
    的标签，就不会把"共同确认"或"别人补打"的标签算成自己的证据。

    ``skill_owner`` 的技能名与作者名会先做 ``strip()``（空名视为未配置），
    否则 ``" Aster "`` 会被当成另一个人，产生自迁移伪边与幽灵作者。

    ``share`` 的分母是原始条目总数（所有 ``item.versions`` 之和），不是
    合并条目数；``authors`` 是原始条目作者与 ``skill_owner`` 非空作者名的
    并集、按名字排序，因此零条目的技能拥有者也会以 ``0.0`` 出现而不是
    消失。空输入时分母为 0，全部取 ``0.0``，不抛异常。
    """
    item_list = list(items)
    owners = _normalized_owners(skill_owner)

    authors_seen: set = set()
    skill_counts: Dict[str, Dict[str, int]] = {}
    type_counts: Dict[str, Dict[str, int]] = {}
    evidence: Dict[Tuple[str, str, str], List[str]] = {}
    participation: Dict[str, int] = {}
    total_entries = 0

    for item in item_list:
        for version in item.versions:
            author = version.author
            authors_seen.add(author)
            participation[author] = participation.get(author, 0) + 1
            total_entries += 1

            for tag in version.tags:
                if tag.startswith(_SKILL_PREFIX):
                    skill = tag[len(_SKILL_PREFIX):]
                    if not skill:
                        continue
                    _increment(skill_counts, author, skill)
                    owner = owners.get(skill)
                    if owner is not None and author != owner:
                        evidence.setdefault((owner, author, skill), []).append(version.eid)
                elif tag.startswith(_TYPE_PREFIX):
                    kind = tag[len(_TYPE_PREFIX):]
                    if kind:
                        _increment(type_counts, author, kind)

    # 技能拥有者即使零条目也要出现在画像里，让"队里有人没写日志"可见。
    for owner in owners.values():
        authors_seen.add(owner)

    authors = tuple(sorted(authors_seen))

    transfers: List[TransferEdge] = []
    for (src, dst, skill), eids in evidence.items():
        transfers.append(
            TransferEdge(
                src=src,
                dst=dst,
                skill=skill,
                evidence=tuple(sorted(set(eids), key=eid_key)),
            )
        )
    transfers.sort(key=lambda edge: (edge.skill, edge.src, edge.dst))

    share = {
        author: (
            round(participation.get(author, 0) / total_entries, 4)
            if total_entries
            else 0.0
        )
        for author in authors
    }

    skill_tags = {
        author: _sorted_bucket(skill_counts.get(author, {})) for author in authors
    }
    type_tags = {
        author: _sorted_bucket(type_counts.get(author, {})) for author in authors
    }

    return Profile(
        authors=authors,
        skill_tags=skill_tags,
        type_tags=type_tags,
        transfers=tuple(transfers),
        share=share,
    )


def _increment(counter: Dict[str, Dict[str, int]], author: str, name: str) -> None:
    """给 ``author -> name`` 的计数加一（analyze 内部私有工具）。"""
    bucket = counter.setdefault(author, {})
    bucket[name] = bucket.get(name, 0) + 1
