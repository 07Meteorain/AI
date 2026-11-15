"""通用工具：时间、ID、原子写、JSONL、中英混排分词。

这里没有一行"花活"——只有四件被反复用到、必须一次写对的小事：

1. **时区固定 UTC+8**。trace 里如果混着 UTC 与本地时间，事后按小时聚合会错。
2. **原子写**。记忆库是长期资产，写一半被 Ctrl+C 打断会毁掉整个人格。
3. **JSONL 追加**。一次运行一条，坏一行不影响其它行（可恢复性优先于紧凑）。
4. **分词**。中文没有空格，不引入 jieba 就得自己定义切法——见 ``tokenize``。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_WORD = re.compile(r"[a-z0-9_]+")
_SLUG_STRIP = re.compile(r"[^\w\u4e00-\u9fff-]+", re.UNICODE)


def now() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime | None = None) -> str:
    dt = dt or now()
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def parse_iso(text: str) -> datetime:
    try:
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


def days_between(a: str, b: str | None = None) -> float:
    return max(0.0, (parse_iso(b or iso()) - parse_iso(a)).total_seconds() / 86400.0)


def new_id(prefix: str, dt: datetime | None = None, seed: str = "") -> str:
    """``k-20261115-3f9a1c``：可读的日期 + 短的唯一尾巴。"""
    dt = dt or now()
    raw = f"{prefix}{dt.isoformat()}{seed}{os.urandom(4).hex()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
    return f"{prefix.lower()}-{dt:%Y%m%d}-{digest}"


def stable_hash(text: str, n: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def slugify(text: str, maxlen: int = 32, default: str = "note") -> str:
    text = unicodedata.normalize("NFKC", text or "").strip().lower()
    text = _SLUG_STRIP.sub("-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if not text:
        return default
    return text[:maxlen].strip("-") or default


def atomic_write_text(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: str | Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path: str | Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def read_jsonl(path: str | Path) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue  # 坏行跳过：一行损坏不该让整个记忆库打不开
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError:
        pass
    return out


def append_jsonl(path: str | Path, obj: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def tokenize(text: str) -> list[str]:
    """中英混排分词：拉丁数字按词，中文按**二元组**。

    为什么是二元组而不是单字：单字噪声太大（"的""了""是"到处都是），
    二元组能保住"记忆""技能""复盘"这类真正有区分度的词，而且不用词典。
    代价是"记忆系统"会被切成 记忆/忆系/系统，所以召回时用 OR 语义 + BM25 权重，
    不是布尔匹配——见 ``memory/index.py``。
    """

    text = unicodedata.normalize("NFKC", text or "").lower()
    tokens: list[str] = _WORD.findall(text)
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def truncate(text: str, limit: int = 120, ellipsis: str = "…") -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + ellipsis


def table(rows: Iterable[Iterable[Any]], headers: Iterable[Any] | None = None) -> str:
    """对齐的纯文本表格。中文宽度按 2 算，否则表格会歪。"""

    def width(s: Any) -> int:
        return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(s))

    def pad(s: Any, w: int) -> str:
        return str(s) + " " * max(0, w - width(s))

    data = [[str(c) for c in row] for row in rows]
    head = [str(h) for h in headers] if headers is not None else []
    cols = max([len(r) for r in data] + [len(head)] + [0])
    widths = [0] * cols
    for row in ([head] if head else []) + data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], width(cell))

    lines: list[str] = []
    if head:
        lines.append("  ".join(pad(c, widths[i]) for i, c in enumerate(head)).rstrip())
        lines.append("  ".join("-" * w for w in widths).rstrip())
    for row in data:
        lines.append("  ".join(pad(c, widths[i]) for i, c in enumerate(row)).rstrip())
    return "\n".join(lines)


def ensure_utf8_stdio() -> None:
    """Windows 控制台默认 cp936，直接 print 中文表格会炸。宁可静默失败也别崩。"""
    import sys

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
