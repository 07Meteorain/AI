#!/usr/bin/env python3
"""
WeChat Publisher — Convert Markdown or Word to WeChat-compatible HTML.

This is the STARTER KIT version. It handles basic conversion but lacks
advanced features like themes, math formulas, callout boxes, etc.
Your mission: use skill-creator to extend this into your own version.

Usage:
    python convert_to_wechat.py input.md output.html
    python convert_to_wechat.py report.docx output.html

Then: open output.html in browser → Ctrl+A → Ctrl+C → paste into WeChat editor.
"""

import sys
import os
import re
from pathlib import Path

# --- Auto-install dependencies ---
def install_dependencies():
    """Install required packages if not available."""
    missing = []
    try:
        import markdown
    except ImportError:
        missing.append("markdown")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        missing.append("beautifulsoup4")
    try:
        from docx import Document
    except ImportError:
        missing.append("python-docx")
    try:
        import lxml
    except ImportError:
        missing.append("lxml")

    if missing:
        print(f"Installing missing packages: {', '.join(missing)}...")
        import subprocess
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", *missing,
            "--break-system-packages", "-q"
        ])
        print("Done!\n")

install_dependencies()

import markdown
from bs4 import BeautifulSoup
from docx import Document

# ============================================================
# CONFIGURATION — Modify these to customize your output
# ============================================================

# Tags that WeChat allows
ALLOWED_TAGS = {
    'p', 'h2', 'h3', 'ul', 'ol', 'li', 'span', 'img', 'a',
    'table', 'tr', 'th', 'td', 'br',
}

# Tags that WeChat forbids (will be removed or converted)
FORBIDDEN_TAGS = {'script', 'style', 'iframe', 'h1', 'div'}

# CSS properties that WeChat allows in inline styles
ALLOWED_CSS = {
    'color', 'background-color', 'font-size', 'font-weight',
    'line-height', 'text-align', 'font-style', 'margin',
    'padding', 'border', 'border-left', 'border-collapse',
    'text-decoration',
}

# Default inline styles for each element type
# 💡 TIP: This is the easiest thing to customize!
#    Change colors, sizes, spacing to match your personal style.
STYLES = {
    'h2': (
        'font-size: 22px; font-weight: bold; line-height: 1.6; '
        'color: #333; margin: 20px 0 10px 0;'
    ),
    'h3': (
        'font-size: 18px; font-weight: bold; line-height: 1.6; '
        'color: #333; margin: 15px 0 8px 0;'
    ),
    'p': (
        'font-size: 16px; line-height: 1.75; color: #333; '
        'margin: 10px 0;'
    ),
    'li': (
        'font-size: 16px; line-height: 1.75; color: #333; '
        'margin: 5px 0;'
    ),
    'code_inline': (
        'background-color: #f5f5f5; color: #d73a49; font-size: 14px; '
        'padding: 2px 4px;'
    ),
    'code_block': (
        'background-color: #f6f8fa; color: #24292e; font-size: 14px; '
        'line-height: 1.6; padding: 16px; margin: 10px 0;'
    ),
    'blockquote': (
        'background-color: #f9f9f9; color: #666; padding: 10px 15px; '
        'margin: 10px 0; border-left: 4px solid #ddd;'
    ),
    'table': 'border-collapse: collapse; margin: 10px 0; font-size: 14px;',
    'th': (
        'background-color: #f6f8fa; color: #24292e; font-weight: bold; '
        'padding: 8px; text-align: left; border: 1px solid #ddd;'
    ),
    'td': 'padding: 8px; border: 1px solid #ddd; color: #333;',
    'a': 'color: #0366d6; text-decoration: underline;',
}


# ============================================================
# INPUT READERS
# ============================================================

def read_markdown(filepath):
    """Convert Markdown file to HTML string."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    html = markdown.markdown(content, extensions=[
        'extra',          # Tables, footnotes, etc.
        'fenced_code',    # ```code blocks```
        'nl2br',          # Newline → <br>
        'sane_lists',     # Better list handling
    ])
    return html


def read_docx(filepath):
    """Convert Word .docx to HTML string."""
    doc = Document(filepath)
    parts = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Map Word heading styles to HTML headings
        style_name = para.style.name if para.style else ''
        if style_name.startswith('Heading'):
            level = style_name.replace('Heading ', '')
            tag = 'h2' if level in ('1', '2') else 'h3'
            parts.append(f'<{tag}>{text}</{tag}>')
        else:
            # Process inline formatting (bold, italic)
            p_html = '<p>'
            for run in para.runs:
                t = run.text
                if not t:
                    continue
                if run.bold and run.italic:
                    p_html += f'<span style="font-weight:bold;font-style:italic;">{t}</span>'
                elif run.bold:
                    p_html += f'<span style="font-weight:bold;">{t}</span>'
                elif run.italic:
                    p_html += f'<span style="font-style:italic;">{t}</span>'
                else:
                    p_html += t
            p_html += '</p>'
            parts.append(p_html)

    return '\n'.join(parts)


# ============================================================
# HTML SANITIZER
# ============================================================

def sanitize(html):
    """
    Sanitize HTML for WeChat compatibility.

    Steps:
    1. Remove forbidden tags entirely (script, style, iframe)
    2. Convert h1 → h2, div → p
    3. Handle code blocks → styled paragraphs
    4. Handle blockquotes → styled paragraphs
    5. Convert strong/em → styled spans
    """
    soup = BeautifulSoup(html, 'lxml')

    # Remove forbidden tags
    for tag_name in ('script', 'style', 'iframe'):
        for el in soup.find_all(tag_name):
            el.decompose()

    # h1 → h2 (WeChat doesn't allow h1)
    for h1 in soup.find_all('h1'):
        h1.name = 'h2'

    # div → p
    for div in soup.find_all('div'):
        div.name = 'p'

    # <pre><code> → styled <p> (code block)
    for pre in soup.find_all('pre'):
        code = pre.find('code')
        code_text = code.get_text() if code else pre.get_text()
        p = soup.new_tag('p')
        # Preserve line breaks in code
        p.string = code_text
        p['style'] = STYLES['code_block']
        pre.replace_with(p)

    # Inline <code> → styled <span>
    for code in soup.find_all('code'):
        span = soup.new_tag('span')
        span.string = code.get_text()
        span['style'] = STYLES['code_inline']
        code.replace_with(span)

    # <blockquote> → styled <p>
    for bq in soup.find_all('blockquote'):
        p = soup.new_tag('p')
        p.string = bq.get_text()
        p['style'] = STYLES['blockquote']
        bq.replace_with(p)

    # <strong>/<b> → styled <span>
    for tag in soup.find_all(['strong', 'b']):
        span = soup.new_tag('span')
        span.string = tag.get_text()
        span['style'] = 'font-weight: bold;'
        tag.replace_with(span)

    # <em>/<i> → styled <span>
    for tag in soup.find_all(['em', 'i']):
        span = soup.new_tag('span')
        span.string = tag.get_text()
        span['style'] = 'font-style: italic;'
        tag.replace_with(span)

    return soup


def apply_styles(soup):
    """Apply default inline styles to all elements."""
    style_map = {
        'h2': STYLES['h2'],
        'h3': STYLES['h3'],
        'p': STYLES['p'],
        'li': STYLES['li'],
        'table': STYLES['table'],
        'th': STYLES['th'],
        'td': STYLES['td'],
        'a': STYLES['a'],
    }

    for tag_name, style in style_map.items():
        for el in soup.find_all(tag_name):
            existing = el.get('style', '')
            if existing:
                # Don't overwrite manually set styles (e.g., code blocks, blockquotes)
                continue
            el['style'] = style

    return soup


def clean_attributes(soup):
    """Remove class, id, and non-allowed CSS properties."""
    for tag in soup.find_all(True):
        # Remove class and id
        for attr in ('class', 'id'):
            if attr in tag.attrs:
                del tag.attrs[attr]

        # Unwrap tags not in allowed list (keep their content)
        if tag.name not in ALLOWED_TAGS and tag.name not in ('html', 'head', 'body', '[document]'):
            tag.unwrap()

    return soup


# ============================================================
# MAIN CONVERTER
# ============================================================

def convert(input_path, output_path):
    """Main conversion pipeline: read → sanitize → style → clean → output."""
    path = Path(input_path)

    if not path.exists():
        print(f"❌ Error: File '{input_path}' not found.")
        return False

    ext = path.suffix.lower()

    # Step 1: Read input
    print(f"📖 Reading {path.name} ({ext})...")
    if ext == '.md':
        html = read_markdown(input_path)
    elif ext == '.docx':
        html = read_docx(input_path)
    elif ext in ('.html', '.htm'):
        with open(input_path, 'r', encoding='utf-8') as f:
            html = f.read()
    else:
        print(f"❌ Unsupported format: {ext}")
        print("   Supported: .md, .docx, .html")
        return False

    # Step 2: Sanitize
    print("🧹 Sanitizing HTML for WeChat...")
    soup = sanitize(html)

    # Step 3: Apply styles
    print("🎨 Applying WeChat styles...")
    soup = apply_styles(soup)

    # Step 4: Clean attributes
    print("✂️  Cleaning non-allowed attributes...")
    soup = clean_attributes(soup)

    # Step 5: Extract body content
    body = soup.find('body')
    if body:
        content = '\n'.join(str(child) for child in body.children if str(child).strip())
    else:
        content = str(soup)

    # Wrap in minimal HTML shell for browser preview
    output_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WeChat Article Preview</title>
</head>
<body style="max-width: 600px; margin: 0 auto; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
{content}
</body>
</html>"""

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_html)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"\n✅ Done! {output_path} ({size_kb:.1f} KB)")
    print(f"\n📋 Next steps:")
    print(f"   1. Open {output_path} in a browser to preview")
    print(f"   2. Ctrl+A → Ctrl+C (select all, copy)")
    print(f"   3. Go to mp.weixin.qq.com → create new article")
    print(f"   4. Ctrl+V (paste into editor)")
    print(f"   5. Upload images via WeChat media library if needed")
    print(f"   6. Preview on phone → publish!")

    return True


def main():
    if len(sys.argv) < 3:
        print("WeChat Publisher — Starter Kit")
        print("=" * 40)
        print()
        print("Usage: python convert_to_wechat.py <input> <output>")
        print()
        print("Supported input formats:")
        print("  .md    — Markdown")
        print("  .docx  — Word document")
        print("  .html  — Existing HTML (will be sanitized)")
        print()
        print("Example:")
        print("  python convert_to_wechat.py article.md wechat.html")
        sys.exit(1)

    success = convert(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
