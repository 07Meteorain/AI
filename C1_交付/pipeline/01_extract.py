"""
01_extract.py — 抽取阶段：把 HTML / PDF 变成结构化 Block + Segment。

用法：
    python 01_extract.py [--config config.jsonc]

产物：
    work/segments.jsonl        每行一个Segment（翻译单元）
    work/blocks/<doc_id>.json  每篇的Block 明细（便于人工校对时定位）
    reports/00_extraction.json 抽取统计（字符数、块数、跳过原因）
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from common import (
    Block, Segment, count_words, ensure_dir, is_probably_code, load_config,
    log, normalize_ws, ok, sha1, warn, write_jsonl, PIPELINE_DIR,
)

# --------------------------------------------------------------------- HTML

# 需要丢弃的标签及其内容
DROP_TAGS = {"script", "style", "noscript", "svg", "iframe", "nav", "footer", "form", "button"}
# 结构性标签 → Block 类型
BLOCK_TAGS = {"p", "li", "blockquote", "pre", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}
HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class ArticleParser(HTMLParser):
    """把 HTML 正文抽成 Block 列表。

    之所以自己写而不是用 BeautifulSoup：
    1) 零依赖，`git clone` + `python 01_extract.py` 就能跑，陌生人零成本复用；
    2) 我们需要保留 <pre> 代码块原样，而这正是通用清洗库最容易破坏的地方。
    """

    def __init__(self, prefer_selector: str | None = None):
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._stack: list[str] = []
        self._drop_depth = 0
        self._buf: list[str] = []
        self._buf_kind: str | None = None
        self._buf_level = 0
        self._in_pre = False
        self._pre_buf: list[str] = []
        self._in_title = False
        self.title = ""
        # 简单的内容区偏好：<article> / <main> 优先
        self._depth_main = 0
        self._main_blocks_start = 0

    # -- helpers
    def _flush(self) -> None:
        if self._buf_kind is None:
            return
        text = normalize_ws("".join(self._buf))
        self._buf.clear()
        kind, level = self._buf_kind, self._buf_level
        self._buf_kind = None
        self._buf_level = 0
        if not text:
            return
        if kind == "code":
            self.blocks.append(Block("code", text, meta={"lang": self._pre_lang}))
            return
        if kind == "heading":
            self.blocks.append(Block("heading", text, level=level))
            return
        if kind == "list_item":
            self.blocks.append(Block("list_item", text))
            return
        if kind == "quote":
            self.blocks.append(Block("quote", text))
            return
        if kind == "table_row":
            self.blocks.append(Block("table_row", text, meta={"cells": self._pre_cells}))
            return
        self.blocks.append(Block("paragraph", text))

    _pre_lang = ""
    _pre_cells: list[str] = []

    # -- HTMLParser hooks
    def handle_starttag(self, tag: str, attrs_list) -> None:
        tag = tag.lower()
        d = dict(attrs_list)
        if tag == "pre":
            self._flush()
            self._in_pre = True
            self._pre_lang = (d.get("class") or "")
            m = re.search(r"language-([\w+-]+)", self._pre_lang)
            self._pre_lang = m.group(1) if m else ""
            self._pre_buf = []
        if tag in ("article", "main"):
            self._depth_main += 1
        if self._drop_depth or tag in DROP_TAGS:
            if tag in DROP_TAGS:
                self._drop_depth += 1
            return
        if tag in ("title",):
            self._in_title = True
            return
        if tag in HEADING_TAGS:
            self._flush()
            self._buf_kind = "heading"
            self._buf_level = HEADING_TAGS[tag]
            return
        if tag == "li":
            self._flush()
            self._buf_kind = "list_item"
            return
        if tag == "blockquote":
            self._flush()
            self._buf_kind = "quote"
            return
        if tag in ("td", "th"):
            self._flush()
            self._buf_kind = "table_row"
            self._pre_cells = []
            return
        if tag == "br":
            self._buf.append("\n")
            return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "pre":
            text = "".join(self._pre_buf).strip("\n")
            if text:
                self.blocks.append(Block("code", text, meta={"lang": self._pre_lang}))
            self._in_pre = False
            self._pre_buf = []
            return
        if tag in ("article", "main") and self._depth_main:
            self._depth_main -= 1
        if self._drop_depth:
            if tag in DROP_TAGS:
                self._drop_depth -= 1
            return
        if tag in ("title",):
            self._in_title = False
            return
        if tag in HEADING_TAGS or tag in ("li", "blockquote", "td", "th", "p", "div", "section"):
            if self._in_pre:
                return
            if tag in ("td", "th") and self._buf_kind == "table_row":
                # 收集单元格
                cell = normalize_ws("".join(self._buf))
                self._pre_cells.append(cell)
                self._buf.clear()
                return
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
            return
        if self._in_pre:
            self._pre_buf.append(data)
            return
        if self._drop_depth:
            return
        if self._buf_kind is None:
            self._buf_kind = "paragraph"
        self._buf.append(data)

    def close(self) -> None:  # noqa: D102
        self._flush()
        super().close()


def html_to_blocks(path: Path) -> tuple[list[Block], str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    p = ArticleParser()
    p.feed(raw)
    p.close()
    return p.blocks, p.title


# --------------------------------------------------------------------- PDF

def pdf_to_blocks(path: Path, max_pages: int | None = None) -> list[Block]:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("需要 PDF 支持：pip install pypdf")
    reader = PdfReader(str(path))
    blocks: list[Block] = []
    n = len(reader.pages) if max_pages is None else min(len(reader.pages), max_pages)
    for i in range(n):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception:
            continue
        for para in re.split(r"\n\s*\n", text):
            para = normalize_ws(para.replace("\n", " "))
            if len(para) < 3:
                continue
            # 短行且无句读→ 视为标题
            if len(para) < 90 and not re.search(r"[.!?。！？]\s*$", para) and para.count(" ") <= 12:
                blocks.append(Block("heading", para, level=2, meta={"page": i + 1}))
            elif is_probably_code(para):
                blocks.append(Block("code", para, meta={"page": i + 1}))
            else:
                blocks.append(Block("paragraph", para, meta={"page": i + 1}))
    return blocks


# ----------------------------------------------------------------- 分段

#导航/页脚/订阅等样板文本特征。不去掉这些，翻译里会出现大量
#「跳过主内容 / 订阅通讯 / 加载更多」之类的垃圾句子，直接拉低译文质量。
BOILERPLATE_PATTERNS = [
    r"^skip to (main )?content$",
    r"^(sign in|log in|log out|sign up|subscribe|subscription|newsletter|advertisement|cookie|accept all cookies|manage cookies|privacy policy|terms of (service|use)|all rights reserved)\.?$",
    r"^(loading|please wait|enable javascript|javascript (is )?(required|disabled))\.?$",
    r"^(read more|learn more|show more|load more|view all|see all|continue reading|read the full|back to (blog|top))$",
    r"^(share this|share on|follow us|copyright|all rights reserved\.?|©.*)$",
    r"^\s*(prev|next|previous|newer|older)\s*$",
    r"^(table of contents|on this page|related (posts|articles|reading)|you might also like|recommended for you)\s*$",
    r"^(by|author|published|updated|last updated)\s*:?\s*$",
]
BOILERPLATE_RE = [re.compile(p, re.I) for p in BOILERPLATE_PATTERNS]

# 整段都是短链导航的启发式：list_item 占比高、平均超短、且不含句读
def is_nav_block(b: Block, siblings: list[Block], idx: int) -> bool:
    t = b.text.strip()
    if not t:
        return True
    if any(rx.match(t) for rx in BOILERPLATE_RE):
        return True
    # 连续短小的 li 列表视为导航
    if b.kind == "list_item" and len(t) <= 40:
        win = siblings[max(0, idx - 3): idx + 4]
        if len(win) >= 3 and sum(1 for x in win if x.kind in ("list_item", "heading")) >= max(3, len(win) - 1):
            return True
    # 形如 "A | B | C" 的分隔符导航行
    if t.count("|") >= 2 and len(t) <= 160 and not re.search(r"[.!?]\s", t):
        return True
    return False


def filter_boilerplate(blocks: list[Block]) -> tuple[list[Block], int]:
    out, dropped = [], 0
    for i, b in enumerate(blocks):
        if is_nav_block(b, blocks, i):
            dropped += 1
            continue
        out.append(b)
    return out, dropped


def blocks_to_segments(
    blocks: list[Block], doc_id: str, target: int, max_chars: int, min_chars: int
) -> list[Segment]:
    """把 Block 聚成Segment。

    规则：
    - 标题与其后紧邻的正文合并成一个 Segment（避免标题被孤立翻译后语义丢失）
    - 连续段落累积到 target 字符后切分
    - 代码块单独成 Segment（不翻译，直接透传）
    - 过短的尾部与前一段合并（min_chars）
    """
    segs: list[Segment] = []
    cur: list[Block] = []
    cur_len = 0
    order = 0

    def flush(kind: str) -> None:
        nonlocal cur, cur_len, order
        if not cur:
            return
        text_parts = []
        for b in cur:
            prefix = ""
            if b.kind == "heading":
                prefix = "#" * max(1, b.level) + " "
            elif b.kind == "list_item":
                prefix = "- "
            elif b.kind == "quote":
                prefix = "> "
            elif b.kind == "code":
                prefix = "```\n" + b.text + "\n```"
            text_parts.append(prefix + b.text if b.kind != "code" else prefix)
        text = "\n\n".join(text_parts)
        sid = f"{doc_id}#{order:04d}"
        segs.append(
            Segment(
                seg_id=sid, doc_id=doc_id, order=order, kind=kind, text=text,
                blocks=[b.to_dict() for b in cur], fingerprint=sha1(text),
                word_count=count_words(text),
                meta={"block_kinds": sorted({b.kind for b in cur})},
            )
        )
        order += 1
        cur, cur_len = [], 0

    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.kind == "code":
            flush("paragraph")
            cur = [b]
            flush("code")
            i += 1
            continue
        # 标题：把后续直到下一个标题前的正文一并纳入
        if b.kind == "heading":
            flush("paragraph")
            group = [b]
            glen = len(b.text)
            j = i + 1
            while j < len(blocks) and blocks[j].kind != "heading" and glen < max_chars:
                nxt = blocks[j]
                if nxt.kind == "code":
                    break
                group.append(nxt)
                glen += len(nxt.text)
                j += 1
            cur = group
            flush("heading_group")
            i = j
            continue
        # 普通块累积
        cur.append(b)
        cur_len += len(b.text)
        if cur_len >= target:
            flush("paragraph")
        i += 1
    flush("paragraph")

    # 合并过短片段
    merged: list[Segment] = []
    for s in segs:
        if merged and s.word_count < 12 and merged[-1].kind == s.kind:
            prev = merged[-1]
            prev.text += "\n\n" + s.text
            prev.blocks += s.blocks
            prev.fingerprint = sha1(prev.text)
            prev.word_count = count_words(prev.text)
            continue
        merged.append(s)
    for idx, s in enumerate(merged):
        s.order = idx
        s.seg_id = f"{doc_id}#{idx:04d}"
    return merged


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PIPELINE_DIR / "config.json"))
    args = ap.parse_args()
    cfg = load_config(args.config)
    proj, pipe = cfg["project"], cfg["pipeline"]

    work = ensure_dir(proj["work_dir"])
    ensure_dir(work / "blocks")

    all_segments: list[Segment] = []
    stats = {"docs": [], "totals": {}}

    for src in cfg["sources"]:
        p = proj["source_root"] / src["path"]
        if not p.exists():
            warn(f"跳过（文件不存在）: {src['id']} -> {p}")
            stats["docs"].append({"id": src["id"], "status": "missing", "path": str(p)})
            continue
        try:
            if src["type"] == "html":
                blocks, title = html_to_blocks(p)
            else:
                blocks, title = pdf_to_blocks(p), ""
        except Exception as e:
            err(f"抽取失败 {src['id']}: {e}")
            stats["docs"].append({"id": src["id"], "status": "error", "error": str(e)})
            continue

        if not blocks:
            warn(f"无正文: {src['id']}（可能是占位页、需登录/JS 渲染，或纯图片 PDF）")
            stats["docs"].append({"id": src["id"], "status": "empty", "title": title,
                                  "path": src["path"],
                                  "reason": "正文为空：原文可能需登录/由 JS 渲染/为扫描版 PDF"})
            continue

        raw_blocks = len(blocks)
        blocks, dropped = filter_boilerplate(blocks)
        if dropped:
            warn(f"{src['id']}: 过滤导航/页脚样板 {dropped} 块（{raw_blocks} → {len(blocks)}）")

        segs = blocks_to_segments(
            blocks, src["id"],
            pipe["segment_target_chars"], pipe["segment_max_chars"], pipe["segment_min_chars"],
        )
        for s in segs:
            s.meta.update({"title": src["title"], "category": src.get("category", ""),
                           "priority": src.get("priority", 2), "src_path": src["path"], "type": src["type"]})
        all_segments.extend(segs)
        (work / "blocks" / f"{src['id']}.json").write_text(
            json.dumps({"meta": src, "page_title": title,
                        "blocks": [b.to_dict() for b in blocks]}, ensure_ascii=False, indent=1),
            encoding="utf-8")

        words = sum(s.word_count for s in segs)
        code_segs = sum(1 for s in segs if s.kind == "code")
        stats["docs"].append({
            "id": src["id"], "status": "ok", "title": src["title"], "category": src.get("category", ""),
            "priority": src.get("priority", 2), "type": src["type"], "path": src["path"],
            "blocks": len(blocks), "raw_blocks": raw_blocks, "boilerplate_dropped": dropped,
            "segments": len(segs), "code_segments": code_segs,
            "words": words, "translatable_words": sum(s.word_count for s in segs if s.kind != "code"),
        })
        log("extract", f"{src['id']:<42} blocks={len(blocks):>4} segs={len(segs):>4} words={words:>6}")

    n = write_jsonl(work / "segments.jsonl", [s.to_dict() for s in all_segments])
    translatable = sum(s.word_count for s in all_segments if s.kind != "code")
    stats["totals"] = {
        "docs_ok": sum(1 for d in stats["docs"] if d["status"] == "ok"),
        "docs_empty": sum(1 for d in stats["docs"] if d["status"] == "empty"),
        "docs_missing": sum(1 for d in stats["docs"] if d["status"] == "missing"),
        "segments": n,
        "words": sum(s.word_count for s in all_segments),
        "translatable_words": translatable,
    }
    ensure_dir(proj["reports_dir"])
    (proj["reports_dir"] / "00_extraction.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"共{stats['totals']['docs_ok']} 篇可用 /{n} 个 Segment / {translatable} 可翻译词 → work/segments.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
