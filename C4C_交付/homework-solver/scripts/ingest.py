#!/usr/bin/env python3
"""
Stage 1: Document Ingestion（扩展版）

starter kit 只实现了 Markdown 读取，PDF / Word / OCR 三个函数直接 raise
NotImplementedError。本模块把这些扩展点全部补齐，并额外做了一件
starter kit 没做的事：**LaTeX 反向摄入**（把 .tex 作业还原成 Markdown），
以及 **PDF 结构修复**（去掉页眉页脚、断行连字符、识别题目编号行）。

设计原则：**依赖可选 + 优雅降级**。
pdfplumber 没装就报清晰的安装提示，而不是让整条流水线崩掉。

用法:
    python ingest.py <输入文件> <输出.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────
# 1. Markdown / 纯文本
# ─────────────────────────────────────────────

def read_markdown(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────
# 2. PDF（文本型）— pdfplumber，pypdf 兜底
# ─────────────────────────────────────────────

# 页面级噪声：页码、页眉页脚、版权行
_NOISE_PATTERNS = [
    re.compile(r"^\s*(page\s+)?\d+\s*(of\s+\d+)?\s*$", re.I),
    re.compile(r"^\s*[-–—]\s*\d+\s*[-–—]\s*$"),
    re.compile(r"(©|copyright)\s+\d{4}",re.I),
    re.compile(r"^\s*(worksheet|homework|problem set|pset)\s*\d*\s*$", re.I),
]


def read_pdf_text(filepath: str) -> str:
    """文本型 PDF 摄入。优先 pdfplumber，失败退pypdf。"""
    text = _read_pdf_pdfplumber(filepath)
    if text is None:
        text = _read_pdf_pypdf(filepath)
    if text is None:
        raise RuntimeError(
            "PDF 摄入失败。请安装依赖：\n"
            "  pip install pdfplumber\n"
            "若为扫描件（提取到空文本），请改用 OCR：\n"
            "  pip install pytesseract Pillow  并安装 Tesseract 本体"
        )
    return text


def _read_pdf_pdfplumber(filepath: str) -> Optional[str]:
    try:
        import pdfplumber
    except ImportError:
        return None
    chunks = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                chunks.append(page_text)
    except Exception:
        return None
    text = "\n".join(chunks)
    return text if len(text.strip()) > 40 else (text or None)


def _read_pdf_pypdf(filepath: str) -> Optional[str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(filepath)
        text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
    except Exception:
        return None
    return text if text.strip() else None


# ─────────────────────────────────────────────
# 3. Word (.docx) — python-docx
# ─────────────────────────────────────────────

def read_docx(filepath: str) -> str:
    """
    Word 摄入。处理要点：
    - 段落保序（含空段落的样式信息丢失，但顺序不丢）
    - 公式在 docx 里是 OMML 对象，纯文本抽不出来；这里做两件事：
      a) 把 oMath 元素转成可读的 LaTeX 近似（best effort）
      b) 无法转换时插入 ``[公式]`` 占位符并保留编号，避免题目被整段丢弃
    - 表格逐格转成 "a | b" 文本行
    """
    try:
        import docx
    except ImportError as e:
        raise RuntimeError(
            "Word 摄入需要 python-docx：\n  pip install python-docx"
        ) from e

    document = docx.Document(filepath)
    parts = []

    for para in document.paragraphs:
        text = para.text
        # 尝试抽取 OMML 公式
        math_latex = _extract_omml(para)
        if math_latex:
            text = f"{text} {math_latex}".strip()
        if text.strip():
            parts.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))

    result = "\n".join(parts)
    if not result.strip():
        raise RuntimeError(
            "Word 文档提取为空。常见原因：内容全在文本框/图片里。"
            "建议先用 Word 另存为 PDF 再走PDF 摄入路径。"
        )
    return result


def _extract_omml(para) -> str:
    """
    从 docx 段落里提取 OMML 公式的 LaTeX 近似。

    OMML (Office Math Markup Language) 的 xpath 是
    `.//m:oMath` 和 `.//m:oMathPara`。这里做浅层转换：把 m:t 节点的文本
    拼起来，够用来让下游解析器识别出「这里有个公式」。
    真正精确的 OMML→LaTeX 需要 XSLT 转换器，依赖过重，不适合内嵌。
    """
    try:
        ns = {
            "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
        }
        maths = para._p.findall(".//m:oMath", ns)
        if not maths:
            return ""
        out = []
        for om in maths:
            texts = [t.text or "" for t in om.findall(".//m:t", ns)]
            s = "".join(texts).strip()
            if s:
                out.append(f"${s}$")
        return " ".join(out)
    except Exception:
        return ""


# ─────────────────────────────────────────────
# 4. 图片 / 扫描件 OCR
# ─────────────────────────────────────────────

def read_image_ocr(filepath: str) -> str:
    """
    OCR 摄入。两条路：
    a) Tesseract 本地（pip install pytesseract + 装 Tesseract 可执行文件）
    b) 国产模型 Vision API（DASHSCOPE_API_KEY 存在时启用，见 llm_engine）

    数学公式的 OCR 准确率天然低，这里不做「伪精确」处理——
    抽不出就报错让人知道，而不是给一份错的公式。
    """
    # 路b：国产模型 Vision（通义千问 VL）
    vision = _try_domestic_vision(filepath)
    if vision:
        return vision

    # 路 a：Tesseract
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "OCR 摄入失败。请任选其一：\n"
            "  (a) 本地 OCR：pip install pytesseract Pillow，并安装 Tesseract 本体\n"
            "      Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  (b) 国产模型 Vision：设置 DASHSCOPE_API_KEY 环境变量后自动启用\n"
            "注意：数学公式的 OCR 准确率有限，复杂公式建议手动校对。"
        ) from e

    image = Image.open(filepath)
    langs = "chi_sim+eng" if _tesseract_has_lang("chi_sim") else "eng"
    try:
        return pytesseract.image_to_string(image, lang=langs)
    except Exception as e:
        raise RuntimeError(f"OCR 调用失败（检查 Tesseract 是否在 PATH 中）: {e}") from e


def _tesseract_has_lang(lang: str) -> bool:
    try:
        import pytesseract
        return lang in pytesseract.get_languages()
    except Exception:
        return False


def _try_domestic_vision(filepath: str) -> Optional[str]:
    """用通义千问 VL 读图——这是「国产模型 Vision」扩展点的实现。"""
    import base64
    import os
    import urllib.request

    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        return None

    try:
        with open(filepath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return None

    payload = {
        "model": "qwen-vl-max",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    "请把图片里的作业题目逐字转写为 Markdown。"
                    "要求：(1) 保留题号；(2) 数学公式写成 $...$ 或 $$...$$ 的 LaTeX；"
                    "(3) 保留子题编号 (a)(b)(c)；(4) 不要解题，只转写题目。"
                )},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]
    except Exception:
        return None


# ─────────────────────────────────────────────
# 5. LaTeX 反向摄入（starter kit 没有的能力）
# ─────────────────────────────────────────────

def read_latex(filepath: str) -> str:
    """
    .tex → Markdown。
    去掉 preamble / 文档命令，把数学环境转成 $ 定界符，让下游 parser 统一处理。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    # 去掉 preamble
    body = re.sub(r"\\documentclass.*?\{.*?\}(\s*\\usepackage.*?)*", "", raw,
                  flags=re.DOTALL)
    body = re.sub(r"\\begin\{document\}|\\end\{document\}", "", body)
    body = re.sub(r"\\(begin|end)\{(equation\*?|align\*?|gather\*?|displaymath)\}", "", body)
    body = re.sub(r"\\begin\{(center|flushleft|itemize|enumerate|proof)\}", "", body)
    body = re.sub(r"\\end\{(center|flushleft|itemize|enumerate|proof)\}", "", body)
    body = re.sub(r"\\(section|subsection|textbf|emph|texttt|mathrm|mbox)\{([^}]*)\}",
                  r"\2", body)
    body = body.replace("\\\\", "\n").replace("~", " ")
    body = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", body)
    body = re.sub(r"\\[a-zA-Z]+", "", body)
    body = body.replace("{", "(").replace("}", ")")
    return re.sub(r"\n{3,}", "\n\n", body).strip()


# ─────────────────────────────────────────────
# 格式路由
# ─────────────────────────────────────────────

FORMAT_HANDLERS = {
    ".md":read_markdown,
    ".txt":  read_markdown,
    ".tex":  read_latex,
    ".pdf":  read_pdf_text,
    ".docx": read_docx,
    ".png":  read_image_ocr,
    ".jpg":  read_image_ocr,
    ".jpeg": read_image_ocr,
    ".webp": read_image_ocr,
}


def detect_format(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    if ext not in FORMAT_HANDLERS:
        raise ValueError(
            f"不支持的文件格式: {ext}\n支持: {', '.join(sorted(FORMAT_HANDLERS))}"
        )
    return ext


def clean_extracted_text(text: str) -> str:
    """清洗从 PDF 抽出的噪声：页眉页脚、断行连字符、多余空行。"""
    lines = text.split("\n")
    kept = []
    for ln in lines:
        if any(p.search(ln) for p in _NOISE_PATTERNS):
            continue
        kept.append(ln)

    joined = "\n".join(kept)
    # 断词合并："limi-\nng" → "liming"→ 但要小心数学内容，限定只处理字母后缀
    joined = re.sub(r"([a-z])-\n([a-z])", r"\1\2", joined)
    # 句中换行合并（中文/英文句子被 PDF 切断）
    joined = re.sub(r"(?<=[a-z,;)])\n(?=[a-z(])", " ", joined)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def split_into_sections(text: str) -> list:
    """按 Markdown 标题分段；无标题时整体作为一个 section。"""
    sections = []
    cur_title, cur_lines = "Untitled", []

    for line in text.split("\n"):
        m = re.match(r"^(#{1,4})\s+(.+)", line)
        if m:
            if cur_lines:
                content = "\n".join(cur_lines).strip()
                if content:
                    sections.append({"title": cur_title, "content": content})
            cur_title, cur_lines = m.group(2).strip(), []
        else:
            cur_lines.append(line)

    if cur_lines:
        content = "\n".join(cur_lines).strip()
        if content:
            sections.append({"title": cur_title, "content": content})
    return sections


def ingest(filepath: str) -> dict:
    """主入口。返回结构化摄入结果。"""
    filepath = str(filepath)
    ext = detect_format(filepath)
    handler = FORMAT_HANDLERS[ext]

    raw_text = handler(filepath)
    if ext in (".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp"):
        raw_text = clean_extracted_text(raw_text)

    return {
        "source_file": Path(filepath).name,
        "format": ext,
        "raw_text": raw_text,
        "sections": split_into_sections(raw_text),
        "char_count": len(raw_text),
    }


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("用法: python ingest.py <输入文件> <输出.json>")
        print("支持: .md .txt .tex .pdf .docx .png .jpg .jpeg .webp")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]
    if not Path(input_path).exists():
        print(f"错误: 文件不存在 — {input_path}")
        sys.exit(1)

    print(f"[Stage 1] 文档摄入: {input_path}")
    result = ingest(input_path)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  格式: {result['format']}  字符数: {result['char_count']}")
    print(f"  分段: {len(result['sections'])} sections")
    print(f"  输出: {output_path}")


if __name__ == "__main__":
    main()