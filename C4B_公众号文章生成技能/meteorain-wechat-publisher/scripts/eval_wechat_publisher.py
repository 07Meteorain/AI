#!/usr/bin/env python3
"""
eval_wechat_publisher.py — automated checks for the meteorain-wechat-publisher skill.

Run:  python scripts/eval_wechat_publisher.py
Exit code 0 = all checks passed.

Each check maps to a capability claimed in SKILL.md, so the eval is a
contract test rather than a smoke test.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONVERTER = HERE / "wechat_publisher.py"
PY = sys.executable

FIXTURES = {
    "callouts.md": """---
title: 评测样例
author: Tester
date: 2026-10-06
abstract: 用于自动化评测的样例文章。
---

# 评测样例

> [!NOTE] 笔记标题
> 这是提示内容。
> [!WARNING] 警告标题
> 这是警告内容。

## 普通引用

普通引用里的 **加粗** 和 `代码` 都要保留。

## 代码块

```python
def demo():
    print("one")
    return 2
```

## 表格

| 名称 | 说明 |
|------|------|
| 甲 | 第一 |
| 乙 | 第二 |
""",
    "edge_empty.md": "",
    "edge_nofm.md": "# 没有 front matter\n\n只有一段正文。\n",
}


def run(args, script=None):
    """Invoke a skill script with args. Defaults to the main converter."""
    return subprocess.run([PY, str(script or CONVERTER)] + args,
                          capture_output=True, text=True)


PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %s%s" % ("[PASS]" if cond else "[FAIL]", name,
                         ("  -> " + detail) if detail and not cond else ""))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="wxpub_eval_"))
    for name, body in FIXTURES.items():
        (tmp / name).write_text(body, encoding="utf-8")

    print("=" * 62)
    print("eval: meteorain-wechat-publisher")
    print("=" * 62)

    out = tmp / "eval.html"
    r = run([str(tmp / "callouts.md"), str(out), "--theme", "accent", "--toc"])
    check("converts a full-featured article without error", r.returncode == 0,
          r.stderr[-300:])
    if not out.exists():
        print("\nFATAL: no output produced")
        return 1
    html = out.read_text(encoding="utf-8")

    # --- capability 2: callouts -------------------------------------------
    check("callout: NOTE box rendered", "笔记标题" in html)
    check("callout: WARNING box rendered", "警告标题" in html)
    check("callout: two adjacent boxes split, not merged",
          html.count("border-radius: 4px; font-size: 15px") >= 2,
          "found %d" % html.count("border-radius: 4px; font-size: 15px"))

    # --- BUG-1: code block line breaks ------------------------------------
    code_m = re.search(r"def demo.*?</p>", html, re.S)
    code = code_m.group(0) if code_m else ""
    check("BUG-1 fixed: code block keeps line breaks", "<br/>" in code,
          "no <br/> in code block")
    check("BUG-1 fixed: indentation preserved",
          "    print" in code or "    print" in code,
          "indentation lost")
    check("BUG-1 fixed: entities not double-escaped",
          "&amp;quot;" not in code and "&amp;lt;" not in html,
          "double-escaped entities present")

    # --- BUG-2: blockquote inline formatting ------------------------------
    check("BUG-2 fixed: bold survives inside blockquote",
          "加粗" in html and re.search(r'加粗[^<]*</span>|font-weight: bold[^"]*"[^>]*>'
                                       r'[^<]*加粗', html) is not None)
    check("BUG-2 fixed: inline code survives inside blockquote",
          re.search(r'Menlo[^"]*"[^>]*>[^<]*代码', html) is not None)

    # --- no invalid nested <p> -------------------------------------------
    check("no <p> nested directly inside <p>",
          re.search(r"<p[^>]*>(?:(?!</p>).)*<p[ >]", html, re.S) is None,
          "found nested <p>")

    # --- WeChat compliance ------------------------------------------------
    for tag in ("script", "style", "iframe", "div", "h1"):
        check("compliance: no <%s> in output" % tag,
              ("<%s" % tag) not in html)
    check("compliance: no class attributes", "class=" not in html)
    check("compliance: no id attributes", re.search(r'\sid="', html) is None)

    # --- capability 3: TOC ------------------------------------------------
    check("toc: generated when --toc passed", "本文目录" in html)
    r2 = run([str(tmp / "callouts.md"), str(tmp / "notoc.html")])
    check("toc: omitted by default",
          "本文目录" not in (tmp / "notoc.html").read_text(encoding="utf-8"))

    # --- capability 4: metadata ------------------------------------------
    check("metadata: title rendered", "评测样例" in html)
    check("metadata: author rendered", "Tester" in html)
    check("metadata: abstract rendered", "用于自动化评测" in html)
    check("metadata: front matter is not leaked as body text",
          "author: Tester" not in html)

    # --- capability 1: themes --------------------------------------------
    colors = {}
    for theme in ("default", "accent", "minimal", "solo", "dark"):
        o = tmp / ("t_%s.html" % theme)
        rr = run([str(tmp / "callouts.md"), str(o), "--theme", theme])
        if rr.returncode == 0 and o.exists():
            colors[theme] = o.read_text(encoding="utf-8")
    check("themes: all 5 themes convert successfully",
          len(colors) == 5, "got %d" % len(colors))
    check("themes: each theme produces distinct output",
          len(set(colors.values())) == len(colors),
          "themes collided")
    if "accent" in colors and "dark" in colors:
        check("themes: accent uses blue, dark uses light text",
              "#1a73e8" in colors["accent"] and "#e0e0e0" in colors["dark"])

    # --- capability 5: footer -------------------------------------------
    check("footer: present by default", "转载请注明出处" in html)
    r3 = run([str(tmp / "callouts.md"), str(tmp / "nofooter.html"),
              "--no-footer"])
    check("footer: suppressed by --no-footer",
          "转载请注明出处" not in
          (tmp / "nofooter.html").read_text(encoding="utf-8"))
    r4 = run([str(tmp / "callouts.md"), str(tmp / "custom.html"),
              "--footer-copyright", "版权所有 (c) 2026 Meteorain"])
    check("footer: custom text honoured",
          "版权所有 (c) 2026 Meteorain" in
          (tmp / "custom.html").read_text(encoding="utf-8"))

    # --- capability 6: Chinese typography --------------------------------
    (tmp / "zh.md").write_text("用Python写脚本很方便。\n", encoding="utf-8")
    run([str(tmp / "zh.md"), str(tmp / "zh.html")])
    zh = (tmp / "zh.html").read_text(encoding="utf-8")
    check("zh typography: space inserted between CJK and Latin",
          "用 Python 写脚本" in zh, "no spacing applied")
    run([str(tmp / "zh.md"), str(tmp / "zh_off.html"), "--no-zh-spacing"])
    zh_off = (tmp / "zh_off.html").read_text(encoding="utf-8")
    check("zh typography: --no-zh-spacing disables it",
          "用Python写脚本" in zh_off)

    # --- capability 7: batch ---------------------------------------------
    bdir = tmp / "batch"
    bdir.mkdir()
    for i in range(3):
        (bdir / ("post%d.md" % i)).write_text(
            "# 文章%d\n\n正文内容。\n" % i, encoding="utf-8")
    rb = run([str(bdir), str(tmp / "batchout"), "--batch"])
    produced = list((tmp / "batchout").glob("*.html"))
    check("batch: converts a whole directory",
          rb.returncode == 0 and len(produced) == 3,
          "produced %d files" % len(produced))

    # --- robustness / edge cases -----------------------------------------
    re_ = run([str(tmp / "edge_empty.md"), str(tmp / "empty.html")])
    check("edge: empty file does not crash", re_.returncode == 0)
    rn = run([str(tmp / "edge_nofm.md"), str(tmp / "nofm.html")])
    check("edge: file without front matter still converts",
          rn.returncode == 0 and (tmp / "nofm.html").exists())
    rmiss = run(["does_not_exist.md", str(tmp / "x.html")])
    check("edge: missing input reports failure", rmiss.returncode != 0)
    run([str(tmp / "callouts.md"), str(tmp / "frag.html"), "--fragment"])
    frag = (tmp / "frag.html").read_text(encoding="utf-8")
    check("fragment: bare output has no <html> shell",
          "<html" not in frag.lower())

    # --- baseline parity: starter kit still runnable ---------------------
    # Runs against the bundled example, not the temp fixture, because the
    # starter script resolves relative sample paths from its own directory.
    base = HERE / "starter_baseline.py"
    sample = ROOT / "examples" / "sample_article.md"
    if base.exists() and sample.exists():
        rb2 = run([str(sample), str(tmp / "base.html")], script=base)
        check("starter baseline preserved and still runnable",
              rb2.returncode == 0 and (tmp / "base.html").exists(),
              "rc=%s" % rb2.returncode)

    print("-" * 62)
    print("passed %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
    if FAIL:
        print("failed:")
        for f in FAIL:
            print("  - " + f)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())