#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
citation_auditor.py — 引用真伪审计器 / Citation Truth Auditor

输入 (Input):
    一个或多个 .bib / .tex / .md 文件
输出 (Output):
    1) 终端审计报告（每个 citekey 一行结论）
    2) Markdown 报告  <out>.audit.md
    3) 修正后的 .bib <out>.fixed.bib  （--fix 时生成）
    4) JSON 机器可读结果 <out>.audit.json

判定 (Verdict) 四档:
    VERIFIED   在权威库中检索到，且标题/作者/年份匹配   -> 可用
    PARTIAL    检索到论文，但字段有偏差（年份/作者/标题轻微不符）-> 需人工确认
    FABRICATED 标题查不到，或字段严重不符，且检出幻觉指纹 -> 疑似编造，必须删/换
    UNCHECKED  网络不可用 / 无法判定                  -> 需离线人工核查

零依赖：仅使用 Python 标准库（urllib / json / re / difflib）。
Python 3.8+。

用法:
    python3 citation_auditor.py refs.bib
    python3 citation_auditor.py paper.tex --fix --out ./audit_out
    python3 citation_auditor.py refs.bib --offline          # 不联网，只做静态体检
    python3 citation_auditor.py refs.bib --timeout 8 --jobs 4
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import difflib
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = "CitationTruthAuditor/1.0 (C4 skill; mailto:student@example.com)"

# ---------------------------------------------------------------- 归一化工具

def norm_text(s):
    """大小写/标点/重音/全角归一化，用于标题与作者比对。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("{", "").replace("}", "").replace("\\", " ")
    s = s.replace("&", " and ").lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def title_sim(a, b):
    """标题相似度 0~1：字符级 ratio 与 token 集合 Jaccard 取加权最大。

    额外处理「版本后缀」：真实标题常带子标题/版本号
    （'The Coq Proof Assistant Reference Manual' vs
      'The Coq Proof Assistant Reference Manual - version 8.19.0'），
    这时逐字 ratio 会被拖低，但二者其实是同一份文献。
    """
    a, b = norm_text(a), norm_text(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / max(1, len(ta | tb))
    # 短标题更看重 ratio，长标题更看重词集
    w = 0.6 if len(a) < 60 else 0.35
    sim = max(ratio * (1 - w) + jac * w, jac * 0.9, ratio * 0.95)
    # 包含关系 + 差异词不多 → 视为高度一致（版本号/副标题差异）
    # 例：'The Coq Proof Assistant Reference Manual'
    #     'The Coq Proof Assistant Reference Manual - version 8.19.0'
    # 差异 token 数量不超过较长标题的一半即认为同一文献。
    if a in b or b in a:
        longer = tb if a in b else ta
        extra = len(tb ^ ta) / max(1, len(longer))
        if extra <= 0.5:
            sim = max(sim, 0.95)
    return sim


def clean_doi(d):
    if not d:
        return ""
    d = str(d).strip()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d, flags=re.I)
    return d.strip().rstrip(".").lower()


def year_of(bib):
    for k in ("year", "date", "yearmonth"):
        v = bib.get(k)
        if v:
            m = re.search(r"(1[89]\d{2}|20\d{2})", str(v))
            if m:
                return int(m.group(1))
    return None


ARXIV_RE = re.compile(r"(arxiv[:/\s]*|arxiv\.)?(\d{4}\.\d{4,5})(v\d+)?", re.I)


def arxiv_id_of(bib, raw=""):
    for k in ("eprint", "archiveprefix", "primaryclass", "url", "note"):
        v = str(bib.get(k, "") or "")
        m = ARXIV_RE.search(v)
        if m:
            return m.group(2)
    m = ARXIV_RE.search(raw or "")
    return m.group(2) if m else None


# ---------------------------------------------------------------- BibTeX 解析

def parse_bib(text):
    """
    解析 BibTeX，返回 [(entry_type, citekey, {field: value}, raw_block), ...]
    手写解析器，避免依赖 bibtexparser，且容忍嵌套括号/引号。
    """
    entries = []
    # 定位每个 @ 开头的条目。用捕获组取真正的括号字符——不能用 m.end()-1，
    # 因为正则以逗号结尾，那个位置是 ','而不是 '{'或'('。
    for m in re.finditer(r"@(\w+)\s*([{(])\s*([^,\s]+)\s*,", text):
        start = m.start()
        open_ch = m.group(2)
        close_ch = "}" if open_ch == "{" else ")"
        depth = 1
        i = m.end()
        in_q = False
        # 安全上限：正常 bib 条目远小于此。防止一个未闭合的条目吞掉整个文件。
        hard_limit = min(len(text), i + 20000)
        while i < hard_limit and depth > 0:
            c = text[i]
            if c == '"' and text[i - 1] != "\\":
                in_q = not in_q
            elif not in_q:
                if c == open_ch:
                    depth += 1
                elif c == close_ch:
                    depth -= 1
            i += 1
        body = text[m.end(): i - 1]
        raw = text[start:i]
        fields = parse_fields(body)
        entries.append((m.group(1).lower(), m.group(3).strip(), fields, raw))
    return entries


def parse_fields(body):
    """解析 entry 内部的 field = {value} / field = "value" / field = number。"""
    fields = {}
    i = 0
    n = len(body)
    while i < n:
        eq = body.find("=", i)
        if eq == -1:
            break
        name = body[i:eq].strip().strip(",").strip().lower()
        j = eq + 1
        while j < n and body[j] in " \t\r\n,":
            j += 1
        if j >= n:
            break
        if body[j] == "{":
            depth, k = 1, j + 1
            while k < n and depth:
                if body[k] == "{":
                    depth += 1
                elif body[k] == "}":
                    depth -= 1
                k += 1
            val = body[j + 1: k - 1]
        elif body[j] == '"':
            k = j + 1
            while k < n and body[k] != '"':
                k += 1
            val = body[j + 1: k]
        else:
            k = j
            while k < n and body[k] != ",":
                k += 1
            val = body[j:k]
        if name:
            fields[name] = re.sub(r"\s+", " ", val).strip()
        i = k + 1
    return fields


def parse_tex_cites(text):
    """提取 .tex 中的 \\cite / \\citep / \\citet 等引用 key。"""
    keys = []
    for m in re.finditer(r"\\[a-zA-Z]*cite[a-zA-Z]*\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", text):
        for k in m.group(1).split(","):
            k = k.strip()
            if k:
                keys.append(k)
    return keys


# ---------------------------------------------------------------- 幻觉指纹

HALLUC_PATTERNS = [
    # (正则, 说明, 严重度)
    (r"arxiv[:/\s]*\d{4}\.\d{4,5}", "arXiv ID 格式正确", 0),
    (r"10\.\d{4,9}/[-._;()/:a-z0-9]+", "DOI 格式正确", 0),
    (r"\b(proceedings|journal|transactions|annals|bulletin)\s+of\s+.{0,40}(symposium|conference|workshop)", "泛化会议/期刊名，常见于编造", 1),
    (r"\bin\s+the\s+proceedings\s+of\s+the\s+international\b", "模板化会议名占位符", 2),
    (r"\b(19|20)\d{2}\b", "含年份", 0),
    (r"et\s+al\.", "作者含 et al.（核查时无法定位首作者）", 1),
]


def hallucination_fingerprints(title, fields):
    """对标题与字段做启发式幻觉检测，返回 [(信号, 严重度)]。"""
    sig = []
    t = title or ""
    low = t.lower()
    # 1) 过于"通用"的标题：每个词都很常见但组合不存在
    words = [w for w in norm_text(t).split() if len(w) > 3]
    if len(words) >= 4:
        common = sum(1 for w in words if w in
                     {"learning", "model", "models", "network", "networks", "data",
                      "analysis", "method", "methods", "approach", "based", "system",
                      "framework", "algorithm", "deep", "neural", "intelligent", "survey"})
        if common / len(words) > 0.5:
            sig.append(("标题由高频泛义词堆砌，疑似占位/编造", 2))
    # 2) 标题含模板化会议占位
    if re.search(r"in\s+the\s+proceedings\s+of\s+the\s+international", low):
        sig.append(("标题使用 'In the Proceedings of the International...' 占位式表述", 2))
    # 3) 年份在未来 / 明显不可能
    y = year_of(fields)
    if y and (y > 2026 or y < 1600):
        sig.append((f"年份 {y} 不合理（未来或过旧）", 2))
    # 4) 有 DOI 但格式损坏
    doi = fields.get("doi", "")
    if doi and not re.match(r"10\.\d{4,9}/\S+", doi.strip()):
        sig.append((f"DOI 格式损坏: {doi[:40]}", 2))
    # 5) 作者列表为空或只有一个单词
    a = fields.get("author", "")
    if not a.strip():
        sig.append(("缺少作者字段", 2))
    # 6) 页码范围不可能
    pg = fields.get("pages", "")
    m = re.match(r"^(\d+)\s*[-–]+\s*(\d+)$", pg.strip())
    if m and int(m.group(2)) < int(m.group(1)):
        sig.append((f"页码区间倒置: {pg}", 2))
    return sig


# ---------------------------------------------------------------- HTTP 层

def http_get(url, timeout=10, retries=2):
    """带重试与限速的 GET。返回 str 或 None。"""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception:
            time.sleep(0.8 * (attempt + 1))
    return None


def q(s):
    return urllib.parse.quote(str(s or ""), safe="")


# ---------------------------------------------------------------- 数据源查询

def query_crossref_by_doi(doi, timeout):
    data = http_get(f"https://api.crossref.org/works/{q(doi)}?mailto=student@example.com", timeout)
    if not data:
        return None
    try:
        m = json.loads(data).get("message", {})
        if not m.get("title"):
            return None
        return {
            "source": "Crossref",
            "title": (m.get("title") or [""])[0],
            "year": (m.get("issued", {}).get("date-parts", [[None]])[0][0]),
            "authors": [" ".join(filter(None, [a.get("given"), a.get("family")]))
                        for a in m.get("author", [])][:12],
            "venue": (m.get("container-title") or [""])[0],
            "doi": m.get("DOI", ""),
            "url": m.get("URL", ""),
            "cited_by": m.get("is-referenced-by-count", None),
        }
    except Exception:
        return None


def query_crossref_by_title(title, timeout, rows=3):
    url = ("https://api.crossref.org/works?query.bibliographic="
           f"{q(title)}&rows={rows}&mailto=student@example.com")
    data = http_get(url, timeout)
    if not data:
        return None
    try:
        items = json.loads(data).get("message", {}).get("items", [])
    except Exception:
        return None
    out = []
    for m in items:
        t = (m.get("title") or [""])[0]
        if not t:
            continue
        out.append({
            "source": "Crossref",
            "title": t,
            "year": (m.get("issued", {}).get("date-parts", [[None]])[0][0]),
            "authors": [" ".join(filter(None, [a.get("given"), a.get("family")]))
                        for a in m.get("author", [])][:12],
            "venue": (m.get("container-title") or [""])[0],
            "doi": m.get("DOI", ""),
            "url": m.get("URL", ""),
            "cited_by": m.get("is-referenced-by-count", None),
            "_sim": title_sim(title, t),
        })
    return out


def query_openalex_by_title(title, timeout, rows=3):
    url = (f"https://api.openalex.org/works?filter=title.search:{q(title)}"
           f"&per-page={rows}&mailto=student@example.com")
    data = http_get(url, timeout)
    if not data:
        return None
    try:
        items = json.loads(data).get("results", [])
    except Exception:
        return None
    out = []
    for m in items:
        loc = m.get("primary_location") or {}
        src = loc.get("source") or {}
        out.append({
            "source": "OpenAlex",
            "title": m.get("title") or m.get("display_name") or "",
            "year": m.get("publication_year"),
            "authors": [a.get("author", {}).get("display_name", "")
                        for a in m.get("authorships", [])][:12],
            "venue": src.get("display_name") or "",
            "doi": (m.get("doi") or "").replace("https://doi.org/", ""),
            "url": loc.get("landing_page_url") or m.get("id") or "",
            "cited_by": m.get("cited_by_count", None),
            "_sim": title_sim(title, m.get("title") or ""),
        })
    return out


def query_arxiv_by_id(arxiv_id, timeout):
    data = http_get(f"https://export.arxiv.org/api/query?id_list={q(arxiv_id)}"
                    f"&max_results=1", timeout)
    if not data:
        return None
    try:
        root = ET.fromstring(data)
    except Exception:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    e = root.find("a:entry", ns)
    if e is None:
        return None
    title = (e.findtext("a:title", "", ns) or "").strip().replace("\n", " ")
    if not title:
        return None
    authors = [(a.findtext("a:name", "", ns) or "").strip()
               for a in e.findall("a:author", ns)][:12]
    pub = (e.findtext("a:published", "", ns) or "")
    year = int(pub[:4]) if pub[:4].isdigit() else None
    return {"source": "arXiv", "title": title, "year": year, "authors": authors,
            "venue": "arXiv preprint", "doi": "", "url": f"https://arxiv.org/abs/{arxiv_id}",
            "cited_by": None, "arxiv": arxiv_id}


# ---------------------------------------------------------------- 核心核查

def split_authors(field):
    """拆分 BibTeX author 字段。

    需要同时支持三种分隔符，因为真实 .bib 三种都有人用：
        'A and B and C'   ← BibTeX 标准
        'A; B; C'        ← Nature/部分期刊导出格式
        'A, B and others'← 含 'others' 的简写
    """
    s = str(field or "").strip()
    if not s:
        return []
    s = re.sub(r"\s+and\s+others\b", "", s, flags=re.I)
    s = re.sub(r"\s*\betal\b\.?", "", s, flags=re.I)
    parts = re.split(r"\s+and\s+|;", s)
    return [p.strip() for p in parts if p.strip()]


def _surname(name):
    """从单个作者名中提取姓氏。

    同时兼容两种写法：
        'Vaswani, Ashish'  -> vaswani   (BibTeX 常用'姓, 名')
        'Ashish Vaswani'  -> vaswani   (API 返回 '名 姓')
    另外处理机构作者：'{The Coq Development Team}' 整体作为一个"姓氏"，
    否则花括号包裹会导致姓/名切分错误、匹配不上。
    """
    n = str(name or "").strip()
    if not n:
        return ""
    # 机构作者：整体作为单个标识（去掉外层花括号）
    if n.startswith("{") and n.endswith("}"):
        return norm_text(n.strip("{}"))
    if "," in n:                       # '姓, 名' —— 取逗号前
        return norm_text(n.split(",")[0])
    parts = [p for p in norm_text(n).split() if p]
    if not parts:
        return ""
    # '名 姓' —— 取最后一段；排除可能的后缀 (Jr., III)
    if len(parts) >= 2 and parts[-1] in ("jr", "sr", "ii", "iii", "iv", "phd", "md"):
        parts = parts[:-1]
    return parts[-1] if parts else ""


def author_overlap(a, b):
    """作者姓氏重合度 0~1。取较短列表做分母，避免长作者列表稀释结果。"""
    sa = {_surname(x) for x in (a or [])}
    sb = {_surname(x) for x in (b or [])}
    sa = {x for x in sa if x}
    sb = {x for x in sb if x}
    if not sa or not sb:
        return -1.0          # 无法判断，交由调用方跳过该维度
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def audit_entry(etype, key, bib, timeout=10, offline=False, threshold=0.82):
    """核查单条 bib 条目，返回结论 dict。"""
    title = bib.get("title", "")
    bib_year = year_of(bib)
    bib_authors = split_authors(bib.get("author", ""))
    doi = clean_doi(bib.get("doi", ""))
    arxiv_id = arxiv_id_of(bib)
    fingerprints = hallucination_fingerprints(title, bib)

    rec = {
        "key": key, "type": etype, "title": title,
        "bib_year": bib_year, "bib_authors": bib_authors[:5],
        "bib_doi": doi, "bib_arxiv": arxiv_id,
        "bib_venue": bib.get("journal") or bib.get("booktitle") or "",
        "fingerprints": fingerprints,
        "source_used": None, "matched": None,
        "title_sim": 0.0, "author_overlap": -1.0,
        "verdict": "UNCHECKED", "reason": "", "suggested": None,
    }

    if not title.strip():
        rec["verdict"] = "UNCHECKED"
        rec["reason"] = "条目无 title 字段，无法检索"
        return rec

    if offline:
        rec["reason"] = "离线模式：仅完成静态体检，幻觉指纹 %d 条" % len(fingerprints)
        rec["verdict"] = "FABRICATED" if any(s >= 2 for _, s in fingerprints) else "UNCHECKED"
        return rec

    # ---- A. DOI 直查（最高置信度）
    candidates = []
    if doi:
        # arXiv 的 DOI 前缀是 10.48550（DataCite 签发），Crossref 查不到，
        # 必须改走 arXiv 精确查询，否则会误判为编造。
        if doi.startswith("10.48550/arxiv."):
            ax_id = doi.split("10.48550/arxiv.", 1)[1].strip()
            r = query_arxiv_by_id(ax_id, timeout)
            if r:
                r["_sim"] = title_sim(title, r["title"])
                candidates.append(r)
        else:
            r = query_crossref_by_doi(doi, timeout)
            if r:
                r["_sim"] = title_sim(title, r["title"])
                candidates.append(r)
    # ---- B. arXiv ID 直查
    if arxiv_id:
        r = query_arxiv_by_id(arxiv_id, timeout)
        if r:
            r["_sim"] = title_sim(title, r["title"])
            candidates.append(r)
    # ---- C. 标题检索（Crossref + OpenAlex 并行）
    if not candidates or max(c["_sim"] for c in candidates) < threshold:
        cr = query_crossref_by_title(title, timeout) or []
        oa = query_openalex_by_title(title, timeout) or []
        candidates.extend(cr + oa)

    if not candidates:
        rec["verdict"] = "UNCHECKED" if not fingerprints else "FABRICATED"
        rec["reason"] = ("所有数据源均无结果（网络不可达或确实不存在）"
                         if not fingerprints else "数据源无结果 + 检出幻觉指纹")
        if any(s >= 2 for _, s in fingerprints):
            rec["verdict"] = "FABRICATED"
        return rec

    def rank(c):
        """排序键：作者吻合 > 年份接近 > 标题相似度 > 引用量。

        三点都必要：
        - 作者参与排序——否则同名不同作者的论文会挤掉正确记录；
        - 年份参与排序——OpenAlex 常把论文的某个重印/修订版当作主记录
          （例如把 2017 的 Attention Is All You Need 挂到 2025 的条目上），
          bib 中的年份是强先验，应参与择优；
        - 标题相似度与引用量用于打破平局。
        """
        ao = author_overlap(bib_authors, c["authors"])
        ao_key = 0.5 if ao < 0 else min(1.0, ao)
        if bib_year and c["year"]:
            gap = abs(bib_year - c["year"])
            yr_key = 1.0 / (1.0 + gap)
        else:
            yr_key = 0.5
        return (round(ao_key, 2), round(yr_key, 3), c["_sim"], (c.get("cited_by") or 0))

    best = max(candidates, key=rank)
    best_ao = author_overlap(bib_authors, best["authors"])
    rec["matched"] = best
    rec["source_used"] = best["source"]
    rec["title_sim"] = round(best["_sim"], 3)
    rec["author_overlap"] = round(best_ao, 3)
    rec["suggested"] = {
        "title": best["title"], "year": best["year"], "venue": best["venue"],
        "doi": best.get("doi", ""), "url": best.get("url", ""),
        "authors": best["authors"][:5], "cited_by": best.get("cited_by"),
    }

    # ---- 判定逻辑
    sim = best["_sim"]
    yr_ok = (bib_year is None or best["year"] is None
             or abs(bib_year - best["year"]) <= 1)
    ao = best_ao
    au_ok = (ao < 0 or ao >= 0.5)

    if sim >= 0.95 and yr_ok and au_ok:
        rec["verdict"] = "VERIFIED"
        rec["reason"] = f"{best['source']} 命中，标题相似度 {sim:.2f}，年份/作者一致"
    elif sim >= 0.95 and yr_ok and not au_ok:
        # 标题几乎完全一致、年份也对，只有作者对不上——更可能是作者字段写法
        # （机构作者、分隔符差异、超长作者列表截断）导致的匹配偏差，
        # 而不是文献本身有问题。降级为 PARTIAL 并说明，不直接判编造。
        rec["verdict"] = "PARTIAL"
        rec["reason"] = (f"{best['source']} 命中且标题一致（相似度 {sim:.2f}）、年份相符，"
                         f"但作者姓氏重合度仅 {ao:.2f}（写法差异或作者列表过长）；"
                         "文献很可能存在，请人工确认作者信息")
    elif sim >= threshold:
        rec["verdict"] = "PARTIAL"
        why = []
        # 标题+作者都对得上、只有年份对不上时，多半是权威库把同一篇论文的
        # 重印/修订/重新索引版本当作主记录（如 ACM 的 10.5555 前缀不在
        # Crossref 注册，导致回退到 OpenAlex 命中另一条年份不同的记录）。
        # 这不是"写错了"，如实说明，不误报为字段错误。
        version_drift = (not yr_ok and sim >= 0.95 and au_ok)
        if not yr_ok:
            why.append(f"年份不一致（bib={bib_year} vs 数据源={best['year']}）")
        if not au_ok:
            why.append(f"作者不匹配（姓氏重合度 {ao:.2f}）")
        if sim < 0.95:
            why.append(f"标题偏差（相似度 {sim:.2f}）")
        if version_drift:
            rec["verdict"] = "PARTIAL"
            rec["reason"] = ("检索到同一篇论文（标题与作者均吻合），但数据源年份为 "
                             f"{best['year']}；常见于同一论文存在重印/修订版本，"
                             "建议人工确认后再决定是否改 year 字段。" + " 其余：" + "；".join(why))
        else:
            rec["reason"] = "检索到论文，但" + "；".join(why)
    else:
        # 最相似都不达标 —— 引用不存在，或属于权威库不收录的类型
        s = best["title"]
        # 学术三库（Crossref/arXiv/OpenAlex）不收录软件手册、技术文档、
        # 标准文本、内部资料。这类条目查不到是**预期的**，不是编造。
        # 判为 UNCHECKED 并说明原因，避免把合法引用误杀成"编造"。
        doc_kw = ("reference manual", "user manual", "user guide", "documentation",
                  "technical report", "standard", "specification", "handbook",
                  "reference guide", "getting started", "教程", "手册", "文档")
        low = (title + " " + (bib.get("booktitle", "") or "")
               + " " + (bib.get("journal", "") or "") + " " + (bib.get("note", "") or "")).lower()
        is_doc = any(k in low for k in doc_kw)
        if best.get("cited_by") and best["cited_by"] > 0:
            rec["verdict"] = "PARTIAL"
            rec["reason"] = (f"仅模糊匹配到《{s[:50]}》（相似度 {sim:.2f}，"
                             f"引用量 {best['cited_by']}），证据不足以确认，请人工核查")
        elif is_doc:
            rec["verdict"] = "UNCHECKED"
            rec["reason"] = ("疑似软件手册/技术文档类条目——Crossref、arXiv、OpenAlex "
                             "均不收录此类文献，查不到属预期。请人工确认其存在性")
        else:
            rec["verdict"] = "FABRICATED"
            rec["reason"] = (f"最佳匹配仅 {sim:.2f} < 阈值 {threshold}"
                             f"（最接近的是《{s[:60]}》），判定为编造引用")
    return rec


# ---------------------------------------------------------------- 输入装载

def load_entries(paths):
    entries, cited, files = [], set(), []
    for p in paths:
        try:
            raw = open(p, "r", encoding="utf-8", errors="replace").read()
        except OSError as e:
            print(f"[!] 无法读取 {p}: {e}", file=sys.stderr)
            continue
        files.append(p)
        if p.lower().endswith(".bib"):
            entries += [(t, k, f, r) for (t, k, f, r) in parse_bib(raw)]
        else:
            # .tex / .md：抓取其中的 \cite key，并把整个文件当上下文
            cited |= set(parse_tex_cites(raw))
            entries += [(t, k, f, r) for (t, k, f, r) in parse_bib(raw)]
    return entries, cited, files


# ---------------------------------------------------------------- 输出

MARK = {"VERIFIED": "[VERIFIED]", "PARTIAL": "[PARTIAL]",
        "FABRICATED": "[FABRICATED]", "UNCHECKED": "[UNCHECKED]"}


def render_console(results, files, elapsed):
    print("=" * 78)
    print("引用真伪审计报告 / Citation Truth Audit Report")
    print("=" * 78)
    print(f"输入文件: {', '.join(files)}")
    n = len(results)
    print(f"共审计 {n} 条引用，用时 {elapsed:.1f}s\n")
    order = {"FABRICATED": 0, "PARTIAL": 1, "UNCHECKED": 2, "VERIFIED": 3}
    for r in sorted(results, key=lambda x: (order[x["verdict"]], -x["title_sim"])):
        line = f"{MARK[r['verdict']]} {r['key']}"
        line += f"\n    题名: {(r['title'] or '(无)')[:70]}"
        if r["bib_authors"]:
            line += f"\n    作者: {', '.join(r['bib_authors'][:3])}"
        line += f"\n    年份: {r['bib_year']}  期刊: {r['bib_venue'] or '-'}  DOI: {r['bib_doi'] or '-'}"
        line += f"\n    结论: {r['reason']}"
        if r["verdict"] == "PARTIAL" and r["suggested"]:
            s = r["suggested"]
            line += (f"\n    建议修正: 题名=《{s['title'][:55]}》 年份={s['year']} "
                     f"期刊={s['venue'][:30]} DOI={s['doi'] or '-'}")
        for sig, sev in r["fingerprints"]:
            if sev:
                line += f"\n    ⚠ 幻觉指纹[{sev}]: {sig}"
        print(line)
        print("-" * 78)
    cnt = {}
    for r in results:
        cnt[r["verdict"]] = cnt.get(r["verdict"], 0) + 1
    print("\n汇总 / Summary")
    print("-" * 78)
    total = max(1, n)
    for v in ("VERIFIED", "PARTIAL", "FABRICATED", "UNCHECKED"):
        c = cnt.get(v, 0)
        print(f"  {MARK[v]:<13} {c:>3} 条  ({c*100//total:>3}%)")
    if cnt.get("FABRICATED"):
        print(f"\n⚠ 有 {cnt['FABRICATED']} 条疑似编造引用，提交前必须删除或替换。")
        print("  处理顺序：1) FABRICATED 全部删除或换成真实来源")
        print("            2) PARTIAL 按建议字段修正")
        print("            3) VERIFIED 保留")
    print()


def render_markdown(results, files, elapsed):
    L = ["# 引用真伪审计报告 / Citation Truth Audit Report", ""]
    L.append(f"- **输入文件**: {', '.join(f'`{f}`' for f in files)}")
    L.append(f"- **审计条数**: {len(results)}")
    L.append(f"- **用时**: {elapsed:.1f}s")
    L.append("- **数据源**: Crossref → arXiv → OpenAlex（含回退）")
    L.append("")
    order = {"FABRICATED": 0, "PARTIAL": 1, "UNCHECKED": 2, "VERIFIED": 3}
    L.append("## 1. 判定汇总")
    L.append("")
    cnt = {}
    for r in results:
        cnt[r["verdict"]] = cnt.get(r["verdict"], 0) + 1
    L.append("| 判定 | 数量 | 占比 | 含义 |")
    L.append("|---|---|---|---|")
    mean = {"VERIFIED": "可用", "PARTIAL": "需人工确认字段",
            "FABRICATED": "疑似编造，必须删/换", "UNCHECKED": "证据不足，需核查"}
    total = max(1, len(results))
    for v in ("VERIFIED", "PARTIAL", "FABRICATED", "UNCHECKED"):
        c = cnt.get(v, 0)
        L.append(f"| {MARK[v]} | {c} | {c*100//total}% | {mean[v]} |")
    L.append("")
    L.append("## 2. 逐条明细")
    L.append("")
    for r in sorted(results, key=lambda x: (order[x["verdict"]], -x["title_sim"])):
        L.append(f"### {MARK[r['verdict']]} `{r['key']}`")
        L.append("")
        L.append(f"- **题名**: {r['title'] or '(缺失)'}")
        L.append(f"- **作者**: {', '.join(r['bib_authors']) or '(缺失)'}")
        L.append(f"- **年份**: {r['bib_year']}　**期刊**: {r['bib_venue'] or '-'}")
        L.append(f"- **DOI**: {r['bib_doi'] or '-'}　**arXiv**: {r['bib_arxiv'] or '-'}")
        L.append(f"- **结论**: {r['reason']}")
        if r["verdict"] == "PARTIAL" and r["suggested"]:
            s = r["suggested"]
            L.append(f"- **建议修正为**:")
            L.append(f"  - title = {{{s['title']}}}")
            L.append(f"  - year = {{{s['year']}}}")
            L.append(f"  - journal = {{{s['venue']}}}")
            L.append(f"  - doi = {{{s['doi'] or '-'}}}　url = {{{s['url']}}}")
        if r["fingerprints"]:
            L.append("- **幻觉指纹**:")
            for sig, sev in r["fingerprints"]:
                L.append(f"  - [严重度 {sev}] {sig}")
        L.append("")
    L.append("## 3. 修复建议")
    L.append("")
    if cnt.get("FABRICATED"):
        L.append(f"1. **删除或替换 {cnt['FABRICATED']} 条编造引用**——这些标题在 Crossref / arXiv / OpenAlex 中均不存在。")
    else:
        L.append("1. 未发现编造引用。")
    if cnt.get("PARTIAL"):
        L.append(f"2. **修正 {cnt['PARTIAL']} 条 PARTIAL 引用**的年份/期刊/DOI 字段（见第 2 节建议值）。")
    L.append("3. 修正后用 `latexmk -pdf` 重新编译，确认无 undefined citation。")
    L.append("4. 若引用确实找不到但正文论述依赖它，改写为\"已有工作尚缺证据\"的表述，而非虚构引用。")
    L.append("")
    return "\n".join(L)


def build_fixed_bib(results, entries, out_path):
    """对 PARTIAL 条目用权威库字段覆盖，生成修正版 .bib。"""
    raw_map = {k: r for (_, k, _, r) in entries}
    by_key = {r["key"]: r for r in results}
    lines = ["% Auto-generated by citation_auditor.py --fix",
             "% VERIFIED entries kept as-is; PARTIAL entries field-corrected.",
             "% FABRICATED entries are commented out, NOT deleted (review before removing).",
             ""]
    for key in [k for (_, k, _, _) in entries]:
        r = by_key.get(key)
        if not r:
            continue
        raw = raw_map[key]
        if r["verdict"] == "FABRICATED":
            lines.append("% !! FABRICATED -- 疑似编造，禁止直接引用：")
            for ln in raw.splitlines():
                lines.append("% " + ln)
            lines.append("")
        elif r["verdict"] == "PARTIAL" and r["suggested"]:
            fixed = raw
            s = r["suggested"]
            # 版本漂移（标题+作者吻合、仅年份不同）不要自动改写 year——
            # 数据源年份未必比 bib 里的更权威，交给人工判断。
            drift = ("重印/修订版本" in (r.get("reason") or ""))
            if drift:
                lines.append("% PARTIAL but NOT auto-corrected: 疑似版本漂移（标题/作者吻合，"
                             "仅年份不同），year 字段保留原值，请人工确认：")
                lines.append(fixed)
                lines.append("")
                continue
            if re.search(r"(?im)^\s*title\s*=", fixed):
                fixed = re.sub(r"(?im)^\s*title\s*=\s*[{\"].*?([}\"])\s*,?\s*$",
                               lambda m: f"  title = {{{s['title']}}},", fixed, count=1)
            if s["year"] and re.search(r"(?im)^\s*year\s*=", fixed):
                fixed = re.sub(r"(?im)^\s*year\s*=\s*[{\"]?\s*\d{4}\s*[}\"]?\s*,?\s*$",
                               f"  year = {{{s['year']}}},", fixed, count=1)
            if s["venue"] and re.search(r"(?im)^\s*(journal|booktitle)\s*=", fixed):
                key2 = "journal" if re.search(r"(?im)^\s*journal\s*=", fixed) else "booktitle"
                fixed = re.sub(rf"(?im)^\s*{key2}\s*=\s*[{{\"].*?([}}\"])\s*,?\s*$",
                               lambda m: f"  {key2} = {{{s['venue']}}},", fixed, count=1)
            if s["doi"] and re.search(r"(?im)^\s*doi\s*=", fixed):
                fixed = re.sub(r"(?im)^\s*doi\s*=\s*[{\"].*?([}\"])\s*,?\s*$",
                               f"  doi = {{{s['doi']}}},", fixed, count=1)
            lines.append(f"% PARTIAL corrected from {r['source_used']} (sim={r['title_sim']}):")
            lines.append(fixed)
            lines.append("")
        else:
            lines.append(raw)
            lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="引用真伪审计器：核查 .bib/.tex 中每条引用是否真实存在（零依赖）")
    ap.add_argument("inputs", nargs="+", help=".bib / .tex / .md 文件")
    ap.add_argument("--out", default=".", help="输出目录（默认当前目录）")
    ap.add_argument("--fix", action="store_true", help="生成字段修正后的 .bib")
    ap.add_argument("--offline", action="store_true", help="不联网，仅做静态体检")
    ap.add_argument("--timeout", type=int, default=10, help="单次 HTTP 超时秒（默认 10）")
    ap.add_argument("--jobs", type=int, default=4, help="并发数（默认 4）")
    ap.add_argument("--threshold", type=float, default=0.82, help="标题相似度阈值（默认 0.82）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    t0 = time.time()
    entries, cited, files = load_entries(args.inputs)

    if not entries:
        print("[!] 未解析到任何 BibTeX 条目。请确认文件是 .bib，或含 @article/@inproceedings 等条目。",
              file=sys.stderr)
        sys.exit(2)

    # 统计：正文引用但 bib 里没有
    missing = sorted(cited - {k for (_, k, _, _) in entries})
    unused = sorted({k for (_, k, _, _) in entries} - cited) if cited else []

    print(f"[i] 解析到 {len(entries)} 条 bib 条目，开始核查…")
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = {ex.submit(audit_entry, t, k, f, args.timeout, args.offline,
                          args.threshold): k for (t, k, f, _) in entries}
        for fu in as_completed(futs):
            key = futs[fu]
            try:
                results.append(fu.result())
            except Exception as e:  # 单条失败不影响整体
                results.append({
                    "key": key, "type": "?", "title": "", "bib_year": None,
                    "bib_authors": [], "bib_doi": "", "bib_arxiv": None,
                    "bib_venue": "", "fingerprints": [], "source_used": None,
                    "matched": None, "title_sim": 0.0, "author_overlap": -1.0,
                    "verdict": "UNCHECKED", "reason": f"核查异常: {e}",
                    "suggested": None})

    # 按原始顺序排序
    order_keys = [k for (_, k, _, _) in entries]
    results.sort(key=lambda r: order_keys.index(r["key"]) if r["key"] in order_keys else 999)

    elapsed = time.time() - t0
    os.makedirs(args.out, exist_ok=True)
    render_console(results, files, elapsed)

    if missing:
        print(f"[!] 正文 \\cite 引用了但 .bib 中不存在: {', '.join(missing)}")
    if unused and cited:
        print(f"[i] .bib 中存在但正文未引用: {', '.join(unused)}")

    stem = os.path.splitext(os.path.basename(args.inputs[0]))[0]
    md_path = os.path.join(args.out, f"{stem}.audit.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(results, files, elapsed))
    print(f"[✓] Markdown 报告: {md_path}")

    if args.json:
        js = os.path.join(args.out, f"{stem}.audit.json")
        with open(js, "w", encoding="utf-8") as f:
            json.dump({"files": files, "elapsed": elapsed,
                       "missing_cited_keys": missing, "unused_bib_keys": unused,
                       "results": results}, f, ensure_ascii=False, indent=2)
        print(f"[✓] JSON 结果: {js}")

    if args.fix:
        fb = os.path.join(args.out, f"{stem}.fixed.bib")
        build_fixed_bib(results, entries, fb)
        print(f"[✓] 修正版 bib: {fb}（FABRICATED 条目已注释，未直接删除）")

    n_bad = sum(1 for r in results if r["verdict"] == "FABRICATED")
    sys.exit(1 if n_bad else 0)   # 退出码 1 = 存在编造引用，方便 CI 集成


if __name__ == "__main__":
    main()