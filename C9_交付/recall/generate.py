"""候选卡抽取 + 质量门。

Recall 的产品判断：**自动出卡的上限是「候选」，不是「成品」**。
所以这里做的不是「尽量多出」，而是「每条都能被追溯到某一句话」，
并且用一组可解释的硬门把明显不能学的卡挡掉：

- 来源必须是正文段落 / 定义列表 / 显式问答，代码块与表格不出题；
- 答案 8–320 字，问题 6–160 字；
- 不含 URL、图片、表格、HTML；
- 去重（问题归一化 / 长答案归一化）；
- 每节、每篇都有配额，避免一篇长文刷屏。

被挡掉的原因会进入 BuildStats，供 `build` 打印——**拒绝也是数据**。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .mdparse import clean_inline, count_words, is_cjk, parse_note
from .model import BuildResult, BuildStats, Card, Note, Section, make_id, normalize

# ---------------------------------------------------------------- 规则表

QUESTION_HEAD_RE = re.compile(
    r"(？|\?|是什么|为什么|如何|怎么|哪些|是否|能否|多少|有何)"
)
LIST_DEF_RE = re.compile(
    r"^\s*\*\*(?P<term>[^*\n]{2,40})\*\*\s*(?:[：:]\s*|[—–-]{1,2}\s*)(?P<def>.+)$"
)
BOLD_RE = re.compile(r"\*\*(?P<term>[^*\n]{1,40})\*\*")
INLINE_DEF_TAIL_RE = re.compile(
    r"^\s*(?:本质上是|本质上|指的是|是指|是|指|表示|即|称为|是一种|是一个|是一套|是一项|用于|用来)"
)
NUMBER_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|倍|个|篇|条|项|小时|分钟|秒|天|年|美元|token|tokens|字符|字|次|张|页|人|行)"
)
QA_LEAD_RE = re.compile(r"(?:Q|问|问题)\s*[：:]\s*")
QA_SPLIT_RE = re.compile(r"(?:A|答|答案)\s*[：:]")

BOILER_HEADINGS = {
    "目录",
    "参考文献",
    "参考资料",
    "来源",
    "相关阅读",
    "关于作者",
    "版权",
    "声明",
    "附录",
    "索引",
    "致谢",
    "更新日志",
    "作者简介",
    "contents",
    "references",
}
NAV_PREFIX_RE = re.compile(
    r"^(?:原文|来源|作者|译者|日期|目录|Last9|Cookie|预约演示|产品|资源|更多|客户|文档|定价|"
    r"打开菜单|关闭菜单|首页|博客|指南|活动|更新日志|登录|注册|分享|标签|广告|赞助)"
)
BOILER_SUBSTR = (
    "Cookie",
    "版权所有",
    "扫码",
    "点击关注",
    "订阅",
    "本文档由",
    "机器翻译",
    "译者注",
    "未经授权",
)
URL_RE = re.compile(r"(?:https?://|www\.)", re.I)
SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?])")
CJK_OR_WORD_RE = re.compile(r"[\u4e00-\u9fff]")
FORMAT_BAD_RE = re.compile(r"(?:\]\s*\(|!\[|\||<[a-zA-Z/])")


@dataclass
class Options:
    min_confidence: float = 0.55
    max_per_section: int = 6
    max_per_file: int = 40
    max_total: int = 4000
    kinds: Tuple[str, ...] = ()
    include_gist: bool = False

    def allows(self, kind: str) -> bool:
        return not self.kinds or kind in self.kinds


@dataclass
class Gate:
    """质量门：维护去重集合与拒绝原因计数。"""

    min_confidence: float
    seen_prompts: Set[str] = field(default_factory=set)
    seen_long_answers: Set[str] = field(default_factory=set)
    rejected: Dict[str, int] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def check(self, card: Card) -> Optional[str]:
        prompt = card.prompt.strip()
        answer = card.answer.strip()
        if card.confidence < self.min_confidence:
            return "low-confidence"
        if not (6 <= len(prompt) <= 160):
            return "prompt-length"
        min_answer = 2 if card.kind == "cloze" else 8
        if not (min_answer <= len(answer) <= 320):
            return "answer-length"
        if URL_RE.search(answer) or FORMAT_BAD_RE.search(answer):
            return "format"
        if any(token in answer for token in BOILER_SUBSTR):
            return "boilerplate"
        if card.kind != "cloze":
            cjk = len(CJK_OR_WORD_RE.findall(answer))
            if cjk < 6 and len(answer.split()) < 5:
                return "too-thin"
        pkey = normalize(prompt)
        if pkey in self.seen_prompts:
            return "duplicate-prompt"
        self.seen_prompts.add(pkey)
        if len(answer) > 40:
            akey = normalize(answer)
            if akey in self.seen_long_answers:
                return "duplicate-answer"
            self.seen_long_answers.add(akey)
        return None


# ---------------------------------------------------------------- 文本工具


def split_sentences(text: str) -> List[str]:
    parts = [part.strip() for part in SENT_SPLIT_RE.split(text) if part.strip()]
    return parts


def truncate(text: str, limit: int = 300) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    best = -1
    for mark in ("。", "！", "？", ". "):
        idx = cut.rfind(mark)
        if idx > best:
            best = idx + (1 if mark != ". " else 1)
    if best >= int(limit * 0.45):
        return cut[:best].strip()
    return cut.rstrip("，、；：,;: ") + "…"


def ensure_question(title: str) -> str:
    title = title.strip()
    if title.endswith(("？", "?")):
        return title
    return title + "？"


def is_noise_paragraph(text: str) -> bool:
    plain = clean_inline(text)
    if not plain:
        return True
    if len(plain) < 30 and "。" not in plain and "？" not in plain:
        return True
    if NAV_PREFIX_RE.match(plain) and len(plain) < 160:
        return True
    if any(token in text for token in BOILER_SUBSTR):
        return True
    if plain.count("　") >= 3:  # 全角空格拼出的导航条
        return True
    return False


def is_noise_heading(title: str) -> bool:
    key = title.strip().lower()
    if not key or key in BOILER_HEADINGS:
        return True
    if re.fullmatch(r"[\d\s.、()（）-]{1,12}", key):
        return True
    return False


def _substantive_paragraphs(section: Section, seen: Set[str]) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for block in section.blocks:
        if block.kind != "para":
            continue
        raw = block.text
        if is_noise_paragraph(raw):
            continue
        plain = clean_inline(raw)
        key = normalize(plain)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((raw, block.line))
    return out


def _emit(
    cards: List[Card],
    *,
    note: Note,
    section: Section,
    kind: str,
    prompt: str,
    answer: str,
    confidence: float,
    line: int,
    opts: Options,
) -> None:
    if not opts.allows(kind):
        return
    prompt = prompt.strip()
    answer = truncate(answer.strip(), 320)
    min_answer = 2 if kind == "cloze" else 8
    if len(prompt) < 6 or len(answer) < min_answer:
        return
    cards.append(
        Card(
            id=make_id(note.source, kind, prompt),
            kind=kind,
            prompt=prompt,
            answer=answer,
            source=note.source,
            heading=section.title,
            line=line,
            confidence=confidence,
            tags=((note.meta.get("category", "").strip(),) if note.meta.get("category") else ()),
        )
    )


# ---------------------------------------------------------------- 五条规则


def _iter_qa_pairs(text: str) -> Iterable[Tuple[str, str]]:
    """从一段文本里提取「问：… 答：…」对；兼容换行与中文直接相连两种排版。"""
    leads = list(QA_LEAD_RE.finditer(text))
    for index, match in enumerate(leads):
        start = match.end()
        end = leads[index + 1].start() if index + 1 < len(leads) else len(text)
        chunk = text[start:end]
        parts = QA_SPLIT_RE.split(chunk, maxsplit=1)
        if len(parts) != 2:
            continue
        question = parts[0].strip().strip("？?：: \n")
        answer = parts[1].strip()
        if question and answer:
            yield question, answer


def rule_explicit_qa(note: Note, section: Section, opts: Options, seen: Set[str]) -> List[Card]:
    cards: List[Card] = []
    for block in section.blocks:
        if block.kind not in ("para", "list"):
            continue
        text = block.text if block.kind == "para" else "\n".join(block.items)
        for question, answer in _iter_qa_pairs(text):
            clean_answer = clean_inline(answer)
            if not clean_answer:
                continue
            _emit(
                cards,
                note=note,
                section=section,
                kind="explicit-qa",
                prompt=ensure_question(question),
                answer=clean_answer,
                confidence=0.95,
                line=block.line,
                opts=opts,
            )
            seen.add(normalize(clean_answer))
    return cards


def rule_term_list(note: Note, section: Section, opts: Options, seen: Set[str]) -> List[Card]:
    cards: List[Card] = []
    for block in section.blocks:
        if block.kind != "list":
            continue
        for index, item in enumerate(block.items):
            match = LIST_DEF_RE.match(item)
            if not match:
                continue
            term = clean_inline(match.group("term"))
            definition = clean_inline(match.group("def"))
            if len(term) < 2 or len(definition) < 8:
                continue
            if definition.startswith(("例如", "比如", "见", "参考")):
                continue
            item_line = block.item_lines[index] if index < len(block.item_lines) else block.line
            _emit(
                cards,
                note=note,
                section=section,
                kind="term-list",
                prompt="「{}」是什么？".format(term),
                answer=definition,
                confidence=0.84,
                line=item_line,
                opts=opts,
            )
    return cards


def rule_inline_definition(note: Note, section: Section, opts: Options, seen: Set[str]) -> List[Card]:
    cards: List[Card] = []
    for raw, para_line in _substantive_paragraphs(section, set()):
        for sentence in split_sentences(raw):
            if normalize(sentence) in seen:
                continue
            for match in BOLD_RE.finditer(sentence):
                term = clean_inline(match.group("term"))
                if not (2 <= len(term) <= 30):
                    continue
                tail = sentence[match.end():]
                if not INLINE_DEF_TAIL_RE.match(tail):
                    continue
                answer = clean_inline(tail)
                answer = re.sub(
                    r"^(?:本质上是|本质上|指的是|是指|是|指|表示|即|称为|是一种|是一个|是一套|是一项|用于|用来)\s*",
                    "",
                    answer,
                )
                if len(answer) < 10:
                    continue
                key = normalize(answer)
                if key in seen:
                    continue
                seen.add(key)
                _emit(
                    cards,
                    note=note,
                    section=section,
                    kind="definition",
                    prompt="「{}」是什么？".format(term),
                    answer=answer,
                    confidence=0.80,
                    line=para_line,
                    opts=opts,
                )
    return cards


def rule_heading_question(note: Note, section: Section, opts: Options, seen: Set[str]) -> List[Card]:
    if not QUESTION_HEAD_RE.search(section.title):
        return []
    paragraphs = _substantive_paragraphs(section, set())
    if not paragraphs:
        return []
    first_raw, first_line = paragraphs[0]
    answer = truncate(clean_inline(first_raw), 300)
    if len(answer) < 20:
        return []
    cards: List[Card] = []
    _emit(
        cards,
        note=note,
        section=section,
        kind="heading-question",
        prompt=ensure_question(section.title),
        answer=answer,
        confidence=0.88,
        line=first_line,
        opts=opts,
    )
    return cards


def rule_cloze(note: Note, section: Section, opts: Options, seen: Set[str], limit: int = 2) -> List[Card]:
    cards: List[Card] = []
    used = 0
    paragraphs = _substantive_paragraphs(section, set())
    for raw, para_line in paragraphs:
        if used >= limit:
            break
        for sentence in split_sentences(raw):
            if used >= limit:
                break
            plain = clean_inline(sentence)
            if not (30 <= len(plain) <= 180):
                continue
            if "例如" in plain or "如下" in plain or "http" in plain:
                continue
            target = ""
            for match in BOLD_RE.finditer(sentence):
                term = clean_inline(match.group("term"))
                if 2 <= len(term) <= 24 and term not in target:
                    target = term
                    break
            if not target:
                match = NUMBER_UNIT_RE.search(plain)
                if match:
                    target = match.group(0).strip()
            if not target:
                continue
            answer_key = normalize(target)
            if not answer_key or answer_key in seen:
                continue
            blanked = plain.replace(target, "____", 1)
            if blanked == plain or len(blanked) < 25:
                continue
            if len(re.findall(r"[\u4e00-\u9fff]", blanked)) < 12:
                continue
            seen.add(answer_key)
            used += 1
            _emit(
                cards,
                note=note,
                section=section,
                kind="cloze",
                prompt="填空：{}".format(blanked),
                answer=target,
                confidence=0.62,
                line=para_line,
                opts=opts,
            )
    return cards


def rule_gist(note: Note, section: Section, opts: Options, seen: Set[str]) -> List[Card]:
    if not opts.include_gist:
        return []
    if QUESTION_HEAD_RE.search(section.title) or is_noise_heading(section.title):
        return []
    paragraphs = _substantive_paragraphs(section, set())
    if not paragraphs:
        return []
    first_raw, first_line = paragraphs[0]
    answer = truncate(clean_inline(first_raw), 280)
    if len(answer) < 60:
        return []
    cards: List[Card] = []
    _emit(
        cards,
        note=note,
        section=section,
        kind="gist",
        prompt="《{}》这一节讲了什么？".format(section.title),
        answer=answer,
        confidence=0.50,
        line=first_line,
        opts=opts,
    )
    return cards


# ---------------------------------------------------------------- 组装


def generate_from_note(note: Note, opts: Options) -> List[Card]:
    """对一篇笔记跑全部规则。配额按节生效，避免长文刷屏。"""
    seen: Set[str] = set()
    out: List[Card] = []
    for section in note.sections:
        if is_noise_heading(section.title):
            continue
        per_section: List[Card] = []
        for rule in (rule_explicit_qa, rule_heading_question, rule_term_list, rule_inline_definition, rule_cloze, rule_gist):
            try:
                produced = rule(note, section, opts, seen)
            except Exception:  # 单条规则失败不应让整篇笔记失败
                produced = []
            per_section.extend(produced)
        # 配额：高分优先，同分保留出现顺序
        per_section.sort(key=lambda c: -c.confidence)
        out.extend(per_section[: opts.max_per_section])
    return out


def build_deck(root: str, opts: Optional[Options] = None, generated: str = "") -> BuildResult:
    """扫描目录并构建卡组；所有卡默认 approved，可后续审核剔除。"""
    from .mdparse import iter_markdown_files

    opts = opts or Options()
    stats = BuildStats()
    gate = Gate(min_confidence=opts.min_confidence)
    notes: List[Note] = []
    accepted: List[Card] = []
    base = root if os.path.isdir(root) else os.path.dirname(os.path.abspath(root))

    for path in iter_markdown_files(root):
        note = parse_note(str(path), root=base)
        notes.append(note)
        stats.files += 1
        stats.sections += len(note.sections)
        stats.paragraphs += len(note.paragraphs)
        stats.words += count_words("\n".join(note.paragraphs))

        candidates = generate_from_note(note, opts)
        stats.candidates += len(candidates)
        # 每篇配额：高分优先
        candidates.sort(key=lambda c: -c.confidence)
        candidates = candidates[: opts.max_per_file]
        for card in candidates:
            reason = gate.check(card)
            if reason:
                gate.reject(reason)
                continue
            card.status = "approved"
            card.created = generated
            accepted.append(card)
            stats.by_kind[card.kind] = stats.by_kind.get(card.kind, 0) + 1
            stats.by_source[card.source] = stats.by_source.get(card.source, 0) + 1

    accepted.sort(key=lambda c: (c.source, c.line, c.prompt))
    if len(accepted) > opts.max_total:
        accepted = accepted[: opts.max_total]
    stats.accepted = len(accepted)
    stats.rejected = dict(gate.rejected)
    return BuildResult(cards=accepted, stats=stats, notes=notes, generated=generated)
