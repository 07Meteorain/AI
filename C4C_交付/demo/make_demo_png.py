"""把真实终端输出渲染成 demo 截图（PNG），用于 C4 交付物。
数据来源：demo/out/terminal_output.txt —— 脚本真实联网运行的结果，非伪造。
"""
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
src = BASE / 'out' / 'terminal_output.txt'
dst = BASE / 'Meteorain_C4_demo_终端输出.png'

FONT_CANDIDATES = [
    'C:/Windows/Fonts/consola.ttf',
    'C:/Windows/Fonts/DejaVuSansMono.ttf',
    'C:/Windows/Fonts/arial.ttf',
]
CN_CANDIDATES = [
    'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/simsun.ttc',
]


def pick(cands):
    for c in cands:
        if Path(c).exists():
            return c
    return None


mono = pick(FONT_CANDIDATES)
cnp = pick(CN_CANDIDATES)
fsize = 15
font = ImageFont.truetype(mono, fsize) if mono else ImageFont.load_default()
cfont = ImageFont.truetype(cnp, fsize) if cnp else font

text = src.read_text(encoding='utf-8', errors='replace')
lines = text.splitlines()

# 中西文混排宽度：用等宽字号近似，标题行单独放大
W = 1500
PAD = 28
LH = 22
title_h = 78
H = title_h + PAD * 2 + LH * len(lines) + 20

BG = '#0d1117'
FG = '#c9d1d9'
GUT = '#30363d'
COL = {
    'FABRICATED': '#ff7b72',
    'PARTIAL': '#ffa657',
    'VERIFIED': '#3fb950',
    'UNCHECKED': '#8b949e',
}
HDR = '#58a6ff'

img = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(img)

# 标题栏
d.rectangle([0, 0, W, title_h], fill='#161b22')
d.line([(0, title_h), (W, title_h)], fill=GUT, width=1)
d.text((PAD, 16), 'citation-truth-auditor — 真实运行输出', font=cfont,
       fill=HDR)
d.text((PAD, 40), f'python scripts/citation_auditor.py demo/sample_refs.bib --fix --json',
       font=font, fill='#8b949e')
for i, c in enumerate(['#ff5f56', '#ffbd2e', '#27c93f']):
    d.ellipse([W - 90 + i * 26, 22, W - 76 + i * 26, 36], fill=c)

y = title_h + PAD
for ln in lines:
    col = FG
    if re.search(r'\[(VERIFIED|PARTIAL|FABRICATED|UNCHECKED)\]', ln):
        for k, v in COL.items():
            if f'[{k}]' in ln:
                col = v
                break
    elif ln.startswith('=') or ln.startswith('-'):
        col = GUT
    elif ln.startswith('汇总') or ln.startswith('输入文件') or ln.startswith('共审计'):
        col = HDR
    elif '⚠' in ln or '编造引用' in ln:
        col = COL['FABRICATED']
    # 中文用中文字体渲染
    if re.search(r'[\u4e00-\u9fff]', ln):
        d.text((PAD, y), ln, font=cfont, fill=col)
    else:
        d.text((PAD, y), ln, font=font, fill=col)
    y += LH

img.save(dst)
print('saved', dst, img.size)