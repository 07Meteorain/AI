"""笔记可出卡性诊断（`recall doctor`）。

这个命令来自一个真实的挫败：把 33 篇课程译文（12.9 万字）丢进 Recall，
只抽出 62 张卡。问题不在抽取规则，而在**输入形态**——那些文本是 PDF 转写，
没有定义列表、没有问句标题，段落也不围绕一个可提问的点组织。

与其假装「多调几个正则就能解决」，不如把「为什么出不了卡」直接告诉用户。
诊断只看结构，不评判内容好坏；它衡量的是「机器能不能从这篇笔记里提出好问题」。
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from .generate import BOLD_RE, QUESTION_HEAD_RE, Options, _iter_qa_pairs, generate_from_note, is_noise_heading
from .mdparse import count_words, iter_markdown_files, parse_note
from .model import Note


@dataclass
class Diagnosis:
    source: str
    title: str
    words: int
    sections: int
    paragraphs: int
    list_items: int
    bold_terms: int
    question_heads: int
    qa_pairs: int
    cards: int
    score: int
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _analyze(note: Note, opts: Options) -> Diagnosis:
    words = count_words("\n".join(note.paragraphs))
    sections = [s for s in note.sections if not is_noise_heading(s.title)]
    paragraphs = sum(len(s.paragraphs) for s in sections)
    list_items = sum(len(s.list_items) for s in sections)
    bold_terms = 0
    qa_pairs = 0
    for section in sections:
        for block in section.blocks:
            if block.kind in ("para", "list"):
                bold_terms += len(BOLD_RE.findall(block.text))
                qa_pairs += sum(1 for _ in _iter_qa_pairs(block.text))
    question_heads = sum(1 for s in sections if QUESTION_HEAD_RE.search(s.title))
    cards = len(generate_from_note(note, opts))

    score_structure = 0
    if words >= 300:
        score_structure += 15
    if len(sections) >= 3:
        score_structure += 20
    if list_items >= 3:
        score_structure += 20
    if bold_terms >= 3:
        score_structure += 15
    if question_heads >= 1:
        score_structure += 15
    if qa_pairs >= 1:
        score_structure += 15
    score_structure = min(100, score_structure)
    # 结构分只占 70%，剩下 30% 看「实际能出多少卡」——
    # 否则一篇结构齐全但卡片为 0 的笔记会拿到虚高的分数。
    yield_ratio = min(1.0, cards / 10.0)
    score = int(round(score_structure * 0.7 + yield_ratio * 30))

    issues: List[str] = []
    if cards < 5:
        issues.append("按当前规则只能出 {} 张卡；先补定义列表或问句标题".format(cards))
    if words < 300:
        issues.append("正文不足 300 字，样本太小")
    if len(sections) < 3:
        issues.append("只有 {} 个有效标题；用 `##` 把内容切成可提问的小节".format(len(sections)))
    if list_items == 0:
        issues.append("没有定义列表；`- **术语**：解释` 是最稳定的出卡结构")
    if bold_terms == 0:
        issues.append("没有加粗术语；`**术语**` 可以被抽成定义卡或填空卡")
    if question_heads == 0:
        issues.append("没有问句标题；把「X 的定义」改成「X 是什么？」能多出一批卡")
    if qa_pairs == 0:
        issues.append("没有显式问答；`问：… 答：…` 的抽取置信度最高")

    return Diagnosis(
        source=note.source,
        title=note.title,
        words=words,
        sections=len(sections),
        paragraphs=paragraphs,
        list_items=list_items,
        bold_terms=bold_terms,
        question_heads=question_heads,
        qa_pairs=qa_pairs,
        cards=cards,
        score=score,
        issues=issues,
    )


def diagnose_path(root: str, opts: Optional[Options] = None) -> List[Diagnosis]:
    opts = opts or Options()
    if not os.path.exists(root):
        raise FileNotFoundError(root)
    base = root if os.path.isdir(root) else os.path.dirname(os.path.abspath(root))
    out: List[Diagnosis] = []
    for path in iter_markdown_files(root):
        note = parse_note(str(path), root=base)
        out.append(_analyze(note, opts))
    out.sort(key=lambda d: (d.score, d.source))
    return out


def _bar(score: int) -> str:
    filled = int(round(score / 10))
    return "█" * filled + "░" * (10 - filled)


def render_report(diagnoses: Sequence[Diagnosis]) -> str:
    if not diagnoses:
        return "没有找到 Markdown 笔记。\n"
    lines = [
        "# 笔记可出卡性诊断",
        "",
        "> 分数衡量的是「结构是否适合自动出卡」，不评价内容质量。",
        "> 60 分以下：自动出卡会明显偏少，建议按右侧问题改结构。",
        "",
        "| 笔记 | 字数 | 标题 | 列表项 | 加粗术语 | 问句标题 | 问答 | 卡片 | 可出卡性 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in diagnoses:
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} | {} | {} | {} {} |".format(
                item.source,
                item.words,
                item.sections,
                item.list_items,
                item.bold_terms,
                item.question_heads,
                item.qa_pairs,
                item.cards,
                _bar(item.score),
                item.score,
            )
        )
    low = [item for item in diagnoses if item.issues]
    if low:
        lines.append("")
        lines.append("## 低分笔记的具体问题")
        lines.append("")
        for item in low:
            lines.append("### `{}`".format(item.source))
            for issue in item.issues:
                lines.append("- {}".format(issue))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
