---
name: meteorain-wechat-publisher
description: "Convert Markdown or Word documents into paste-ready WeChat Official Account (微信公众号) HTML. Applies inline CSS, strips tags the WeChat editor rejects, and adds five colour themes, callout boxes, an automatic table of contents, an article metadata header, a copyright footer, and Chinese/Latin spacing polish. This skill should be used when the user says 'convert to WeChat', '公众号文章', '微信公众号格式', '转换成公众号', 'make WeChat article', 'generate WeChat HTML', '排版成公众号', asks to publish an article to a WeChat Official Account, or supplies a .md or .docx file and wants it formatted for WeChat publishing."
agent_created: true
---

# WeChat Publisher — Markdown/Word → 公众号 HTML

## Purpose

Treat this skill as a print driver for WeChat: supply content, receive
copy-paste-ready HTML that survives the WeChat editor's strict rules. The
conversion is deterministic, so a given input always yields the same output.

This skill is derived from the C4B starter kit
(`scripts/starter_baseline.py`, kept for comparison). It fixes two defects
found in that baseline and adds seven capabilities.

## Quick Start

```bash
python scripts/wechat_publisher.py article.md article.html --theme accent --toc
```

Then open `article.html` in a browser, select the article body, copy, and paste
into the WeChat editor at mp.weixin.qq.com.

## Inputs and Outputs

| Direction | Format | Notes |
|-----------|--------|-------|
| Input | `.md` | YAML front matter supported; callouts and fenced code supported |
| Input | `.docx` | Headings, paragraphs, bold/italic, tables |
| Input | `.html` | Re-sanitized and re-styled |
| Input | directory | With `--batch`, converts every `.md` inside |
| Output | `.html` | Full preview page by default |
| Output | `.html` | With `--fragment`, only the pasteable body markup |

## Options

| Flag | Default | Effect |
|------|---------|--------|
| `--theme NAME` | `default` | `default` / `accent` / `minimal` / `solo` / `dark` |
| `--toc` | off | Insert an inline-styled table of contents |
| `--title` / `--author` / `--date` / `--abstract` | — | Override front matter |
| `--footer-copyright` | auto | Custom footer text |
| `--no-footer` | off | Omit the footer |
| `--no-zh-spacing` | off | Disable CJK/Latin spacing polish |
| `--batch` | off | Treat input as a directory |
| `--fragment` | off | Emit only the pasteable fragment |
| `--fragment-out PATH` | — | Also write the bare fragment to a second file |

## Article Authoring Conventions

Use YAML front matter for metadata:

```markdown
---
title: 文章标题
author: 作者名
date: 2026-10-06
abstract: 一句话摘要，用于公众号的摘要位。
---
```

Write callouts as blockquotes whose first line carries a marker:

```markdown
> [!NOTE] 可选标题
> 正文内容。

> [!WARNING] 注意
> 另一条独立提示。
```

Recognised markers: `NOTE` `TIP` `INFO` `WARNING` `IMPORTANT` `CAUTION`
`SUCCESS` `QUOTE`. Anything else is treated as an ordinary blockquote.

**Insert a blank `>` line between two callouts.** Markdown otherwise merges
adjacent callouts into one blockquote; the converter splits them again, but
separating them explicitly keeps the source readable.

## Workflow

1. **Read** the source. Parse front matter, detect format by extension.
2. **Sanitize**, in this order — the order is load-bearing:
   1. drop `script` / `style` / `iframe` / `video` / `audio`
   2. rewrite `h1` → `h2`
   3. rewrite `div` → `p`
   4. convert `<pre>` code blocks, preserving line breaks and indentation
   5. convert `[!KIND]` callouts — **must precede step 6**
   6. convert remaining blockquotes, preserving inline formatting
   7. flatten `strong`/`em`/`code` into styled `<span>`
   8. style tables cell by cell
   9. apply Chinese typography polish
3. **Inject** the metadata header, then the table of contents.
4. **Append** the footer into `<body>`.
5. **Clean** attributes: drop `class`, `id`, `align`, `width`, `height`;
   unwrap tags outside the allow-list.
6. **Render** either a full preview page or a bare fragment.

## What Was Fixed From the Starter Kit

Both defects were found by running the baseline and inspecting the output, not
by reading the code. `scripts/starter_baseline.py` reproduces them.

| ID | Defect | Cause | Fix |
|----|--------|-------|-----|
| BUG-1 | Code blocks rendered as one line; indentation lost | `p.string = code_text` wrote a literal `\n` into a `<p>`, and HTML collapses newlines | Split lines, join with `<br/>`, encode leading indent as U+00A0 |
| BUG-2 | Bold and inline code inside blockquotes were flattened to plain text | `p.string = bq.get_text()` discarded every child node | Move the child nodes into the styled `<p>` instead of re-creating text |

Three further traps were hit while building callout support, all caused by
BeautifulSoup's fragment parsing and worth remembering:

- `BeautifulSoup("<br/>")` parses to `<html><body><br/></body></html>`. Appending
  that injects a nested document. Always use `soup.new_tag("br")`.
- Pre-escaping text and then appending it double-encodes: `&quot;` becomes
  `&amp;quot;`. Append raw `NavigableString`s and let the parser escape once.
- A `<p>` must never contain another `<p>`. Boxes that group paragraphs use
  `<section>`, which WeChat renders reliably.

## WeChat Constraints Enforced

Allowed tags: `p` `h2` `h3` `h4` `ul` `ol` `li` `span` `img` `a` `table`
`thead` `tbody` `tr` `th` `td` `br` `hr` `section`.

Rewritten or removed: `h1`→`h2`, `div`→`p`, `script`/`style`/`iframe` removed,
`class`/`id` removed, `<pre><code>`→styled `<p>`, `hr`→styled `<p>`.

All CSS is inline. No `<style>` block, no classes, no layout properties.

Full detail: `references/wechat_restrictions.md`. Original baseline palette:
`references/starter_baseline_styles.md`.

## Capabilities

1. **Theme system** — five palettes; every style derives from theme tokens.
2. **Callout boxes** — eight marker types rendered as bordered cards.
3. **Auto TOC** — built from `h2`/`h3`, numbered.
4. **Metadata block** — title, author, date, abstract from front matter or flags.
5. **Footer** — divider plus copyright line, customisable.
6. **Chinese typography** — automatic spacing between CJK and Latin/digits.
7. **Batch mode** — convert a whole directory of `.md` files.

## Adding a Theme

Extend the `THEMES` dict with the same keys used by the existing entries
(`accent`, `heading`, `heading_bar`, `text`, `muted`, `code_bg`, `code_fg`,
`quote_bar`, `quote_bg`, `th_bg`, `link`, `divider`). Every style is derived
from these tokens by `build_styles()`, so a new theme needs no changes there.

When adding a style key that helpers read directly (`accent`, `muted`,
`divider`, `code_bg`, `code_fg`, `text`), add it to `build_styles()` as well —
helpers index that dict, not the theme.

## Verification

```bash
python scripts/eval_wechat_publisher.py
```

37 assertions covering both bug fixes, all seven capabilities, WeChat
compliance, five themes, batch mode, and edge cases (empty file, missing front
matter, missing input, fragment mode). Exit code 0 means all passed.

Treat this as a contract: when changing `wechat_publisher.py`, run the eval and
keep it at 100%. It caught six real defects during initial development.

## Edge Cases

| Situation | Handling |
|-----------|----------|
| Empty file | Converts to an empty body without crashing |
| No front matter | Metadata block skipped, conversion proceeds |
| Missing input file | Error message, exit code 1 |
| Unsupported extension | Lists supported formats, exit code 1 |
| Adjacent callouts | Split into separate boxes automatically |
| Very long article | Converts fine; WeChat caps articles near 20,000 characters |
| Wide tables | No horizontal scroll available; split wide tables manually |
| Images | `img` tags are preserved; local files still need uploading to the WeChat media library |

## Dependencies

```bash
pip install markdown beautifulsoup4 python-docx lxml
```

The script auto-installs anything missing on first run.