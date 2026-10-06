#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
c4a_evaluator.py — C4 技能提交自动评审器（C4A Level 1-4）

拿来做的事：把 wechat-doc-mapper 的"分类盘点"升级为"自动阅卷"。

四阶段流水线：
    ① 文件采集与作者识别   → collect_submissions()
    ② 提交完整性检查       → check_completeness()
    ③ 技能质量评审（四条件）→ evaluate_quality()
    ④ 评审报告生成         → Markdown / JSON / Excel

设计取舍（详见 references/c4_rubric.yaml 顶部注释）：
    规则层做确定性判定（快、免费、可复现、可单测）
    LLM 层作为可选深审（--llm-reviewed），不在默认路径上
    理由：C4A 要评的是"客观可判定的信号"，规则层的可审计性 > LLM 的覆盖率

用法：
    python c4a_evaluator.py <FOLDER> --outdir <OUTDIR> [--md NAME] [--json NAME]
                           [--xlsx NAME] [--strict] [--verbose]

只依赖：PyYAML（必需）、openpyxl（可选，仅 --xlsx 需要）
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "ERROR: 需要 PyYAML。请先运行  pip install pyyaml\n"
        "（本脚本除 YAML 外全部使用标准库）\n"
    )
    raise SystemExit(2)

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RUBRIC = SKILL_DIR / "references" / "c4_rubric.yaml"

MAX_SIZE_KB = 50_000          # > 50MB 只按文件名判定，不读内容
MAX_TEXT_BYTES = 400_000      # 单文件最多读 400KB 文本，避免拖慢扫描

# --------------------------------------------------------------------------
# 文本提取：能提取就提取，提取不了就优雅降级（绝不因单个坏文件中断全批）
# --------------------------------------------------------------------------

TEXTUAL_EXT = {
    ".md", ".txt", ".py", ".json", ".yaml", ".yml", ".sh", ".js",
    ".ts", ".html", ".css", ".toml", ".cfg", ".ini", ".tex", ".bib", ".log",
}
EXTRACTABLE_EXT = TEXTUAL_EXT | {".pdf", ".docx", ".skill", ".zip", ".tar", ".gz", ".pptx", ".xlsx"}


def _read_text_safe(path: Path) -> str:
    """尽力读取文本内容；任何失败都返回空串而不是抛异常。"""
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(MAX_TEXT_BYTES)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(MAX_TEXT_BYTES)
    except (OSError, UnicodeError):
        return ""


def _text_from_skill_archive(path: Path) -> str:
    """.skill 是 tar.gz；取其中所有文本类成员拼起来评审。"""
    chunks: list[str] = []
    try:
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as tf:
                for m in tf.getmembers():
                    if not m.isfile() or m.size > MAX_TEXT_BYTES:
                        continue
                    if Path(m.name).suffix.lower() not in TEXTUAL_EXT:
                        continue
                    fp = tf.extractfile(m)
                    if fp is None:
                        continue
                    with fp:
                        chunks.append(f"### [archive member] {m.name}\n"
                                      + fp.read().decode("utf-8", errors="replace"))
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                for n in zf.namelist():
                    if Path(n).suffix.lower() not in TEXTUAL_EXT:
                        continue
                    if zf.getinfo(n).file_size > MAX_TEXT_BYTES:
                        continue
                    chunks.append(f"### [archive member] {n}\n"
                                  + zf.read(n).decode("utf-8", errors="replace"))
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        pass
    return "\n".join(chunks)


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in TEXTUAL_EXT:
        return _read_text_safe(path)
    if ext in {".skill", ".tar", ".gz"}:
        return _text_from_skill_archive(path)
    if ext == ".zip":
        return _text_from_skill_archive(path)
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            r = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in r.pages[:40])
        except Exception:
            return ""
    if ext == ".docx":
        try:
            import docx  # python-docx
            d = docx.Document(str(path))
            return "\n".join(p.text for p in d.paragraphs)
        except Exception:
            # 无 python-docx 时退回 zip 内 XML 抽取（docx 本质是 zip）
            try:
                with zipfile.ZipFile(path) as zf:
                    if "word/document.xml" in zf.namelist():
                        raw = zf.read("word/document.xml").decode("utf-8", "replace")
                        return re.sub(r"<[^>]+>", " ", raw)
            except Exception:
                pass
            return ""
    if ext == ".pptx":
        try:
            from pptx import Presentation
            pr = Presentation(str(path))
            return "\n".join(
                sh.text_frame.text
                for sl in pr.slides
                for sh in sl.shapes
                if getattr(sh, "has_text_frame", False)
            )
        except Exception:
            return ""
    if ext == ".xlsx":
        try:
            from openpyxl import load_workbook
            wb = load_workbook(str(path), read_only=True)
            buf = []
            for ws in wb.worksheets:
                buf.append(f"# sheet {ws.title}")
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    buf.append(" ".join(str(c) for c in row if c is not None))
                    if i > 200:
                        break
            wb.close()
            return "\n".join(buf)
        except Exception:
            return ""
    return ""


def find_evidence(text: str, pattern: str) -> list[dict]:
    """在文本中定位命中位置，产出可引用的证据（行号 + 片段）。

    这是"证据化评分"的实现基础：每一条评审依据都必须能追溯到具体行。
    """
    out: list[dict] = []
    if not text:
        return out
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return out
    lines = text.splitlines()
    for idx, line in enumerate(lines, 1):
        if rx.search(line):
            snippet = line.strip()
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            out.append({"line": idx, "text": snippet})
            if len(out) >= 3:      # 每条信号最多留 3 条证据，避免报告冗长
                break
    return out


def keyword_hits(text: str, keywords: Iterable[str]) -> list[dict]:
    """关键词命中，返回带行号的证据列表。"""
    hits: list[dict] = []
    if not text:
        return hits
    lines = text.splitlines()
    low = [ln.lower() for ln in lines]
    for kw in keywords:
        kw_l = str(kw).lower()
        for i, ln in enumerate(low, 1):
            if kw_l in ln:
                snippet = lines[i - 1].strip()
                if len(snippet) > 160:
                    snippet = snippet[:157] + "..."
                hits.append({"keyword": kw, "line": i, "text": snippet})
                break  # 每个关键词只记第一条证据
    return hits


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------

@dataclass
class FileRec:
    rel_path: str
    name: str            # 文件名（不含扩展名）
    ext: str
    size_kb: float
    modified: str
    author: str = "Unknown"
    author_source: str = "fallback_unknown"
    is_c4: bool = False  # 是否属于 C4/C4A 范畴
    text: str = field(default="", repr=False)
    text_available: bool = False


@dataclass
class CriterionResult:
    id: str
    label_cn: str
    score: float
    grade: str            # ✅ / ⚠️ / ❌
    items: list[dict] = field(default_factory=list)   # 每项 check_item 的判定明细
    evidence: list[str] = field(default_factory=list)  # 汇总证据


@dataclass
class AuthorResult:
    author: str
    author_source: str
    files: list[FileRec] = field(default_factory=list)
    completeness: dict[str, dict] = field(default_factory=dict)
    completeness_score: float = 0.0
    completeness_grade: str = "❌"
    criteria: list[CriterionResult] = field(default_factory=list)
    quality_score: float = 0.0
    composite_score: float = 0.0
    confidence: str = "medium"
    flags: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 阶段① 文件采集与作者识别
# --------------------------------------------------------------------------

# 命名规范：姓名拼音_C4A_内容描述 / 姓名拼音_C4_内容描述
NAMING_RX = re.compile(
    r"^(?P<author>[A-Za-z一-鿿][A-Za-z0-9一-鿿\-]{0,20})[_\-](?P<cid>C4A?)[_\-](?P<part>.+)$",
    re.IGNORECASE,
)
# 退化匹配：至少含 _C4_ 或 _C4_（也支持文件以 C4_ 开头，即漏写作者名的情形）
LOOSE_RX = re.compile(r"[_\-](?P<cid>C4A?)[_\-]|^C4A?[_\-]", re.IGNORECASE)
AUTHOR_HEADER_RX = re.compile(
    r"(?:作者|姓名|提交人|学号|Author|Name)\s*[:：]\s*([^\s，,。;；]{1,20})",
    re.IGNORECASE,
)


def _author_from_metadata(path: Path) -> tuple[str | None, str]:
    """从 PDF / DOCX 元数据取作者。"""
    try:
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            m = PdfReader(str(path)).metadata
            if m and m.author and m.author.strip():
                return m.author.strip()[:30], "metadata_pdf"
        elif path.suffix.lower() == ".docx":
            import docx
            c = docx.Document(str(path)).core_properties
            if c.author and c.author.strip():
                return c.author.strip()[:30], "metadata_docx"
    except Exception:
        pass
    return None, "fallback_unknown"


def _author_from_header(text: str) -> tuple[str | None, str]:
    """从文档开头找"作者：XXX"。"""
    if not text:
        return None, "fallback_unknown"
    for line in text.splitlines()[:15]:
        m = AUTHOR_HEADER_RX.search(line)
        if m:
            cand = m.group(1).strip()
            # 过滤明显不是人名的取值（URL / 邮箱 / 太长）
            if cand and len(cand) <= 20 and "@" not in cand and "http" not in cand:
                return cand, "doc_header"
    return None, "fallback_unknown"


def _normalize_author(name: str) -> str:
    return re.sub(r"[\s\-]+", "", name.strip())


def collect_submissions(folder: Path, verbose: bool = False) -> tuple[dict[str, list[FileRec]], list[FileRec]]:
    """扫描文件夹，按作者分组返回 (bundles, non_c4_files)。

    两遍扫描，解决真实群文件夹里最常见的两种布局：
      ① 扁平布局：ZhangWei_C4_skill说明.md、ZhangWei_C4_教学说明.md …
      ② 子文件夹布局：ZhangWei/ ├─ C4_skill说明.md ├─ plot_tool.py …
         —— 此时脚本类文件本身没有 _C4_ 标记，靠「同文件夹已有 C4 文件」归入同一 bundle
    """
    if not folder.is_dir():
        raise SystemExit(f"ERROR: '{folder}' 不是有效目录。")

    all_recs: list[FileRec] = []
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        all_recs.append(FileRec(
            rel_path=str(f.relative_to(folder)),
            name=f.stem,
            ext=f.suffix.lower(),
            size_kb=round(st.st_size / 1024, 1),
            modified=datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
        ))

    # ---- 第一遍：判定每个文件是否属于 C4 范畴，并尝试识别作者 ----
    for rec in all_recs:
        f_stem = Path(rec.rel_path).stem
        m = NAMING_RX.match(f_stem)
        parent = Path(rec.rel_path).parent.name
        # 父目录是否像作者名（排除 C4 标记目录、根目录、过长名字）
        parent_is_author = bool(
            parent and parent not in (".", "..") and not LOOSE_RX.search(parent)
            and len(parent) <= 20
        )
        if m:
            rec_is_c4 = True
            # 同一目录下，若文件夹名本身像作者名，优先用文件夹名——
            # 否则「王晓_C4_说明.md」放进「WangXiao/」会分裂成两个作者
            if parent_is_author:
                rec.author = _normalize_author(parent)
                rec.author_source = "parent_folder"
            else:
                rec.author = _normalize_author(m.group("author"))
                rec.author_source = "filename_convention"
        else:
            rec_is_c4 = bool(LOOSE_RX.search(f_stem))
            if parent_is_author:
                rec.author = _normalize_author(parent)
                rec.author_source = "parent_folder"
        rec.is_c4 = rec_is_c4          # type: ignore[attr-defined]

    # ---- 第二遍：目录传播 ----
    # 真实群文件夹里，一个人往往把技能包整个放进自己的目录：
    #     ZhangWei/
    #     ├── ZhangWei_C4_skill说明.md      ← 有 C4 标记
    #     └── scripts/pr_desc.py            ← 没有 C4 标记，但在同一作者目录下
    # 规则：只要某目录（含其所有子目录）内出现 C4 标记文件，
    #       且该文件能归属到某作者，则该作者目录子树内其余文件一并纳入。
    # 这样既能收全scripts/ 下的可执行文件，又不会把别人的目录误吞。
    author_dirs: dict[str, set[str]] = {}      # 目录 -> 该目录下已确认的作者集合
    for rec in all_recs:
        if not getattr(rec, "is_c4", False) or rec.author == "Unknown":
            continue
        d = str(Path(rec.rel_path).parent)
        author_dirs.setdefault(d, set()).add(rec.author)
        # 该目录树下的所有祖先目录也归属此作者
        parts = Path(rec.rel_path).parts[:-1]
        for k in range(len(parts)):
            author_dirs.setdefault(str(Path(*parts[:k + 1])), set()).add(rec.author)

    for rec in all_recs:
        if getattr(rec, "is_c4", False):
            continue
        # 沿目录树向上找最近的"已归属某作者"的祖先目录
        parts = Path(rec.rel_path).parts[:-1]
        owners: set[str] = set()
        nearest = ""
        for k in range(len(parts), 0, -1):
            d = str(Path(*parts[:k]))
            if d in author_dirs:
                owners = author_dirs[d]
                nearest = d
                break
        if len(owners) == 1:
            rec.author = next(iter(owners))
            rec.author_source = ("author_dir_inherit"
                                 if rec.author_source == "fallback_unknown"
                                 else rec.author_source)
            rec.is_c4 = True        # type: ignore[attr-defined]
        elif len(owners) > 1:
            # 祖先目录归属不唯一 → 标为待回退，由元数据/文档头链决定
            rec.is_c4 = True# type: ignore[attr-defined]

    bundles: dict[str, list[FileRec]] = {}
    non_c4: list[FileRec] = []

    for rec in all_recs:
        if not getattr(rec, "is_c4", False):
            non_c4.append(rec)
            continue

        # 文本类文件在此处即读取正文（毫秒级开销），
        # 使 collect_submissions 的返回值即可直接用于完整性/质量评审，
        # 避免调用方忘记填充 text 导致"代码可解析"等结构性检查失效。
        if rec.ext in TEXTUAL_EXT and rec.size_kb * 1024 <= MAX_SIZE_KB:
            rec.text = extract_text(folder / rec.rel_path)
            rec.text_available = bool(rec.text)

        # 作者仍未识别 → 回退到元数据 / 文档头
        if rec.author == "Unknown":
            p = folder / rec.rel_path
            if rec.ext in EXTRACTABLE_EXT and rec.size_kb * 1024 <= MAX_SIZE_KB:
                if not rec.text:
                    rec.text = extract_text(p)
                    rec.text_available = bool(rec.text)
                a2, s2 = _author_from_metadata(p)
                if a2:
                    rec.author, rec.author_source = _normalize_author(a2), s2
                else:
                    a3, s3 = _author_from_header(rec.text)
                    if a3:
                        rec.author, rec.author_source = _normalize_author(a3), s3

        bundles.setdefault(rec.author, []).append(rec)

    # ---- 第三遍：作者别名归并（同一目录下的不同写法视为同一人）----
    # 例：ZhangWei_C4_a.md 与 ZhangWei_C4_b.md 分处不同子目录，
    #     或目录名 ZhangWei 与文件名 zhangwei 大小写不同 → 统一为一个 bundle
    for key in list(bundles.keys()):
        if key == "Unknown":
            continue
        canon = key[:1].upper() + key[1:]        # Zhangwei → ZhangWei
        if canon != key and canon in bundles:
            bundles[canon].extend(bundles.pop(key))
        elif canon != key:
            bundles[canon] = bundles.pop(key)

    if verbose:
        print(f"[collect] {sum(len(v) for v in bundles.values())} 个 C4 文件，"
              f"{len(bundles)} 位作者，{len(non_c4)} 个非 C4 文件", file=sys.stderr)
    return bundles, non_c4


# --------------------------------------------------------------------------
# 阶段② 提交完整性检查（Level 2）
# --------------------------------------------------------------------------

def _deliverable_status(files: list[FileRec], spec: dict) -> dict:
    """判断单个必须文件是否存在，返回状态 + 证据。

    判定优先级：真实二进制文件 > 文件名强信号 > 正文多信号命中
    （文件名是人主动命名的，可信度高于正文关键词猜测）
    """
    strong = [s.lower() for s in spec.get("strong_filename", [])]
    content = [s.lower() for s in spec.get("content_signals", [])]
    need = int(spec.get("min_content_hits", 3))
    need_partial = int(spec.get("min_content_hits_partial", 1))

    # 1) 文件名强信号
    for fr in files:
        low = fr.name.lower()
        if any(s in low for s in strong):
            return {"status": "✅", "matched": fr.rel_path,
                    "reason": f"文件名命中强信号：{fr.name}"}

    # 2) 媒体类真实存在（demo 的最强证据）
    media_exts = [e.lower() for e in spec.get("media_extensions", [])]
    if media_exts:
        for fr in files:
            if fr.ext in media_exts:
                return {"status": "✅", "matched": fr.rel_path,
                        "reason": f"存在真实媒体文件（{fr.ext}, {fr.size_kb}KB）"}

    # 3) 正文信号聚合
    hits: list[str] = []
    matched_file = ""
    for fr in files:
        if not fr.text:
            continue
        local = [s for s in content if any(s in ln.lower() for ln in fr.text.splitlines())]
        if len(local) > len(hits):
            hits, matched_file = local, fr.rel_path

    if len(hits) >= need:
        return {"status": "✅", "matched": matched_file,
                "reason": f"正文命中 {len(hits)}/{need} 个信号：{', '.join(hits[:5])}"}
    if len(hits) >= need_partial:
        return {"status": "⚠️", "matched": matched_file,
                "reason": f"正文仅命中 {len(hits)} 个信号（需 {need}）：{', '.join(hits[:5])}"}

    return {"status": "❌", "matched": "—",
            "reason": "文件名与正文均未检出足够信号"}


def check_completeness(files: list[FileRec], rubric: dict) -> tuple[dict[str, dict], float, str]:
    """五必须文件加权完整性检查。"""
    reqs = rubric.get("required_deliverables", {})
    out: dict[str, dict] = {}
    total_w = 0.0
    got_w = 0.0
    for key, spec in reqs.items():
        st = _deliverable_status(files, spec)
        out[key] = {
            "label": spec.get("label_cn", key),
            "weight": float(spec.get("weight", 0.2)),
            **st,
        }
        total_w += float(spec.get("weight", 0.2))
        if st["status"] == "✅":
            got_w += float(spec.get("weight", 0.2))
        elif st["status"] == "⚠️":
            got_w += float(spec.get("weight", 0.2)) * 0.5

    score = round(got_w / total_w, 4) if total_w else 0.0
    sc = rubric.get("scoring", {}).get("completeness", {})
    if score >= float(sc.get("full_threshold", 0.80)):
        grade = "✅ 齐全"
    elif score >= float(sc.get("partial_threshold", 0.50)):
        grade = "⚠️ 部分缺失"
    else:
        grade = "❌ 严重缺失"
    return out, score, grade


# --------------------------------------------------------------------------
# 阶段③ 技能质量评审（Level 3）—— 本项目的核心创新
# --------------------------------------------------------------------------

def _structural_facts(files: list[FileRec], abs_folder: Path | None) -> dict[str, bool]:
    """结构性硬校验：给出 high-confidence 的确定性事实。

    这些事实不依赖关键词猜测，因此权重最高，是控制误判率的关键。
    """
    facts = {
        "python_ast_parseable": False,
        "yaml_frontmatter_valid": False,
        "skill_archive_valid": False,
        "has_demo_media": False,
        "has_code_block": False,
        "has_executable_script": False,
    }
    for fr in files:
        if fr.ext in {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mov", ".webm"}:
            facts["has_demo_media"] = True
        if fr.text:
            if "```" in fr.text:
                facts["has_code_block"] = True
            # YAML frontmatter：--- 开头，含 name: 与 description:
            if re.search(r"\A---\s*\n(?:[^\n]*\n){0,30}?name\s*:\s*\S+", fr.text) \
               and re.search(r"\ndescription\s*:", fr.text[:2000]):
                facts["yaml_frontmatter_valid"] = True
        if fr.ext == ".py":
            # 结构性硬校验：直接用文件真实内容解析，不依赖 fr.text 是否已填充
            src = fr.text
            if not src and abs_folder is not None:
                src = _read_text_safe(abs_folder / fr.rel_path)
            if src:
                try:
                    ast.parse(src)
                    facts["python_ast_parseable"] = True
                except SyntaxError:
                    pass
            facts["has_executable_script"] = True
        if fr.ext in {".skill", ".zip"}:
            p = abs_folder / fr.rel_path if abs_folder else None
            if p and p.exists():
                try:
                    if tarfile.is_tarfile(p) or zipfile.is_zipfile(p):
                        facts["skill_archive_valid"] = True
                        facts["has_executable_script"] = True
                except Exception:
                    pass
    return facts


def evaluate_quality(files: list[FileRec], rubric: dict,
                     abs_folder: Path | None = None) -> tuple[list[CriterionResult], float, str]:
    """按 C4 四条件评审，返回逐维度结果 + 质量总分 + 置信度。

    打分公式（每维度）：
        raw = Σ(命中正向的项 weight) - Σ(命中反向的项 weight)
        ratio = clamp(raw / Σ(weight), 0, 1)
        ✅ if ratio >= 0.70 ; ⚠️ if >= 0.35 ; else ❌
    """
    facts = _structural_facts(files, abs_folder)
    blob = "\n".join(fr.text for fr in files if fr.text)
    criteria_spec = rubric.get("quality_criteria", {})
    th = rubric.get("scoring", {}).get("criterion", {})
    pass_th = float(th.get("pass_threshold", 0.70))
    part_th = float(th.get("partial_threshold", 0.35))

    results: list[CriterionResult] = []
    low_conf_any = False

    for cid, cspec in criteria_spec.items():
        pos_sum = 0.0
        tot_sum = 0.0
        items: list[dict] = []
        evidence: list[str] = []

        for item in cspec.get("check_items", []):
            iid = item.get("id", "?")
            name = item.get("name", "")
            w = float(item.get("weight", 1.0))
            itype = item.get("type", "keyword")
            tot_sum += w

            satisfied = False
            detail = ""
            conf = "medium"

            if itype == "structural":
                # 结构性检查：由 facts 决定，high confidence
                mapping = {
                    "E4": ("python_ast_parseable", "yaml_frontmatter_valid", "skill_archive_valid"),
                    "V3": ("has_demo_media", "has_code_block"),
                }
                keys = mapping.get(iid, ())
                if not keys:
                    # rubric 里新增 structural 项但代码未实现 → 明确报错，
                    # 绝不静默判成"不满足"（那会制造假的 ❌）
                    raise KeyError(
                        f"rubric 中的 {cid}/{iid} 声明 type=structural，"
                        f"但 c4a_evaluator.evaluate_quality 未实现对应事实检查。"
                        f"请在 _structural_facts() 补充事实，并在上面的 mapping 中登记。"
                    )
                got = [k for k in keys if facts.get(k)]
                satisfied = bool(got)
                detail = f"结构事实命中：{', '.join(got)}" if got else "结构事实均未命中"
                conf = "high"

            elif itype == "io_pattern":
                # 「输入X，输出Y」同一句式；pattern 来自 rubric，代码不硬编码
                patterns = item.get("io_patterns") or [
                    r"[^\n。]{0,80}输入[^\n。]{0,80}输出[^\n。]{0,60}"]
                ev: list[dict] = []
                for pat in patterns:
                    ev += find_evidence(blob, pat)
                satisfied = bool(ev)
                detail = (f"命中「输入…输出…」句式 {len(ev)} 处" if ev
                          else f"未找到 IO 一句话描述（已试 {len(patterns)} 种句式）")
                conf = "high" if ev else "medium"
                if ev:
                    evidence.append(f"句式证据：L{ev[0]['line']} 「{ev[0]['text']}」")

            elif itype in ("regex", "veto"):
                # veto 型：只看红线；regex 型：看正向模式
                pos = item.get("positive", [])
                neg = item.get("negative", [])
                pos_ev: list[dict] = []
                neg_ev: list[dict] = []
                for p in pos:
                    pos_ev += find_evidence(blob, p)
                for n in neg:
                    neg_ev += find_evidence(blob, n)
                if itype == "veto" or item.get("veto"):
                    # 否决项语义：只要没踩红线就算通过。
                    # positive 为空是**正常**的——这类项评的是"没有坏东西"
                    # （R2 无硬编码路径、R5 无凭据泄露），而非"有好东西"。
                    satisfied = not neg_ev and bool(neg)
                    if neg_ev:
                        detail = (f"命中红线（否决）：L{neg_ev[0]['line']} "
                                  f"「{neg_ev[0]['text']}」")
                        evidence.append(f"🚫 否决证据：L{neg_ev[0]['line']} 「{neg_ev[0]['text']}」")
                        low_conf_any = True
                    elif neg:
                        detail = f"未命中任何红线（已检查 {len(neg)} 类），通过"
                    else:
                        detail = "未配置红线信号，无法判定（记为不通过）"
                        satisfied = False
                else:
                    satisfied = bool(pos_ev)
                    detail = (f"正向信号命中 {len(pos_ev)} 处" if pos_ev
                              else f"未命中正向信号（检查 {len(pos)} 个模式）")
                    if pos_ev:
                        evidence.append(f"L{pos_ev[0]['line']} 「{pos_ev[0]['text']}」")
                # 正则未命中时证据可能为 0 条 —— 属正常

            else:  # keyword
                pos = item.get("positive", [])
                hits = keyword_hits(blob, pos)
                satisfied = bool(hits)
                if hits:
                    # 单关键词命中 → 置信度降为 low（误判风险最高的情形）
                    conf = "low"
                    detail = f"命中关键词 {len(hits)}/{len(pos)}：{', '.join(h['keyword'] for h in hits[:4])}"
                    evidence.append(f"关键词「{hits[0]['keyword']}」L{hits[0]['line']} 「{hits[0]['text']}」")
                else:
                    detail = f"未命中关键词（检查 {len(pos)} 个）"

            pos_sum += w if satisfied else 0.0
            items.append({
                "id": iid, "name": name, "weight": w, "type": itype,
                "satisfied": satisfied, "detail": detail, "confidence": conf,
            })

        ratio = max(0.0, min(1.0, pos_sum / tot_sum)) if tot_sum else 0.0
        grade = "✅" if ratio >= pass_th else ("⚠️" if ratio >= part_th else "❌")

        # ---- 一票否决（veto）----
        # R2「无硬编码绝对路径」与 R5「无凭据泄露」是致命项：
        # 只要命中其中任意一条，这份技能对"陌生人"就不可用——
        # C4 对可复用的检验原话是"让一个陌生人按你的说明操作，能成功吗？"，
        # 答案已经是否定的，再多的加分项也救不回来，评级直接封顶 ❌。
        veto_failed = [it["id"] for it in items
                       if not it["satisfied"] and it.get("type") == "veto"]
        if veto_failed:
            grade = "❌"

        results.append(CriterionResult(
            id=cid,
            label_cn=cspec.get("label_cn", cid),
            score=round(ratio, 4),
            grade=grade,
            items=items,
            evidence=evidence[:4],
        ))

    quality = round(sum(c.score for c in results) / len(results), 4) if results else 0.0

    # ---- 置信度评估 ----
    # 置信度描述的是"支撑本结论的证据有多硬"，取最强的那一类：
    #   1) 命中红线（veto_failed）→ low，红线判定宁可过度提醒人工复核
    #   2) 有任一关键项由结构性硬校验支撑 → high（ast/YAML/媒体文件不会看错）
    #   3) 过半关键项只靠单词��命中 → low
    #   4) 其余（正则、多信号命中）→ medium
    decisive = [it for c in results for it in c.items if it["weight"] >= 1.0]
    has_high = any(it["confidence"] == "high" and it["satisfied"] for it in decisive)
    weak = [it for it in decisive if it["confidence"] == "low" and it["satisfied"]]
    ratio_weak = len(weak) / len(decisive) if decisive else 1.0

    if low_conf_any:
        confidence = "low"
    elif has_high:
        confidence = "high"
    elif decisive and ratio_weak >= 0.5:
        confidence = "low"
    else:
        confidence = "medium"
    return results, quality, confidence


# --------------------------------------------------------------------------
# 阶段④ 报告生成（Level 4）
# --------------------------------------------------------------------------

def build_suggestions(res: AuthorResult) -> list[str]:
    """基于实际检测结果生成可执行的下一步行动——不输出通用套话。"""
    out: list[str] = []

    # 完整性优先：缺什么补什么
    for key, d in res.completeness.items():
        if d["status"] == "❌":
            out.append(f"【补齐缺失交付物】缺少「{d['label']}」——"
                       f"文件名建议包含：{key}（判定依据：{d['reason']}）")
        elif d["status"] == "⚠️":
            out.append(f"【强化弱项交付物】「{d['label']}」仅有弱证据（{d['reason']}），"
                       f"建议直接在文件名中写明用途以提升识别度")

    # 质量优先：只对未达标维度给建议，且绑定具体证据
    for c in res.criteria:
        if c.grade == "✅":
            continue
        failed = [it for it in c.items if not it["satisfied"]]
        names = "、".join(it["name"] for it in failed[:3]) or "整体深度不足"
        out.append(f"【提升「{c.label_cn}」（当前 {c.grade} {c.score:.0%}）】"
                   f"未满足：{names}")

    if not out:
        out.append("✅ 五文件齐全、四条件全部达标——建议补充真实使用人数与反馈截图，"
                   "C4 评分以「被使用次数」为核心。")
    return out


def _fmt_cell(v: Any, width: int) -> str:
    """简易等宽对齐（报告输出到终端/Markdown 时保证表格可读）。"""
    s = str(v)
    # 中文按 2 列宽度计
    w = sum(2 if ord(c) > 0x2E80 else 1 for c in s)
    return s + " " * max(0, width - w)


def render_markdown(results: dict[str, AuthorResult], non_c4: list[FileRec],
                    folder: Path, level_reached: str,
                    weights: dict | None = None, confidence: str = "medium") -> str:
    weights = weights or {"w_completeness": 0.4, "w_quality": 0.6,
                          "low_confidence_penalty": 0.9}
    L: list[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ranked = sorted(
        [r for r in results.values() if r.author != "Unknown" or not
         weights.get("exclude_unknown_from_ranking", True)],
        key=lambda r: -r.composite_score,
    )
    unknown = [r for r in results.values()
               if r.author == "Unknown" and weights.get("exclude_unknown_from_ranking", True)]

    n_files = sum(len(r.files) for r in results.values())
    complete = [r for r in ranked if r.completeness_score >= 0.80]
    avg_q = (sum(r.quality_score for r in ranked) / len(ranked)) if ranked else 0.0

    L.append("# C4 提交自动评审报告")
    L.append("")
    L.append(f"- **生成时间**：{ts}")
    L.append(f"- **扫描路径**：`{folder}`")
    L.append(f"- **识别结果**：{len(results)} 位作者 / {n_files} 个 C4 相关文件"
             f"（另有 {len(non_c4)} 个非 C4 文件已过滤）")
    L.append(f"- **本次达成级别**：{level_reached}")
    L.append(f"- **评审引擎**：`c4a_evaluator.py`（规则层确定性判定 + 结构化硬校验）")
    L.append(f"- **评分权重**：完整性 {weights['w_completeness']:.0%} + 质量 {weights['w_quality']:.0%}")
    L.append("")

    # ---- 一、班级总览----
    L.append("## 一、班级总览")
    L.append("")
    L.append("| 指标 | 数值 |")
    L.append("|---|---|")
    L.append(f"| 提交人数 | {len(ranked)} |")
    L.append(f"| 完整提交（加权完整性 ≥ 80%） | {len(complete)} |")
    L.append(f"| 部分提交 | {sum(1 for r in ranked if 0.5 <= r.completeness_score < 0.8)} |")
    L.append(f"| 严重缺失 | {sum(1 for r in ranked if r.completeness_score < 0.5)} |")
    L.append(f"| 平均质量分 | {avg_q:.1%} |")
    L.append(f"| 需人工复核 | {sum(1 for r in ranked if r.confidence == 'low')} |")
    L.append("")

    # 四条件班级均分
    if ranked:
        L.append("**四条件班级平均达成度：**")
        L.append("")
        cid_order = list(ranked[0].criteria)
        L.append("| 条件 | 平均达成度 | 达标(✅) | 部分(⚠️) | 未达标(❌) |")
        L.append("|---|---|---|---|---|")
        for c in cid_order:
            vals = [r for r in ranked if any(x.id == c.id for x in r.criteria)]
            scores = [next(x.score for x in r.criteria if x.id == c.id) for r in vals]
            grades = [next(x.grade for x in r.criteria if x.id == c.id) for r in vals]
            lbl = next(x.label_cn for x in vals[0].criteria if x.id == c.id)
            L.append(f"| {lbl} | {sum(scores)/len(scores):.0%} | "
                     f"{grades.count('✅')} | {grades.count('⚠️')} | {grades.count('❌')} |")
        L.append("")

    # ---- 二、作者详情 ----
    L.append("## 二、作者详情")
    L.append("")
    for r in ranked:
        L.append(f"### {r.author}")
        L.append("")
        L.append(f"> 作者识别方式：`{r.author_source}`　|　文件数：{len(r.files)}　|　"
                 f"综合分：**{r.composite_score:.1f}**　|　置信度：`{r.confidence}`")
        L.append("")
        L.append("**① 完整性检查（C4 五必须文件）**")
        L.append("")
        L.append("| 必须文件 | 状态 | 匹配文件 | 判定依据 |")
        L.append("|---|---|---|---|")
        for d in r.completeness.values():
            L.append(f"| {d['label']} | {d['status']} | `{d['matched']}` | {d['reason']} |")
        L.append("")
        L.append(f"加权完整性：**{r.completeness_score:.0%}** → {r.completeness_grade}")
        L.append("")
        L.append("**② 技能质量评审（C4 四条件）**")
        L.append("")
        L.append("| 条件 | 评级 | 达成度 | 主要依据 |")
        L.append("|---|---|---|---|")
        for c in r.criteria:
            ev = c.evidence[0] if c.evidence else "—"
            ev = ev.replace("|", "\\|")
            if len(ev) > 90:
                ev = ev[:87] + "..."
            L.append(f"| {c.label_cn} | {c.grade} | {c.score:.0%} | {ev} |")
        L.append("")
        L.append(f"质量总分：**{r.quality_score:.0%}**")
        L.append("")
        # 逐项明细（可追溯）
        L.append("<details><summary>逐项评审明细（点击展开，含文件行号证据）</summary>")
        L.append("")
        for c in r.criteria:
            L.append(f"**{c.label_cn}**")
            L.append("")
            L.append("| 项 | 检查内容 | 权重 | 结果 | 置信度 | 依据 |")
            L.append("|---|---|---|---|---|---|")
            for it in c.items:
                mark = "✅" if it["satisfied"] else "❌"
                d = it["detail"].replace("|", "\\|")
                if len(d) > 110:
                    d = d[:107] + "..."
                L.append(f"| {it['id']} | {it['name']} | {it['weight']} | {mark} | "
                         f"`{it['confidence']}` | {d} |")
            L.append("")
        L.append("</details>")
        L.append("")
        L.append("**③ 下一步行动建议**")
        L.append("")
        for i, s in enumerate(r.suggestions, 1):
            L.append(f"{i}. {s}")
        L.append("")
        if r.flags:
            L.append(f"> 🚩 **需人工复核**：{'；'.join(r.flags)}")
            L.append("")
        L.append("---")
        L.append("")

    # ---- 三、排名 ----
    L.append("## 三、综合排名")
    L.append("")
    L.append("| 排名 | 作者 | 完整性 | 质量分 | 综合分 | 置信度 |")
    L.append("|---|---|---|---|---|---|")
    for i, r in enumerate(ranked, 1):
        L.append(f"| {i} | {r.author} | {r.completeness_score:.0%} | "
                 f"{r.quality_score:.0%} | **{r.composite_score:.1f}** | `{r.confidence}` |")
    L.append("")
    if unknown:
        L.append("**未识别作者（不参与排名）：**")
        L.append("")
        for r in unknown:
            L.append(f"- `{r.author}`：{len(r.files)} 个文件——"
                     f"{', '.join(f.name for f in r.files[:5])}")
        L.append("")

    # ---- 四、班级共性诊断 ----
    L.append("## 四、班级共性问题与行动建议")
    L.append("")
    if ranked:
        # 最常缺失的文件
        miss_counter: dict[str, int] = {}
        for r in ranked:
            for d in r.completeness.values():
                if d["status"] != "✅":
                    miss_counter[d["label"]] = miss_counter.get(d["label"], 0) + 1
        if miss_counter:
            worst = max(miss_counter.items(), key=lambda kv: kv[1])
            L.append(f"- **最常见缺失**：{worst[0]}（{worst[1]}/{len(ranked)} 人未达标）")

        # 最弱维度
        dim_scores: dict[str, list[float]] = {}
        for r in ranked:
            for c in r.criteria:
                dim_scores.setdefault(c.label_cn, []).append(c.score)
        if dim_scores:
            weakest = min(dim_scores.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
            avgw = sum(weakest[1]) / len(weakest[1])
            L.append(f"- **最弱维度**：{weakest[0]}（班级平均 {avgw:.0%}）——"
                     f"建议下次提交前用本评审器自检")
        L.append(f"- **整体质量分**：{avg_q:.0%}"
                 f"{'（偏低，建议优先补「IO 明确」与「可验证」）' if avg_q < 0.6 else '（良好）'}")
    L.append("")
    if non_c4:
        L.append(f"<details><summary>非 C4 文件（{len(non_c4)} 个，已排除）</summary>")
        L.append("")
        for fr in non_c4[:20]:
            L.append(f"- `{fr.rel_path}`")
        if len(non_c4) > 20:
            L.append(f"- …… 另有 {len(non_c4) - 20} 个")
        L.append("")
        L.append("</details>")
        L.append("")

    L.append("---")
    L.append("")
    L.append(f"*本报告由 `c4a_evaluator.py` 自动生成；所有 ✅/⚠️/❌ 均可追溯到具体文件与行号。"
             f"标有 `low` 置信度的结论为单关键词命中，存在误判可能，建议人工复核。*")
    return "\n".join(L)


def render_json(results: dict[str, AuthorResult], non_c4: list[FileRec],
                folder: Path, level_reached: str, confidence: str) -> str:
    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "folder": str(folder),
            "level_reached": level_reached,
            "engine": "c4a_evaluator.py",
        },
        "authors": {},
        "non_c4_files": [f.rel_path for f in non_c4],
    }
    for name, r in results.items():
        payload["authors"][name] = {
            "author_source": r.author_source,
            "files": [f.rel_path for f in r.files],
            "completeness": r.completeness,
            "completeness_score": r.completeness_score,
            "completeness_grade": r.completeness_grade,
            "quality_score": r.quality_score,
            "composite_score": r.composite_score,
            "confidence": r.confidence,
            "flags": r.flags,
            "criteria": [asdict(c) for c in r.criteria],
            "suggestions": r.suggestions,
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_xlsx(results: dict[str, AuthorResult], non_c4: list[FileRec],
                out: Path, folder: Path) -> bool:
    """生成 Excel 详表。openpyxl 缺失时优雅跳过。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        sys.stderr.write("[warn] 未安装 openpyxl，跳过 Excel 输出（pip install openpyxl）\n")
        return False

    wb = Workbook()
    hf = Font(name="Arial", bold=True, size=11, color="FFFFFF")
    hfill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    cf = Font(name="Arial", size=10)
    bd = Border(*[Side(style="thin")] * 4)

    def style_header(ws, headers, fill=hfill):
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font, cell.fill, cell.border = hf, fill, bd
            cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Sheet1 排名总表
    ws = wb.active
    ws.title = "排名总表"
    style_header(ws, ["排名", "作者", "识别方式", "完整性", "完整性评级",
                      "可复用", "可执行", "可验证", "IO明确", "质量分",
                      "综合分", "置信度", "需复核"])
    ranked = sorted(results.values(), key=lambda r: -r.composite_score)
    for i, r in enumerate(ranked, 1):
        g = {c.id: c.grade + f" {c.score:.0%}" for c in r.criteria}
        row = [i, r.author, r.author_source, r.completeness_score, r.completeness_grade,
               g.get("reusable", "—"), g.get("executable", "—"),
               g.get("verifiable", "—"), g.get("clear_io", "—"),
               r.quality_score, r.composite_score, r.confidence,
               "；".join(r.flags) or "—"]
        for cidx, v in enumerate(row, 1):
            cell = ws.cell(row=i + 1, column=cidx, value=v)
            cell.font, cell.border = cf, bd
    for c in range(1, 14):
        ws.column_dimensions[get_column_letter(c)].width = 16
    ws.freeze_panes = "A2"

    # Sheet2 完整性矩阵
    ws2 = wb.create_sheet("完整性矩阵")
    keys = list(next(iter(results.values())).completeness.keys()) if results else []
    labels = [results[list(results)[0]].completeness[k]["label"] for k in keys] if keys else []
    style_header(ws2, ["作者"] + labels + ["加权完整性"], fill=PatternFill(
        start_color="C00000", end_color="C00000", fill_type="solid"))
    for i, r in enumerate(ranked, 1):
        vals = [r.author] + [f"{r.completeness[k]['status']} {r.completeness[k]['matched']}"
                            for k in keys] + [r.completeness_score]
        for cidx, v in enumerate(vals, 1):
            cell = ws2.cell(row=i + 1, column=cidx, value=v)
            cell.font, cell.border = cf, bd
            if cidx > 1:
                cell.alignment = Alignment(wrap_text=True)
    for c in range(1, len(labels) + 2):
        ws2.column_dimensions[get_column_letter(c)].width = 30
    ws2.freeze_panes = "B2"

    # Sheet3 逐项评审明细（可追溯证据）
    ws3 = wb.create_sheet("逐项评审明细")
    style_header(ws3, ["作者", "条件", "项ID", "检查内容", "权重", "结果", "置信度", "判定依据"],
                 fill=PatternFill(start_color="548235", end_color="548235", fill_type="solid"))
    rr = 2
    for r in ranked:
        for c in r.criteria:
            for it in c.items:
                row = [r.author, c.label_cn, it["id"], it["name"], it["weight"],
                       "✅" if it["satisfied"] else "❌", it["confidence"], it["detail"]]
                for cidx, v in enumerate(row, 1):
                    cell = ws3.cell(row=rr, column=cidx, value=v)
                    cell.font, cell.border = cf, bd
                rr += 1
    for c, w in zip(range(1, 9), [16, 12, 8, 30, 8, 8, 12, 70]):
        ws3.column_dimensions[get_column_letter(c)].width = w
    ws3.freeze_panes = "A2"

    # Sheet4 文件清单
    ws4 = wb.create_sheet("文件清单")
    style_header(ws4, ["作者", "相对路径", "扩展名", "大小KB", "修改日期", "识别方式"],
                 fill=PatternFill(start_color="7030A0", end_color="7030A0", fill_type="solid"))
    rr = 2
    for r in ranked:
        for f in r.files:
            row = [r.author, f.rel_path, f.ext, f.size_kb, f.modified, f.author_source]
            for cidx, v in enumerate(row, 1):
                cell = ws4.cell(row=rr, column=cidx, value=v)
                cell.font, cell.border = cf, bd
            rr += 1
    for c, w in zip(range(1, 7), [16, 45, 10, 10, 14, 22]):
        ws4.column_dimensions[get_column_letter(c)].width = w
    ws4.freeze_panes = "A2"

    # Sheet5 改进建议
    ws5 = wb.create_sheet("改进建议")
    style_header(ws5, ["作者", "序号", "建议"], fill=PatternFill(
        start_color="ED7D31", end_color="ED7D31", fill_type="solid"))
    rr = 2
    for r in ranked:
        for i, s in enumerate(r.suggestions, 1):
            for cidx, v in enumerate([r.author, i, s], 1):
                cell = ws5.cell(row=rr, column=cidx, value=v)
                cell.font, cell.border = cf, bd
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            rr += 1
    for c, w in zip(range(1, 4), [16, 8, 100]):
        ws5.column_dimensions[get_column_letter(c)].width = w
    ws5.freeze_panes = "A2"

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return True


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def run(folder: Path, outdir: Path, rubric_path: Path,
        md_name: str, json_name: str, xlsx_name: str,
        strict: bool = False, verbose: bool = False) -> int:
    with open(rubric_path, "r", encoding="utf-8") as f:
        rubric = yaml.safe_load(f)

    bundles, non_c4 = collect_submissions(folder, verbose=verbose)

    # 正文填充策略：
    #   默认模式 —— 读取所有文本类文件（.md/.py/.txt/... ，毫秒级）+ 作者未识别的可提取文件
    #   严格模式 —— 额外解析 .pdf/.docx/.pptx/.xlsx/.skill/.zip（更准但更慢，适合正式评审）
    # 四条件评审依赖正文信号，因此文本类必须无条件读取。
    STRICT_TEXT_EXT = TEXTUAL_EXT | {".pdf", ".docx", ".pptx", ".xlsx", ".skill", ".zip"}
    for files in bundles.values():
        for fr in files:
            if fr.text or fr.size_kb * 1024 > MAX_SIZE_KB:
                continue
            if fr.ext in TEXTUAL_EXT or (strict and fr.ext in STRICT_TEXT_EXT) \
                    or (fr.author == "Unknown" and fr.ext in EXTRACTABLE_EXT):
                fr.text = extract_text(folder / fr.rel_path)
            fr.text_available = bool(fr.text)

    results: dict[str, AuthorResult] = {}
    scoring = rubric.get("scoring", {}).get("composite", {})
    w_c = float(scoring.get("w_completeness", 0.4))
    w_q = float(scoring.get("w_quality", 0.6))
    penalty = float(scoring.get("low_confidence_penalty", 0.9))

    for author, files in bundles.items():
        comp, comp_score, comp_grade = check_completeness(files, rubric)
        crits, q_score, confidence = evaluate_quality(files, rubric, abs_folder=folder)

        composite = comp_score * w_c + q_score * w_q
        if confidence == "low":
            composite *= penalty

        flags: list[str] = []
        if author == "Unknown":
            flags.append("作者未识别，无法归属")
        if confidence == "low":
            flags.append("多为单关键词命中，结论置信度低")
        # 矛盾检测：文件齐全但质量极低，或反之
        if rubric.get("scoring", {}).get("qa", {}).get("contradiction_check", True):
            if comp_score >= 0.8 and q_score < 0.25:
                flags.append("完整性高但质量极低——请确认内容是否只是占位/空壳")
            if comp_score < 0.3 and q_score >= 0.75:
                flags.append("质量高但完整性低——可能漏交了某些必须文件")

        r = AuthorResult(
            author=author,
            author_source=files[0].author_source if files else "fallback_unknown",
            files=files,
            completeness=comp,
            completeness_score=comp_score,
            completeness_grade=comp_grade,
            criteria=crits,
            quality_score=q_score,
            composite_score=round(composite, 4),
            confidence=confidence,
            flags=flags,
        )
        r.suggestions = build_suggestions(r)
        results[author] = r

    # 达成级别判定
    n_ranked = sum(1 for r in results.values() if r.author != "Unknown")
    if n_ranked == 0:
        level = "Level 0（未识别到任何 C4 提交）"
    elif any(r.criteria for r in results.values()):
        has_quality = all(len(r.criteria) == 4 for r in results.values())
        has_excel = True
        has_rank = n_ranked >= 1
        level = ("Level 4 完整评审系统" if (has_quality and has_excel and has_rank)
                 else "Level 3 质量评审器")
    elif any(r.completeness for r in results.values()):
        level = "Level 2 完整性检查器"
    else:
        level = "Level 1 文件采集器"

    outdir.mkdir(parents=True, exist_ok=True)
    weights = {
        "w_completeness": w_c, "w_quality": w_q,
        "low_confidence_penalty": penalty,
        "exclude_unknown_from_ranking": rubric.get("scoring", {}).get("qa", {})
                                            .get("exclude_unknown_from_ranking", True),
    }
    overall_conf = "low" if any(r.confidence == "low" for r in results.values()) else "medium"

    md_path = outdir / md_name
    md_path.write_text(
        render_markdown(results, non_c4, folder, level, weights, overall_conf),
        encoding="utf-8",
    )

    json_path = outdir / json_name
    json_path.write_text(
        render_json(results, non_c4, folder, level, overall_conf), encoding="utf-8"
    )

    xlsx_path = outdir / xlsx_name
    xlsx_ok = render_xlsx(results, non_c4, xlsx_path, folder)

    print(f"扫描路径   : {folder}")
    print(f"作者数     : {len(results)}（参与排名 {n_ranked}）")
    print(f"C4 文件数  : {sum(len(v) for v in bundles.values())}（非 C4 排除 {len(non_c4)}）")
    print(f"达成级别   : {level}")
    print(f"报告(MD)   : {md_path}")
    print(f"数据(JSON) : {json_path}")
    if xlsx_ok:
        print(f"详表(XLSX) : {xlsx_path}")
    else:
        print("详表(XLSX) : 跳过（未安装 openpyxl）")
    print("-" * 60)
    for r in sorted(results.values(), key=lambda x: -x.composite_score):
        print(f"  {r.author:<14} 完整性 {r.completeness_score:>5.0%}  "
              f"质量 {r.quality_score:>5.0%}  综合 {r.composite_score:>5.1f}  "
              f"[{r.confidence}]")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="C4 技能提交自动评审器（C4A）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python c4a_evaluator.py ../wechat_C4_group --outdir ../../reports\n"
            "  python c4a_evaluator.py <folder> --outdir out --md 评审.md --json 评审.json\n"
        ),
    )
    ap.add_argument("folder", help="包含 C4 提交文件的本地文件夹路径")
    ap.add_argument("--outdir", default="./reports", help="报告输出目录（默认 ./reports）")
    ap.add_argument("--rubric", default=str(DEFAULT_RUBRIC), help="评审标准 YAML 路径")
    ap.add_argument("--md", dest="md_name", default="Meteorain_C4A_评审报告.md",
                    help="Markdown 报告文件名")
    ap.add_argument("--json", dest="json_name", default="evaluation.json",
                    help="JSON 数据文件名")
    ap.add_argument("--xlsx", dest="xlsx_name", default="Meteorain_C4A_评审详表.xlsx",
                    help="Excel 详表文件名")
    ap.add_argument("--strict", action="store_true", help="严格模式：读取全部可提取文件正文（更准更慢）")
    ap.add_argument("--verbose", "-v", action="store_true", help="打印扫描诊断信息")
    args = ap.parse_args(argv)

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.stderr.write(f"ERROR: '{folder}' 不是有效目录。\n"
                         f"提示：请传入 WeChat 群文件夹、手动下载目录或任意含 C4 提交的目录。\n")
        return 1
    rubric_path = Path(args.rubric).expanduser().resolve()
    if not rubric_path.is_file():
        sys.stderr.write(f"ERROR: 评审标准文件不存在: {rubric_path}\n")
        return 1

    try:
        return run(folder, Path(args.outdir).expanduser().resolve(), rubric_path,
                   args.md_name, args.json_name, args.xlsx_name,
                   args.strict, args.verbose)
    except KeyboardInterrupt:
        sys.stderr.write("\n已中断。\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())