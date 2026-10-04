"""
C1 课程资料翻译管线 · 公共库
零第三方依赖（PDF 抽取可选依赖 pypdf）。

设计目标：换一门课的资料时，本文件与所有脚本无需修改，
只需改config.jsonc 的 sources / glossary 即可复用。
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Iterator

# ----------------------------------------------------------------- 路径与配置

PIPELINE_DIR = Path(__file__).resolve().parent
ROOT = PIPELINE_DIR.parent


def strip_jsonc(text: str) -> str:
    """把config.jsonc（允许 // 与 /* */ 注释）转成合法 JSON。

    自己实现而不是用 json5，避免引入依赖。
    """
    out = []
    i, n = 0, len(text)
    in_str = False
    quote = ""
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                in_str = False
            i += 1
            continue
        if ch in "\"'":
            in_str = True
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else PIPELINE_DIR / "config.json"
    raw = p.read_text(encoding="utf-8")
    cfg = json.loads(strip_jsonc(raw))
    proj = cfg["project"]
    base = p.parent
    for k in ("source_root", "work_dir", "cache_dir", "out_dir", "reports_dir", "site_dir", "glossary"):
        proj[k] = (base / proj[k]).resolve()
    return cfg


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_jsonl(path: Path) -> list[dict]:
    """逐行读 JSONL。

    注意：必须用 split("\\n") 而非 splitlines()。
    PDF 抽取出的文本里常含 \\x0c（换页符）、\\x0b、\\u2028 等控制字符，
    str.splitlines() 会在这些字符处断行，而 json.dumps 不会转义它们，
    于是这些行会被读成两条损坏的记录。踩过这个坑，别改回splitlines()。
    """
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    ensure_dir(path.parent)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


# ----------------------------------------------------------------- 数据结构

@dataclass
class Block:
    """一个语义块：标题 + 段落列表。抽取阶段的最小单位。"""
    kind: str                 # heading | paragraph | list_item | code | quote | table_row
    text: str
    level: int = 0            # heading 层级
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Segment:
    """一个可翻译单元。由若干 Block 组成，带稳定 ID 与指纹。"""
    seg_id: str
    doc_id: str
    order: int
    kind: str# paragraph | heading_group | code | table
    text: str                 # 送翻译的原文
    blocks: list[dict] = field(default_factory=list)  # 结构信息，翻译后按此重建 Markdown
    fingerprint: str = ""     # 原文 sha1，翻译缓存键
    word_count: int = 0
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ----------------------------------------------------------------- 文本工具

CODE_LANG_HINT = re.compile(
    r"^\s*(?:\$\s|>\s|#\s|//\s|/\*|\*\s|def\s|class\s|import\s|from\s|const\s|let\s|var\s|function\s"
    r"|SELECT\b|INSERT\b|UPDATE\b|DELETE\b|GitHub\b|npm\b|pip\b|curl\b|docker\b|git\s)"
)


def is_probably_code(text: str) -> bool:
    """启发式判断是否代码/日志/命令行——这类内容不翻译，原样保留。"""
    t = text.strip()
    if not t:
        return False
    if t.startswith("```"):
        return True
    if CODE_LANG_HINT.match(t):
        return True
    # 代码符号密度
    symbols = sum(t.count(c) for c in "{}[]()<>=;|&$#")
    if len(t) > 20 and symbols / len(t) > 0.12:
        return True
    # 驼峰/蛇形标识符密集
    if len(re.findall(r"\b[a-z]+_[a-z_]+\b", t)) >= 3:
        return True
    return False


# PDF 抽取常见的控制字符：\x0c 换页、\x0b 竖向制表、软连字符 \xad、零宽字符等。
# 不清理的话：1) JSONL 行会被 splitlines 截断；2) 译文里混入不可见字符，读者根本看不出来。
CONTROL_CHARS = dict.fromkeys(
    [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0b, 0x0c, 0x0e, 0x0f,
     0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c,
     0x1d, 0x1e, 0x1f, 0xad, 0x7f, 0x200b, 0x200c, 0x200d, 0xfeff]
    + list(range(0x2028, 0x202f))
    + [0x2060, 0x2061, 0x2062, 0x2063, 0x2064],
    " ",
)


def normalize_ws(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(CONTROL_CHARS)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def count_words(text: str) -> int:
    """英文词数 + 中文字数，作为覆盖率与长度比的统一度量。"""
    en = len(re.findall(r"[A-Za-z][A-Za-z'-]*", text))
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    return en + zh


def cjk_ratio(text: str) -> float:
    letters = re.findall(r"[A-Za-z\u4e00-\u9fff]", text)
    if not letters:
        return 0.0
    zh = sum(1 for c in letters if "\u4e00" <= c <= "\u9fff")
    return zh / len(letters)


# ----------------------------------------------------------------- 术语表

@dataclass
class Term:
    en: str
    zh: str
    aliases: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)   # 错误/不一致译法，QC 会报警
    note: str = ""
    category: str = "通用"
    # forbidden 里这些词本身就是常用中文（如「背景」=background、「光标」=cursor），
    # 脚本无法区分「术语误译」和「普通词义」，因此降级为提示而非错误。
    ambiguous: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class Glossary:
    def __init__(self, terms: list[Term]):
        self.terms = terms
        # 英文 → 中文（含别名），长词优先匹配
        self.en2zh: dict[str, str] = {}
        for t in terms:
            self.en2zh[t.en.lower()] = t.zh
            for a in t.aliases:
                self.en2zh.setdefault(a.lower(), t.zh)
        self._en_sorted = sorted(self.en2zh.keys(), key=len, reverse=True)
        # 中文译法 → 规范中文（用于反向查术语一致性）
        self.zh2en: dict[str, str] = {}
        for t in terms:
            self.zh2en.setdefault(t.zh, t.en)
            for a in t.aliases:
                pass
        self.forbidden_pairs: list[tuple[str, str, str, str]] = []
        for t in terms:
            for f in t.forbidden:
                self.forbidden_pairs.append((f, t.en, t.zh, "error"))
            for f in t.ambiguous:
                self.forbidden_pairs.append((f, t.en, t.zh, "info"))

    @classmethod
    def load(cls, path: Path) -> "Glossary":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Term(**t) for t in data["terms"]])

    def __len__(self) -> int:
        return len(self.terms)

    def glossary_prompt_block(self, only: list[str] | None = None) -> str:
        """生成注入 prompt 的术语约束块。"""
        if only:
            picked = [t for t in self.terms if t.en in only or t.en.lower() in {e.lower() for e in only}]
        else:
            picked = self.terms
        lines = []
        for t in picked:
            extra = ""
            if t.forbidden:
                extra += f"（勿用：{'、'.join(t.forbidden)}）"
            if t.note:
                extra += f"｜{t.note}"
            lines.append(f"- {t.en} → {t.zh}{extra}")
        return "\n".join(lines)

    def check_consistency(self, zh_text: str, source_text: str | None = None) -> list[dict]:
        """检查中文译文中是否出现被禁用的译法。

        这里踩过一个很典型的坑，值得写下来：

        最初的实现是「禁用译法只要在译文里出现就报错」。结果 267 条告警里
        绝大多数是误报——因为中文里「不同」「模式」「背景」「期间」「标记」
        这些本身就是常用词，正常句子都会用。例如：
            「不同模型对特定格式的响应可能更好」← 这里的「不同」是形容词，
            并不是把 diff 译错了。
        还有「码库」是「代码库」的子串，纯字符串匹配必然误报。

        修正后的判定规则（两级置信度）：
        1. 若原文里根本没出现该英文术语 → 译文里的中文词不可能是它的误译，直接跳过；
        2. 若译文中同时出现了规范译法 → 译者是一致的，降级为提示（info）；
        3. 若规范译法没出现、只有禁用译法 → 真的有 inconsististency，判为错误（error）。
        """
        issues: list[dict] = []
        for bad, en, good, base_level in self.forbidden_pairs:
            if bad not in zh_text:
                continue
            # 规则 1：原文没提这个术语 → 不可能是误译
            if source_text is not None:
                low = source_text.lower()
                keys = [en.lower()] + [a.lower() for a in self._aliases_of(en)]
                # 必须按词边界匹配。这里踩过坑：纯 substring 匹配会让
                # "diff" 命中 "different"、"span" 命中 "spanish"，
                # 于是「不同模型」被当成了「diff 译错」，误报一片。
                if not any(self._has_term(low, k) for k in keys):
                    continue
            # 规则 2：规范译法也在译文里 → 说明译者是一致的
            core = good.split("（")[0]
            if core and core in zh_text:
                level = "info"
                detail = (f"「{bad}」与规范译法「{core}」并存，疑为普通词义而非术语误译，"
                          f"建议人工确认")
            else:
                level = base_level
                detail = (f"术语「{en}」译成了「{bad}」，全文未出现规范译法「{core}」")
            issues.append({"type": "forbidden_term" if level == "error" else "forbidden_term_soft",
                           "level": level, "found": bad, "should_be": good,
                           "term": en, "detail": detail})
        return issues

    def _aliases_of(self, en: str) -> list[str]:
        for t in self.terms:
            if t.en == en:
                return list(t.aliases)
        return []

    @staticmethod
    def _has_term(haystack_lower: str, term_lower: str) -> bool:
        """按词边界判断英文术语是否出现。

        短语（含空格/连字符）也要整体按边界匹配，
        否则 "code review" 里的 "review" 会让 context 之类的规则误触发。
        """
        if not term_lower:
            return False
        idx = haystack_lower.find(term_lower)
        while idx != -1:
            before = haystack_lower[idx - 1] if idx > 0 else " "
            after_i = idx + len(term_lower)
            after = haystack_lower[after_i] if after_i < len(haystack_lower) else " "
            before_ok = not (before.isalnum())
            after_ok = not (after.isalnum())
            if before_ok and after_ok:
                return True
            idx = haystack_lower.find(term_lower, idx + 1)
        return False


# ----------------------------------------------------------------- 终端输出

_COLOR = {
    "reset": "\033[0m", "dim": "\033[2m", "red": "\033[31m", "green": "\033[32m",
    "yellow": "\033[33m", "blue": "\033[34m", "cyan": "\033[36m", "bold": "\033[1m",
}


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.name != "nt" or os.environ.get("FORCE_COLOR") == "1"


def c(text: str, color: str) -> str:
    if not _supports_color():
        return text
    return f"{_COLOR.get(color,'')}{text}{_COLOR['reset']}"


def log(stage: str, msg: str) -> None:
    print(f"{c('['+stage+']', 'cyan')} {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"{c('  OK', 'green')} {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{c('  !!', 'yellow')} {msg}", flush=True)


def err(msg: str) -> None:
    print(f"{c('  XX', 'red')} {msg}", flush=True)
