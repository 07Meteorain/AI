#!/usr/bin/env python3
"""
wechat_publisher.py — Markdown/Word -> WeChat Official Account HTML

Derived from the C4B starter kit (scripts/convert_to_wechat.py).
Fixes two defects found in the starter kit baseline:
  BUG-1  code blocks lost their line breaks (indentation destroyed)
  BUG-2  blockquote lost all inline formatting (bold / code flattened to text)

New capabilities added on top of the starter kit:
  1. Theme system   --theme {default,accent,minimal,solo,dark}
  2. Callout boxes  > [!NOTE]/[!TIP]/[!WARNING]/[!IMPORTANT]/[!CAUTION]/[!QUOTE]
  3. Auto TOC       --toc
  4. Metadata block --title/--author/--date/--abstract  (or YAML front matter)
  5. Footer         --footer/--footer-copyright
  6. Chinese typography polish  --zh-spacing / --no-zh-spacing
  7. Batch mode     a directory as input converts every .md inside it

Usage
  python wechat_publisher.py input.md output.html [options]
  python wechat_publisher.py ./posts/ ./out/ --theme accent --toc --batch
  python wechat_publisher.py report.docx report.html
"""

import argparse
import html as html_lib
import os
import re
import sys
import unicodedata
from pathlib import Path

# --- dependency bootstrap -------------------------------------------------
def _ensure_deps():
    missing = []
    for mod, pkg in (("markdown", "markdown"),
                      ("bs4", "beautifulsoup4"),
                      ("docx", "python-docx"),
                      ("lxml", "lxml")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        import subprocess
        print("Installing missing packages: %s" % ", ".join(missing))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing,
             "--break-system-packages", "-q"])

_ensure_deps()

import markdown
from bs4 import BeautifulSoup, NavigableString

# ============================================================
# THEME SYSTEM  (new capability #1)
# ============================================================

THEMES = {
    "default": {
        "label": "经典灰",
        "accent": "#576b95",
        "heading": "#3f3f3f",
        "heading_bar": "#576b95",
        "text": "#3f3f3f",
        "muted": "#9a9a9a",
        "code_bg": "#f7f8fa",
        "code_fg": "#c7254e",
        "quote_bar": "#d0d0d0",
        "quote_bg": "#fafafa",
        "th_bg": "#f2f3f5",
        "link": "#576b95",
        "divider": "#e8e8e8",
    },
    "accent": {
        "label": "学术蓝",
        "accent": "#1a73e8",
        "heading": "#0b57a4",
        "heading_bar": "#1a73e8",
        "text": "#202124",
        "muted": "#80868b",
        "code_bg": "#f0f7ff",
        "code_fg": "#d6336c",
        "quote_bar": "#1a73e8",
        "quote_bg": "#f0f7ff",
        "th_bg": "#e8f1fd",
        "link": "#1a73e8",
        "divider": "#d6e6fb",
    },
    "minimal": {
        "label": "极简黑",
        "accent": "#333333",
        "heading": "#111111",
        "heading_bar": "#111111",
        "text": "#2b2b2b",
        "muted": "#999999",
        "code_bg": "#fbfbfb",
        "code_fg": "#b02a37",
        "quote_bar": "#999999",
        "quote_bg": "#fcfcfc",
        "th_bg": "#f5f5f5",
        "link": "#333333",
        "divider": "#e5e5e5",
    },
    "solo": {
        "label": "暖橙",
        "accent": "#e65100",
        "heading": "#bf360c",
        "heading_bar": "#e65100",
        "text": "#3e2723",
        "muted": "#a1887f",
        "code_bg": "#fff8e1",
        "code_fg": "#c62828",
        "quote_bar": "#ff9800",
        "quote_bg": "#fff8e1",
        "th_bg": "#fff3e0",
        "link": "#e65100",
        "divider": "#ffe0b2",
    },
    "dark": {
        "label": "夜间黑",
        "accent": "#4fc3f7",
        "heading": "#e0e0e0",
        "heading_bar": "#4fc3f7",
        "text": "#d0d0d0",
        "muted": "#8a8a8a",
        "code_bg": "#2a2a2a",
        "code_fg": "#ff8a80",
        "quote_bar": "#4fc3f7",
        "quote_bg": "#263238",
        "th_bg": "#333333",
        "link": "#4fc3f7",
        "divider": "#3a3a3a",
    },
}

# Callout kinds -> (emoji, label)   (new capability #2)
CALLOUTS = {
    "NOTE":      ("\U0001F4D6", "笔记"),
    "TIP":       ("\U0001F4A1", "提示"),
    "INFO":      ("ℹ️", "信息"),
    "WARNING":   ("⚠️", "注意"),
    "IMPORTANT": ("❗", "重要"),
    "CAUTION":   ("\U0001F6D1", "警告"),
    "SUCCESS":   ("✅", "完成"),
    "QUOTE":     ("\U0001F5E3️", "引用"),
}

ALLOWED_TAGS = {
    "p", "h2", "h3", "h4", "ul", "ol", "li", "span", "img", "a",
    "table", "thead", "tbody", "tr", "th", "td", "br", "hr", "section",
}
FORBIDDEN_TAGS = {"script", "style", "iframe", "video", "audio", "form", "input"}


def build_styles(t):
    """Inline CSS for every element type, derived from the chosen theme."""
    return {
        "accent": t["accent"],
        "muted": t["muted"],
        "divider": t["divider"],
        "code_bg": t["code_bg"],
        "code_fg": t["code_fg"],
        "text": t["text"],
        "p": ("font-size: 16px; line-height: 1.8; color: %s; "
              "margin: 18px 0; letter-spacing: 0.5px; text-align: justify;"
              % t["text"]),
        "h2": ("font-size: 20px; font-weight: bold; line-height: 1.5; "
               "color: %s; margin: 34px 0 16px 0; padding-left: 12px; "
               "border-left: 4px solid %s; letter-spacing: 0.5px;"
               % (t["heading"], t["heading_bar"])),
        "h3": ("font-size: 17px; font-weight: bold; line-height: 1.5; "
               "color: %s; margin: 26px 0 12px 0; letter-spacing: 0.5px;"
               % t["heading"]),
        "h4": ("font-size: 16px; font-weight: bold; line-height: 1.5; "
               "color: %s; margin: 22px 0 10px 0;" % t["heading"]),
        "li": ("font-size: 16px; line-height: 1.8; color: %s; margin: 8px 0;"
               % t["text"]),
        "code_inline": ("background-color: %s; color: %s; font-size: 14px; "
                        "padding: 3px 6px; border-radius: 3px; "
                        "font-family: Menlo, Consolas, monospace;"
                        % (t["code_bg"], t["code_fg"])),
        "blockquote": ("background-color: %s; color: %s; padding: 14px 16px; "
                       "margin: 20px 0; border-left: 4px solid %s; "
                       "font-size: 15px; line-height: 1.8;"
                       % (t["quote_bg"], t["text"], t["quote_bar"])),
        "table": ("border-collapse: collapse; margin: 20px 0; font-size: 14px; "
                  "width: 100%;"),
        "th": ("background-color: %s; color: %s; font-weight: bold; "
               "padding: 10px 8px; text-align: left; border: 1px solid %s;"
               % (t["th_bg"], t["heading"], t["divider"])),
        "td": ("padding: 10px 8px; border: 1px solid %s; color: %s; "
               "font-size: 14px; line-height: 1.7;" % (t["divider"], t["text"])),
        "a": ("color: %s; text-decoration: none; border-bottom: 1px solid %s;"
              % (t["link"], t["link"])),
        "hr": ("border: none; border-top: 1px solid %s; margin: 28px 0;"
               % t["divider"]),
    }


# ============================================================
# INPUT READERS  (starter kit logic, extended)
# ============================================================

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_front_matter(text):
    """Return (metadata_dict, body). Supports a minimal YAML subset."""
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta, body = {}, text[m.end():]
    for line in m.group(1).splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        v = v.strip().strip("'\"")
        if v:
            meta[k.strip()] = v
    return meta, body


def read_markdown(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    meta, body = parse_front_matter(content)
    html = markdown.markdown(body, extensions=[
        "extra", "fenced_code", "nl2br", "sane_lists", "toc",
    ])
    return html, meta


def read_docx(filepath):
    """Starter-kit logic, extended: lists and tables are now preserved."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(filepath)
    parts, meta = [], {}
    title = None

    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style_name = para.style.name if para.style else ""
            m = re.match(r"Heading (\d)", style_name)
            if m:
                lvl = int(m.group(1))
                if lvl == 1 and title is None:
                    title = text          # first Heading 1 becomes article title
                    continue
                tagname = "h2" if lvl <= 2 else ("h3" if lvl == 3 else "h4")
                parts.append("<%s>%s</%s>" % (tagname, html_lib.escape(text), tagname))
            else:
                parts.append("<p>%s</p>" % _docx_inline_runs(para))
        elif tag == "tbl":
            parts.append(_docx_table(Table(child, doc)))

    if title:
        meta["title"] = title
    return "\n".join(parts), meta


def _docx_inline_runs(para):
    out = []
    for run in para.runs:
        t = html_lib.escape(run.text)
        if not t:
            continue
        if run.bold and run.italic:
            out.append('<span style="font-weight:bold;font-style:italic;">%s</span>' % t)
        elif run.bold:
            out.append('<span style="font-weight:bold;">%s</span>' % t)
        elif run.italic:
            out.append('<span style="font-style:italic;">%s</span>' % t)
        else:
            out.append(t)
    return "".join(out)


def _docx_table(tbl):
    rows = []
    for row in tbl.rows:
        cells = []
        for c in row.cells:
            txt = html_lib.escape(c.text.strip())
            cells.append(txt)
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    head, *body = rows
    html = ["<table><thead><tr>"]
    for c in head:
        html.append("<th>%s</th>" % c)
    html.append("</tr></thead><tbody>")
    for r in body:
        html.append("<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>")
    html.append("</tbody></table>")
    return "".join(html)


# ============================================================
# CHINESE TYPOGRAPHY  (new capability #6)
# ============================================================

CJK = r"一-鿿㐀-䶿"


def polish_chinese_spacing(text):
    """Insert a hair space between CJK and Latin/digits.

    '用Python写脚本' -> '用 Python 写脚本'
    Only touches boundaries; never inserts inside a Latin word.
    """
    if not text:
        return text
    # CJK followed by Latin/digit
    text = re.sub(r"([%s])([A-Za-z0-9])" % CJK, r"\1 \2", text)
    # Latin/digit followed by CJK
    text = re.sub(r"([A-Za-z0-9])([%s])" % CJK, r"\1 \2", text)
    return text


def normalize_punctuation(text):
    """Full-width punctuation for CJK context; keep code-ish content intact."""
    if not text:
        return text
    pairs = [
        (r"([%s])," % CJK, r"\1，"),
        (r"([%s]);" % CJK, r"\1；"),
        (r"([%s]):" % CJK, r"\1："),
        (r"([%s])\?" % CJK, r"\1？"),
        (r"([%s])!" % CJK, r"\1！"),
    ]
    for pat, rep in pairs:
        text = re.sub(pat, rep, text)
    # collapse repeated spaces introduced by the rules above
    return re.sub(r"[ \t]{2,}", " ", text)


# ============================================================
# SANITIZER  (starter kit logic + bug fixes + callouts)
# ============================================================

# NOTE: no re.M / re.S here. Under re.M, '$' would match at every line end;
# under re.S, '.*' would swallow the whole quote. The title must stay on the
# marker line only, so `[^\n]*` is the correct quantifier.
CALLOUT_RE = re.compile(r"^\[!([A-Za-z]+)\][ \t]*([^\n]*)")


def sanitize(html_text, styles, zh_spacing=True):
    soup = BeautifulSoup(html_text, "lxml")

    for name in FORBIDDEN_TAGS:
        for el in soup.find_all(name):
            el.decompose()

    # h1 -> h2 (WeChat reserves h1 for the article title)
    for h1 in soup.find_all("h1"):
        h1.name = "h2"

    # div -> p  (keep it simple; markdown rarely emits bare div)
    for div in soup.find_all("div"):
        div.name = "p"

    _fix_code_blocks(soup, styles)
    # callouts MUST run before _fix_blockquotes: that step rewrites every
    # <blockquote> into a <p>, after which the [!KIND] marker is no longer
    # detectable as a blockquote.
    _convert_callouts(soup, styles)
    _fix_blockquotes(soup, styles)
    _flatten_inline(soup, styles)
    _style_tables(soup, styles)

    if zh_spacing:
        _apply_zh_polish(soup)

    return soup


def _br(soup):
    """A <br/> built with the soup's own factory.

    Do NOT use BeautifulSoup("<br/>") to make one: the lxml parser wraps a
    bare fragment in <html><body>, and appending that injects a nested
    document into the output. new_tag() always yields a bare element.
    """
    return soup.new_tag("br")


def _fix_code_blocks(soup, styles):
    """BUG-1 FIX.

    The starter kit did `p.string = code_text`, which emitted literal
    '\\n' inside a <p>. HTML collapses those newlines, so every code
    block rendered as one unreadable line and indentation was lost.

    Fix: split on newlines and join with <br>, which WeChat preserves.
    Also add a monospace font-family, absent from the starter kit.
    """
    for pre in soup.find_all("pre"):
        code = pre.find("code")
        raw = code.get_text() if code else pre.get_text()
        lines = raw.split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        body = "<br/>".join(html_lib.escape(l) if l.strip() else "&nbsp;"
                            for l in lines)
        new_p = soup.new_tag("p")
        new_p["style"] = (
            "background-color: %s; color: #24292e; font-size: 13px; "
            "line-height: 1.65; padding: 16px 14px; margin: 20px 0; "
            "border-left: 4px solid %s; border-radius: 4px; "
            "font-family: Menlo, Consolas, 'Courier New', monospace; "
            "white-space: pre-wrap; word-break: break-word; overflow-x: auto;"
            % (styles["code_bg"], styles["code_fg"]))
        # Append plain NavigableStrings separated by <br/>: parsing a
        # fragment would wrap lines in their own <p> (invalid nesting) and
        # pre-escaping would double-encode entities.
        for i, line in enumerate(lines):
            if i:
                new_p.append(_br(soup))
            if not line.strip():
                new_p.append(NavigableString(" "))
                continue
            # Leading spaces are meaningless in HTML and get collapsed, which
            # destroys code indentation. Encode them as non-breaking spaces
            # ( ) so the visual indent survives the round trip.
            stripped = line.lstrip(" ")
            indent = len(line) - len(stripped)
            new_p.append(NavigableString(" " * indent + stripped))
        pre.replace_with(new_p)


def _fix_blockquotes(soup, styles):
    """BUG-2 FIX.

    The starter kit did `p.string = bq.get_text()`, discarding every
    <strong>/<em>/<code> inside the quote. Fix: unwrap the children
    into a styled <p> so inline formatting survives.
    """
    for bq in soup.find_all("blockquote"):
        new_p = soup.new_tag("p")
        new_p["style"] = styles["blockquote"]
        for child in list(bq.children):
            if isinstance(child, NavigableString):
                new_p.append(NavigableString(str(child)))
            else:
                new_p.append(child.extract())
        bq.replace_with(new_p)


def _convert_callouts(soup, styles, theme=None):
    """New capability #2: '> [!NOTE]' blockquote -> coloured callout box."""
    for bq in list(soup.find_all("blockquote")):
        text = bq.get_text().strip()
        if not CALLOUT_RE.match(text):
            continue

        # Two adjacent callouts separated by a blank ">" line collapse into a
        # single <blockquote>. Split on every marker so each becomes its own box.
        flat = re.sub(r"<br\s*/?>", "\n", text)
        segments = []
        current_kind, current_title, buf = None, None, []
        for line in flat.split("\n"):
            m = CALLOUT_RE.match(line.strip())
            if m and m.group(1).upper() in CALLOUTS:
                if current_kind:
                    segments.append((current_kind, current_title,
                                     "\n".join(buf).strip()))
                current_kind = m.group(1).upper()
                current_title = m.group(2).strip()
                buf = []
            else:
                buf.append(line.strip())
        if current_kind:
            segments.append((current_kind, current_title, "\n".join(buf).strip()))
        if not segments:
            continue

        boxes = []
        for kind, title, content in segments:
            emoji, default_label = CALLOUTS[kind]
            new_p = soup.new_tag("section")
            new_p["style"] = (
                "background-color: %s; padding: 14px 16px; margin: 22px 0; "
                "border-left: 4px solid %s; border-radius: 4px; "
                "font-size: 15px; line-height: 1.8; color: %s;"
                % (_tint(styles), styles["accent"], styles["text"]))
            head = soup.new_tag("p")
            head["style"] = ("font-size: 15px; font-weight: bold; color: %s; "
                             "margin: 0 0 6px 0;" % styles["accent"])
            head.append(NavigableString(
                "%s %s" % (emoji, title or default_label)))
            new_p.append(head)
            if content:
                cp = soup.new_tag("p")
                cp["style"] = "font-size: 15px; line-height: 1.8; margin: 0;"
                _append_lines(soup, cp, content)
                new_p.append(cp)
            boxes.append(new_p)

        bq.replace_with(boxes[0])
        for prev, nxt in zip(boxes, boxes[1:]):
            prev.insert_after(nxt)


def _append_lines(soup, tag, text):
    """Append newline-separated text into `tag` using <br/>.

    Text is added as a plain NavigableString and left unescaped, so
    BeautifulSoup escapes exactly once (pre-escaping would double-encode
    `&` into `&amp;quot;`).
    """
    for i, line in enumerate(text.split("\n")):
        if i:
            tag.append(_br(soup))
        tag.append(NavigableString(line))


def _tint(styles):
    """Callout background: reuse the theme's soft code-block background."""
    return styles["code_bg"]


def _flatten_inline(soup, styles):
    """Starter-kit behaviour: strong/em/... -> styled <span>."""
    for tag in soup.find_all(["strong", "b"]):
        span = soup.new_tag("span")
        span["style"] = "font-weight: bold; color: %s;" % styles["accent"]
        span.append(NavigableString(tag.get_text()))
        tag.replace_with(span)

    for tag in soup.find_all(["em", "i"]):
        span = soup.new_tag("span")
        span["style"] = "font-style: italic;"
        span.append(NavigableString(tag.get_text()))
        tag.replace_with(span)

    # inline <code> (outside pre, which is already handled)
    for code in soup.find_all("code"):
        if code.find_parent("pre"):
            continue
        span = soup.new_tag("span")
        span["style"] = styles["code_inline"]
        span.append(NavigableString(code.get_text()))
        code.replace_with(span)

    for hr in soup.find_all("hr"):
        p = soup.new_tag("p")
        p["style"] = styles["hr"]
        hr.replace_with(p)


def _style_tables(soup, styles):
    for table in soup.find_all("table"):
        table["style"] = styles["table"]
        for th in table.find_all("th"):
            th["style"] = styles["th"]
        for td in table.find_all("td"):
            td["style"] = styles["td"]


def _apply_zh_polish(soup):
    """Apply CJK spacing to visible text only, never inside code blocks."""
    for el in soup.find_all(True):
        if el.find_parent("code") or el.name in ("code", "pre"):
            continue
        for node in list(el.children):
            if isinstance(node, NavigableString):
                new = polish_chinese_spacing(str(node))
                new = normalize_punctuation(new)
                if new != str(node):
                    node.replace_with(NavigableString(new))


# ============================================================
# TOC / METADATA / FOOTER  (new capabilities #3 #4 #5)
# ============================================================

def _soup():
    """A fresh empty soup, used purely as a tag factory."""
    return BeautifulSoup("", "lxml")


def build_toc(soup, theme, skip_first_heading=False):
    """Insert an inline-styled table of contents after the metadata block."""
    heads = soup.find_all(["h2", "h3"])
    # When front matter supplies the title, the leading "# ..." heading is a
    # duplicate of it (h1 was rewritten to h2). Listing it as section 1 would
    # be both redundant and misleading.
    if skip_first_heading and heads:
        heads = heads[1:]
    if len(heads) < 3:
        return False

    box = soup.new_tag("section")
    box["style"] = ("background-color: %s; padding: 16px 18px; margin: 24px 0; "
                    "border: 1px solid %s; border-radius: 6px;"
                    % (theme["th_bg"], theme["divider"]))

    title_p = soup.new_tag("p")
    title_p["style"] = ("font-size: 15px; font-weight: bold; color: %s; "
                        "margin: 0 0 10px 0;" % theme["heading"])
    title_p.append(NavigableString("\U0001F4D6 本文目录"))
    box.append(title_p)

    # Number only the h2 sections. Counting h2 and h3 together produced
    # a sequence like 1,2,3,6,8 because sub-headings consumed numbers too.
    section_no = 0
    for h in heads:
        if h.name == "h3":
            label = "· " + h.get_text().strip()
            style = ("font-size: 14px; line-height: 1.9; color: %s; "
                     "margin: 3px 0; padding-left: 14px;" % theme["muted"])
        else:
            section_no += 1
            label = "%d. %s" % (section_no, h.get_text().strip())
            style = ("font-size: 15px; line-height: 1.9; color: %s; "
                     "margin: 5px 0; font-weight: bold;" % theme["text"])
        row = soup.new_tag("p")
        row["style"] = style
        row.append(NavigableString(label))
        box.append(row)

    first = soup.find(["h2", "h3", "p"])
    if first:
        first.insert_before(box)
    else:
        soup.append(box)
    return True


def build_metadata(meta, theme):
    """New capability #4: title / author / date / abstract block."""
    if not meta:
        return None
    box = _soup().new_tag("section")
    box["style"] = ("padding: 0 0 18px 0; margin: 0 0 8px 0; "
                    "border-bottom: 1px solid %s;" % theme["divider"])

    title = meta.get("title")
    if title:
        p = _soup().new_tag("p")
        p["style"] = ("font-size: 22px; font-weight: bold; color: %s; "
                      "line-height: 1.45; margin: 0 0 10px 0;"
                      % theme["heading"])
        p.append(NavigableString(title))
        box.append(p)

    bits = [meta[k] for k in ("author", "date") if meta.get(k)]
    if bits:
        p = _soup().new_tag("p")
        p["style"] = ("font-size: 13px; color: %s; margin: 0 0 8px 0;"
                      % theme["muted"])
        p.append(NavigableString(" · ".join(bits)))
        box.append(p)

    abstract = meta.get("abstract") or meta.get("description")
    if abstract:
        p = _soup().new_tag("p")
        p["style"] = ("font-size: 14px; color: %s; line-height: 1.8; "
                      "margin: 0; padding: 10px 12px; background-color: %s; "
                      "border-radius: 4px;"
                      % (theme["text"], theme["th_bg"]))
        p.append(NavigableString(abstract))
        box.append(p)

    return box


def build_footer(meta, theme, copyright_text=None, show_footer=True):
    """New capability #5: divider + copyright / signature line."""
    if not show_footer:
        return None
    frag = _soup()
    box = frag.new_tag("section")
    box["style"] = ("border-top: 1px solid %s; margin: 36px 0 0 0; "
                    "padding-top: 18px;" % theme["divider"])
    inner = frag.new_tag("p")
    inner["style"] = ("font-size: 13px; color: %s; line-height: 1.9; "
                      "text-align: center; margin: 0;" % theme["muted"])

    lines = []
    if copyright_text:
        lines.append(copyright_text)
    else:
        author = meta.get("author")
        lines.append("— 原创%s，转载请注明出处" % ("，作者：%s" % author
                                            if author else ""))
    inner.append(NavigableString(lines[0]))
    box.append(inner)

    if meta.get("original"):
        row = frag.new_tag("p")
        row["style"] = ("font-size: 13px; color: %s; text-align: center; "
                        "margin: 6px 0 0 0;" % theme["muted"])
        row.append(NavigableString("本文首发于微信公众号"))
        box.append(row)
    return box


# ============================================================
# FINAL CLEANUP + OUTPUT
# ============================================================

def clean_attributes(soup, styles):
    for tag in soup.find_all(True):
        for attr in ("class", "id", "align", "width", "height"):
            if attr in tag.attrs:
                del tag.attrs[attr]

        if tag.name in FORBIDDEN_TAGS:
            tag.decompose()
            continue

        if tag.name not in ALLOWED_TAGS and tag.name not in (
                "html", "head", "body", "[document]"):
            tag.unwrap()

    # default styles for anything still bare
    for name in ("h2", "h3", "h4", "p", "li", "a"):
        for el in soup.find_all(name):
            if not el.get("style"):
                el["style"] = styles[name]


def _block_style(hrefs=True):
    return "max-width: 677px; margin: 0 auto; padding: 20px;"


def render(soup, title, fragment=False):
    """Wrap content. `fragment=True` returns only the pasteable body."""
    if fragment:
        body = soup.find("body")
        return "".join(str(c) for c in (body.children if body else soup.children))

    body = soup.find("body")
    content = "\n".join(str(c) for c in body.children) if body else str(soup)
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "<title>%s</title>\n</head>\n"
        "<body style=\"max-width: 677px; margin: 0 auto; padding: 20px; "
        "background: #ffffff; font-family: -apple-system, BlinkMacSystemFont, "
        "'PingFang SC', 'Helvetica Neue', 'Microsoft YaHei', sans-serif;\">\n"
        "%s\n</body>\n</html>\n" % (html_lib.escape(title or "WeChat Article"), content)
    )


def convert_one(input_path, output_path, args, theme_name=None):
    theme_name = theme_name or args.theme
    theme = THEMES[theme_name]
    styles = build_styles(theme)

    path = Path(input_path)
    if not path.exists():
        print("  [x] file not found: %s" % path)
        return False

    ext = path.suffix.lower()
    print("[1/6] reading %s" % path.name)
    if ext == ".md":
        html_text, meta = read_markdown(path)
    elif ext == ".docx":
        html_text, meta = read_docx(path)
    elif ext in (".html", ".htm"):
        html_text = path.read_text(encoding="utf-8")
        meta = {}
    else:
        print("  [x] unsupported format: %s" % ext)
        return False

    # CLI overrides front matter
    for key in ("title", "author", "date", "abstract"):
        val = getattr(args, key, None)
        if val:
            meta[key] = val

    print("[2/6] sanitizing (callouts / code / quotes)")
    soup = sanitize(html_text, styles, zh_spacing=not args.no_zh_spacing)

    print("[3/6] injecting metadata + toc")
    meta_box = build_metadata(meta, theme)
    if meta_box:
        body = soup.find("body")
        if body is not None:
            body.insert(0, meta_box)
        else:
            soup.append(meta_box)
        print("  metadata: title/author/date/abstract inserted")
    if args.toc:
        if build_toc(soup, theme, skip_first_heading=bool(meta.get("title"))):
            print("  toc: generated")

    print("[4/6] appending footer")
    footer = build_footer(meta, theme, args.footer_copyright, not args.no_footer)
    if footer:
        # Append into <body>, not the soup root: BeautifulSoup.append() on the
        # root places the node outside <body>, so render() would drop it.
        target = soup.find("body")
        if target is not None:
            target.append(footer)
        else:
            soup.append(footer)

    print("[5/6] cleaning attributes (theme=%s)" % theme_name)
    clean_attributes(soup, styles)

    print("[6/6] writing %s" % output_path)
    Path(output_path).write_text(render(soup, meta.get("title"), args.fragment),
                                 encoding="utf-8")
    if not args.fragment and args.fragment_out:
        Path(args.fragment_out).write_text(
            render(soup, meta.get("title"), True), encoding="utf-8")

    size = os.path.getsize(output_path) / 1024
    print("  done: %.1f KB\n" % size)
    return True


def main():
    p = argparse.ArgumentParser(
        description="Markdown/Word -> WeChat Official Account HTML")
    p.add_argument("input", help="input .md/.docx/.html file, or a directory")
    p.add_argument("output", help="output .html file, or output directory")
    p.add_argument("--theme", default="default", choices=list(THEMES),
                   help="colour theme (default: default)")
    p.add_argument("--toc", action="store_true", help="insert a table of contents")
    p.add_argument("--title", help="override article title")
    p.add_argument("--author", help="article author")
    p.add_argument("--date", help="publish date")
    p.add_argument("--abstract", help="article abstract / 摘要")
    p.add_argument("--footer-copyright", help="custom footer text")
    p.add_argument("--no-footer", action="store_true", help="omit the footer")
    p.add_argument("--no-zh-spacing", action="store_true",
                   help="disable CJK/Latin spacing polish")
    p.add_argument("--batch", action="store_true",
                   help="treat input as a directory of .md files")
    p.add_argument("--fragment", action="store_true",
                   help="output only the pasteable fragment")
    p.add_argument("--fragment-out", help="also write the bare fragment here")
    args = p.parse_args()

    inp = Path(args.input)
    if args.batch or inp.is_dir():
        outdir = Path(args.output)
        outdir.mkdir(parents=True, exist_ok=True)
        files = sorted(inp.glob("*.md"))
        if not files:
            print("no .md files found in %s" % inp)
            return 1
        print("batch mode: %d file(s), theme=%s\n" % (len(files), args.theme))
        ok = sum(1 for f in files
                 if convert_one(f, outdir / (f.stem + ".html"), args))
        print("batch finished: %d/%d succeeded" % (ok, len(files)))
        return 0 if ok else 1

    ok = convert_one(inp, args.output, args)
    if ok:
        print("next steps:")
        print("  1. open %s in a browser" % args.output)
        print("  2. select the article body -> copy")
        print("  3. paste into mp.weixin.qq.com editor")
        print("  4. preview on phone -> publish")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())