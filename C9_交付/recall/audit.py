"""抽样审核：把「自动出卡」变成一份可以逐条打勾的清单。

为什么需要它：抽取规则的上限是候选，不是成品。与其假装精确率 100%，
不如让用户抽 30 张、自己判一遍，把「可用率」变成一个能被复核的数字。
"""
from __future__ import annotations

import random
import re
from typing import Iterable, List, Optional, Sequence

from .model import Card

KIND_LABELS = {
    "heading-question": "标题提问",
    "term-list": "术语列表",
    "definition": "行内定义",
    "explicit-qa": "显式问答",
    "cloze": "填空",
    "gist": "章节概述",
}


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip().replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def sample_cards(
    cards: Sequence[Card],
    n: int = 30,
    seed: int = 7,
    kinds: Optional[Iterable[str]] = None,
) -> List[Card]:
    pool = [c for c in cards if not kinds or c.kind in set(kinds)]
    if n >= len(pool):
        return list(pool)
    rng = random.Random(seed)
    return rng.sample(pool, n)


def render_audit_markdown(
    cards: Sequence[Card],
    title: str = "Recall 抽样审核",
    seed: int = 7,
    generated: str = "",
) -> str:
    lines = [
        "# {}".format(title),
        "",
        "> 抽样 {} 张，随机种子 `{}`{}。".format(
            len(cards), seed, "，生成于 " + generated if generated else ""
        ),
        "> 判定口径：**这张卡能不能在 5 秒内看懂、并凭记忆回答**。",
        "> 在「判定」列填 `可用` / `不可用` / `改写`；`不可用` 请顺手写一句原因。",
        "> 这张表本身就是验收证据：可用率 = 可用 / 总数，分母不剔除任何卡。",
        "",
        "| # | 类型 | 问题 | 答案（截断） | 来源 | 判定 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, card in enumerate(cards, 1):
        lines.append(
            "| {} | {} | {} | {} | `{}:{}` |  |  |".format(
                index,
                KIND_LABELS.get(card.kind, card.kind),
                _clip(card.prompt, 60),
                _clip(card.answer, 70),
                card.source,
                card.line,
            )
        )
    lines.append("")
    lines.append("总计：{} 张。".format(len(cards)))
    return "\n".join(lines) + "\n"
