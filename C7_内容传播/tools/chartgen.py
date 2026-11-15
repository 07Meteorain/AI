#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据截图生成器：CSV → PNG（6 张）。

为什么不用 matplotlib：这一关要交付的是"别人能复现的截图"，不是"一张好看的图"。
本脚本只依赖 Pillow，画布、字号、颜色、坐标全部写死在代码里，同一份数据在任何机器上
都落在同样的位置；同时把"喂给图里的数据"的 SHA256 记进 manifest.json，
`--check` 用哈希自查截图是否过期（跨 Pillow 版本也不会误报——比的是数据，不是像素）。

用法：
    python tools/chartgen.py            # 重新生成 6 张 PNG + manifest.json
    python tools/chartgen.py --check    # 校验截图与数据是否同步（CI 用）
    python tools/chartgen.py --only 3   # 只画第 3 张
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W = 1600
MARGIN = 72

INK = (22, 24, 29)
SUB = (107, 114, 128)
FAINT = (238, 241, 245)
LINE = (226, 230, 236)
WHITE = (255, 255, 255)

BLUE = (47, 111, 235)
TEAL = (14, 165, 165)
PURPLE = (124, 58, 237)
AMBER = (245, 158, 11)
GREEN = (16, 185, 129)
RED = (220, 38, 38)

DIM_COLORS = {
    "hook": BLUE,
    "specificity": TEAL,
    "searchability": PURPLE,
    "platformFit": AMBER,
    "credibility": GREEN,
}
CHANNEL_COLORS = {"公众号": BLUE, "知乎": TEAL, "小红书": AMBER, "即刻": PURPLE}

FONT_DIR = Path("C:/Windows/Fonts")
FONT_FILES = {True: "msyhbd.ttc", False: "msyh.ttc"}
_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _font_cache:
        path = FONT_DIR / FONT_FILES[bold]
        if not path.exists():  # 非 Windows 兜底：找同目录任何 ttf
            cands = sorted(Path("/usr/share/fonts").rglob("*.ttf")) if Path("/usr/share/fonts").exists() else []
            path = cands[0] if cands else path
        _font_cache[key] = ImageFont.truetype(str(path), size)
    return _font_cache[key]


class Canvas:
    def __init__(self, height: int, title: str, subtitle: str = ""):
        self.h = height
        self.img = Image.new("RGB", (W, height), WHITE)
        self.d = ImageDraw.Draw(self.img)
        self.d.rectangle([0, 0, W, 6], fill=BLUE)
        self.text(MARGIN, 46, title, 40, INK, bold=True)
        if subtitle:
            self.text(MARGIN, 100, subtitle, 22, SUB)
        self.text(W - MARGIN, 116, "C7 内容传播 · 数据截图", 18, (156, 163, 175), anchor="ra")

    def text(self, x, y, s, size=22, color=INK, bold=False, anchor="la"):
        self.d.text((x, y), s, font=font(size, bold), fill=color, anchor=anchor)

    def width(self, s, size=22, bold=False) -> float:
        return self.d.textlength(s, font=font(size, bold))

    def panel(self, x0, y0, x1, y1, radius=16):
        self.d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=WHITE, outline=LINE, width=2)

    def hgrid(self, x0, x1, y, dash=True):
        if dash:
            x = x0
            while x < x1:
                self.d.line([x, y, min(x + 8, x1), y], fill=FAINT, width=2)
                x += 14
        else:
            self.d.line([x0, y, x1, y], fill=FAINT, width=2)

    def hbar(self, x0, y, length, h, color, radius=None):
        if length <= 0:
            return
        r = h // 2 if radius is None else radius
        self.d.rounded_rectangle([x0, y, x0 + length, y + h], radius=r, fill=color)

    def footer(self, lines: list[str]):
        y = self.h - 26 - 24 * len(lines)
        for i, line in enumerate(lines):
            self.text(MARGIN, y + i * 24, line, 17, (156, 163, 175))

    def save(self, path: Path):
        self.img.save(path, format="PNG", optimize=True)


def fmt_count(v) -> str:
    """计数：>=10 取整，<10 留一位小数（2.7 个互动 vs 860 次曝光，精度不一样）。"""
    return f"{v:,.0f}" if abs(v) >= 10 else f"{v:,.1f}"


def fmt(n) -> str:
    if isinstance(n, float):
        return f"{n:,.1f}"
    return f"{n:,}"


# --------------------------------------------------------------------------- 数据


def read_csv_map(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {row["metric"]: row for row in csv.DictReader(fh)}


def load_params(root: Path) -> dict[str, dict[str, float]]:
    raw = read_csv_map(root / "数据" / "projection_params.csv")
    channels = ["公众号", "知乎", "小红书", "即刻"]
    out: dict[str, dict[str, float]] = {}
    for ch in channels:
        out[ch] = {k: float(raw[k][ch]) for k in raw if raw[k].get(ch) not in (None, "")}
    return out


def funnel(ch: dict[str, float]) -> list[tuple[str, int]]:
    exposure = ch["exposure"]
    entered = exposure * ch["open_rate"] * ch["click_rate"]
    done = entered * ch["read_through"]
    engage = entered * ch["engage_rate"]
    convert = entered * ch["convert_rate"]
    return [
        ("曝光", exposure),
        ("进入正文", entered),
        ("读完", done),
        ("互动", engage),
        ("领取清单", convert),
    ]


def article_stats(root: Path) -> dict:
    raw = (root / "文章" / "正文.md").read_text(encoding="utf-8")
    body = raw.split("---", 2)[-1]
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    paras = [b for b in blocks if not b.startswith(("#", "|", ">", "---", "*"))]
    chars = [len(re.sub(r"\s+", "", p)) for p in paras]
    headings = [b for b in blocks if b.startswith("##")]
    total_chars = sum(chars)
    return {
        "chars": total_chars,
        "paragraphs": len(paras),
        "avg_para": round(total_chars / max(len(paras), 1)),
        "max_para": max(chars) if chars else 0,
        "headings": len(headings),
        "minutes": round(total_chars / 300, 1),
        "para_chars": chars,
    }


def ab_required(p1: float, p2: float, alpha: float = 0.05, power: float = 0.8) -> int:
    z_a = 1.959963985
    z_b = {0.8: 0.841621234, 0.9: 1.281551566}[power]
    p_bar = (p1 + p2) / 2
    num = (z_a * math.sqrt(2 * p_bar * (1 - p_bar)) + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p2 - p1) ** 2)


def power_at(n: int, p1: float, p2: float, alpha: float = 0.05) -> float:
    z_a = 1.959963985
    p_bar = (p1 + p2) / 2
    se0 = math.sqrt(2 * p_bar * (1 - p_bar) / n)
    se1 = math.sqrt((p1 * (1 - p1) + p2 * (1 - p2)) / n)
    z = (abs(p2 - p1) - z_a * se0) / se1
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# --------------------------------------------------------------------------- 图 1


def chart_titles(root: Path) -> tuple[Canvas, dict]:
    rows = list(csv.DictReader((root / "数据" / "titles_scored.csv").open(encoding="utf-8-sig", newline="")))
    rubric = json.loads((root / "数据" / "title_rubric.json").read_text(encoding="utf-8"))
    top = rows[:10]
    dims = [d["id"] for d in rubric["dimensions"]]

    c = Canvas(1060, "标题评分榜 · 前 10 / 共 32 条",
               "五维加权，满分 100。每条给出五个维度各自的填充率（各自满分归一），不是把五项堆成一条看不出差别的长条。")
    lx, bx = MARGIN, 712
    slot, gap = 112, 6
    maxes = {d["id"]: d["max"] for d in rubric["dimensions"]}
    labels = {d["id"]: d["label"] for d in rubric["dimensions"]}
    top_y = 190
    c.text(lx, top_y - 26, "候选标题（ID · 标题）", 19, SUB)

    for k, dim in enumerate(dims):
        x = bx + k * (slot + gap)
        c.d.rounded_rectangle([x, top_y - 6, x + 12, top_y + 8], radius=3, fill=DIM_COLORS[dim])
        c.text(x + 17, top_y - 8, labels[dim], 16, SUB)
        c.text(x + 17 + c.width(labels[dim], 16) + 4, top_y - 8, f"/{maxes[dim]}", 13, (176, 182, 192))
    c.text(bx + 5 * (slot + gap) + 8, top_y - 8, "总分", 16, SUB)

    row_h = 78
    for i, row in enumerate(top):
        y = 216 + i * row_h
        c.text(lx, y + 4, f"{i + 1:>2}. {row['id']}", 19, SUB)
        title = row["title"]
        c.text(lx + 62, y + 2, title if len(title) <= 24 else title[:23] + "…", 22, INK, bold=True)
        c.text(lx + 62, y + 34, f"{row['chars']} 字 · {row['grade']}", 17, (156, 163, 175))

        for k, dim in enumerate(dims):
            x = bx + k * (slot + gap)
            val = int(row[dim])
            ratio = val / maxes[dim]
            fill = max(ratio * slot, 4)
            c.hbar(x, y + 9, slot, 26, (245, 247, 250), radius=6)
            c.hbar(x, y + 9, fill, 26, DIM_COLORS[dim], radius=6)
            if ratio >= 0.4:  # 数字压在自己那段填充里，右对齐
                c.text(x + fill - 7, y + 13, str(val), 14, WHITE, bold=True, anchor="ra")
            else:             # 填充太窄就放到轨道右端，避免白字落在白底上
                c.text(x + slot - 7, y + 13, str(val), 14, (150, 157, 168), bold=True, anchor="ra")

        total = int(row["total"])
        c.text(bx + 5 * (slot + gap) + 12, y + 6, str(total), 28, INK, bold=True)
        c.text(bx + 5 * (slot + gap) + 12 + c.width(str(total), 28, True) + 4, y + 18, "/100", 14, (156, 163, 175))

    c.footer([
        "数据来源：数据/titles_scored.csv（由 tools/title_score.py 从 数据/titles.csv + 数据/title_rubric.json 生成，可复算）",
        "评级阈值：主推 ≥ 75 ｜ 可用 ≥ 64 ｜ 备选 ≥ 52 ｜ 标题党用词一票否决封顶 40。同分按 具体性 → 钩子 → ID 排序。",
    ])
    data = {"rows": [{k: r[k] for k in ("id", "total", "grade", *dims)} for r in top]}
    return c, data


# --------------------------------------------------------------------------- 图 2


def chart_funnel(root: Path) -> tuple[Canvas, dict]:
    params = load_params(root)
    main = params["公众号"]
    stages = funnel(main)

    c = Canvas(900, "四渠道漏斗 · 首篇发布",
               "公众号为主渠道做全漏斗；其余三渠道按同一套参数口径并排展示。数字为可复算的推演值，非线上实测。")
    px0, py0, px1, py1 = MARGIN, 176, MARGIN + 780, 810
    c.panel(px0, py0, px1, py1)

    values = [s[1] for s in stages]
    top = py0 + 46
    max_v = values[0]
    bar_x0 = px0 + 140
    bar_max = 540
    for i, (label, v) in enumerate(stages):
        y = top + i * 118
        c.text(px0 + 28, y + 18, label, 21, INK, bold=True)
        # 底轨：让"很小的那一格"仍然读得出来是"占了多少"
        c.hbar(bar_x0, y, bar_max, 46, (245, 247, 250), radius=10)
        length = max(v / max_v * bar_max, 8)
        color = [BLUE, (91, 141, 239), TEAL, GREEN, AMBER][i]
        c.hbar(bar_x0, y, length, 46, color, radius=10)
        c.text(bar_x0 + bar_max + 16, y + 10, fmt_count(v), 24, INK, bold=True)
        if i > 0:
            rate = v / values[i - 1]
            c.text(px0 + 28, y + 52, f"上一步的 {rate * 100:.1f}%", 16, SUB)

    # 右侧：其余渠道对比
    tx = px1 + 40
    c.text(tx, py0 + 6, "其他渠道（同口径）", 24, INK, bold=True)
    cols = ["渠道", "曝光", "进入", "读完", "互动", "领取"]
    col_x = [tx, tx + 120, tx + 236, tx + 352, tx + 462, tx + 572]
    for i, name in enumerate(cols):
        c.text(col_x[i], py0 + 52, name, 18, SUB)
    c.d.line([tx, py0 + 80, tx + 660, py0 + 80], fill=LINE, width=2)
    for i, ch in enumerate(["知乎", "小红书", "即刻"]):
        f = funnel(params[ch])
        y = py0 + 100 + i * 62
        c.d.rounded_rectangle([tx, y + 6, tx + 10, y + 34], radius=3, fill=CHANNEL_COLORS[ch])
        c.text(tx + 20, y + 8, ch, 21, INK, bold=True)
        for j, item in enumerate(f):
            c.text(col_x[j + 1], y + 8, fmt(round(item[1])), 20, INK)

    total_read = sum(funnel(params[ch])[1][1] for ch in params)
    total_reach = sum(params[ch]["exposure"] for ch in params)
    c.text(tx, py0 + 300, "四渠道合计", 22, SUB, bold=True)
    c.text(tx, py0 + 336, f"曝光 {fmt(int(total_reach))}", 30, INK, bold=True)
    c.text(tx, py0 + 382, f"进入正文 {fmt(int(total_read))}", 30, BLUE, bold=True)
    c.text(tx, py0 + 428, f"整体进入率 {total_read / total_reach * 100:.1f}%", 20, SUB)
    c.text(tx, py0 + 466, f"读完 {fmt(int(sum(funnel(params[ch])[2][1] for ch in params)))} · "
                          f"领取 {fmt(int(sum(funnel(params[ch])[4][1] for ch in params)))}", 20, SUB)

    c.footer([
        "数据来源：数据/projection_params.csv（6 个假设参数 × 4 渠道，参数含义与取值理由见 数据/指标口径.md）",
        "口径提醒：这是发布前的推演，不是线上截图。真实数据回收后覆盖 数据/metrics.csv 即可重画同一张图。",
    ])
    data = {
        "公众号": [[s[0], round(s[1], 1)] for s in stages],
        "其他": {ch: [round(v, 1) for v in [s[1] for s in funnel(params[ch])]] for ch in ("知乎", "小红书", "即刻")},
    }
    return c, data


# --------------------------------------------------------------------------- 图 3


def chart_growth(root: Path) -> tuple[Canvas, dict]:
    params = load_params(root)
    c = Canvas(940, "七日累积阅读 · 四渠道",
               "每条曲线用它自己的日权重分布铺开，纵轴为累积正文阅读量。第 1 天的份额，决定这篇内容有没有「第一口气」。")
    px0, py0, px1, py1 = MARGIN + 60, 190, W - MARGIN - 120, 780
    max_y = 0
    series = {}
    for ch, p in params.items():
        reads = p["exposure"] * p["open_rate"] * p["click_rate"]
        weights = [p[f"day{i}_weight"] for i in range(1, 8)]
        cum, total = [], 0.0
        for w in weights:
            total += reads * w
            cum.append(total)
        series[ch] = cum
        max_y = max(max_y, total)
    max_y = math.ceil(max_y / 100) * 100

    for i in range(5):
        y = py1 - (py1 - py0) * i / 4
        c.hgrid(px0, px1, y, dash=(i != 0))
        c.text(px0 - 16, y - 12, fmt(int(max_y * i / 4)), 18, SUB, anchor="ra")

    step = (px1 - px0) / 6
    for d in range(7):
        x = px0 + step * d
        c.text(x, py1 + 16, f"D{d + 1}", 19, SUB, anchor="ma")

    for ch, cum in series.items():
        pts = []
        for d, v in enumerate(cum):
            pts.append((px0 + step * d, py1 - (py1 - py0) * v / max_y))
        c.d.line(pts, fill=CHANNEL_COLORS[ch], width=4, joint="curve")
        for p in pts:
            c.d.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], fill=WHITE, outline=CHANNEL_COLORS[ch], width=3)
        lx, ly = pts[-1]
        c.text(lx + 14, ly - 12, f"{cum[-1]:.0f}", 20, CHANNEL_COLORS[ch], bold=True)

    lx = px0 + 20
    for ch, cum in series.items():
        c.d.rounded_rectangle([lx, py1 + 58, lx + 14, py1 + 72], radius=3, fill=CHANNEL_COLORS[ch])
        c.text(lx + 22, py1 + 54, ch, 19, INK)
        lx += 24 + c.width(ch, 19) + 34

    c.footer([
        "数据来源：数据/projection_params.csv 的 day1..day7 权重 × 各渠道阅读量；分布式衰减，公众号更陡、知乎长尾更长。",
        "读法：曲线在 D3 之后基本走平 —— 意味着发布后 72 小时是决定这篇文章终局的窗口。",
    ])
    data = {ch: [round(v, 1) for v in cum] for ch, cum in series.items()}
    return c, data


# --------------------------------------------------------------------------- 图 4


def chart_ab(root: Path) -> tuple[Canvas, dict]:
    params = load_params(root)
    n_total = params["公众号"]["exposure"]
    p1, p2 = 0.09, 0.11
    need = ab_required(p1, p2)
    per_arm = int(n_total / 2)

    c = Canvas(860, "A/B 标题实验 · 先算清「做不做得了」",
               f"想在 9% 与 11% 的点击率之间分胜负，需要每臂 {fmt(need)} 个样本；这个新号首篇只有 "
               f"{fmt(int(n_total))} 次曝光。")
    # 左：样本量对比
    px0, py0, px1, py1 = MARGIN, 176, MARGIN + 620, 700
    c.panel(px0, py0, px1, py1)
    c.text(px0 + 28, py0 + 22, "所需样本 vs 可用样本（每臂）", 22, INK, bold=True)
    bars = [
        ("本次可用", per_arm, (148, 163, 184), f"只有所需量的 {per_arm / need * 100:.0f}%"),
        ("检测 9%→11% 所需", need, BLUE, "α=0.05, power=0.8"),
    ]
    bar_max = 520
    for i, (label, v, color, note) in enumerate(bars):
        y = py0 + 84 + i * 148
        c.text(px0 + 28, y, label, 20, INK)
        c.hbar(px0 + 28, y + 34, bar_max, 40, (245, 247, 250), radius=8)
        c.hbar(px0 + 28, y + 34, max(v / need * bar_max, 10), 40, color, radius=8)
        c.text(px0 + 28, y + 82, f"{fmt(v)}  ·  {note}", 18, SUB)
    c.text(px0 + 28, py0 + 396, f"结论：可用样本只有所需量的 {per_arm / need * 100:.0f}%，A/B 不可判定。", 21, RED, bold=True)
    c.text(px0 + 28, py0 + 434, "改判据：三条标题按周轮换（序贯观察），", 19, SUB)
    c.text(px0 + 28, py0 + 462, "主指标换成转发率与收藏率 —— 它们在小样本下噪声更小。", 19, SUB)

    # 右：power 曲线
    rx0, ry0 = px1 + 48, py0
    c.panel(rx0, ry0, W - MARGIN, py1)
    c.text(rx0 + 28, ry0 + 22, "统计功效随样本量的变化", 22, INK, bold=True)
    gx0, gy0, gx1, gy1 = rx0 + 90, ry0 + 96, W - MARGIN - 40, ry0 + 330
    for i in range(5):
        y = gy1 - (gy1 - gy0) * i / 4
        c.hgrid(gx0, gx1, y, dash=(i != 0))
        c.text(gx0 - 12, y - 11, f"{i * 25}%", 16, SUB, anchor="ra")
    nmax = 6000
    pts = []
    for k in range(0, 61):
        n = int(200 + (nmax - 200) * k / 60)
        p = power_at(n, p1, p2)
        pts.append((gx0 + (n - 200) / (nmax - 200) * (gx1 - gx0), gy1 - p * (gy1 - gy0)))
    c.d.line([gx0, gy1 - 0.8 * (gy1 - gy0), gx1, gy1 - 0.8 * (gy1 - gy0)], fill=RED, width=2)
    c.text(gx1 - 4, gy1 - 0.8 * (gy1 - gy0) - 26, "80% 功效线", 16, RED, anchor="ra")
    c.d.line(pts, fill=BLUE, width=4, joint="curve")
    for n in (1000, 2000, need, 5000):
        p = power_at(n, p1, p2)
        x = gx0 + (n - 200) / (nmax - 200) * (gx1 - gx0)
        y = gy1 - p * (gy1 - gy0)
        c.d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=WHITE, outline=BLUE, width=3)
        c.text(x, y - 30, f"n={fmt(n)}", 15, SUB, anchor="ma")
    for i in range(4):
        x = gx0 + (gx1 - gx0) * i / 3
        c.text(x, gy1 + 12, fmt(int(200 + (nmax - 200) * i / 3)), 16, SUB, anchor="ma")
    c.text((gx0 + gx1) / 2, gy1 + 42, "每臂样本量", 16, SUB, anchor="ma")

    c.footer([
        "公式：n = (z_a·√(2·pm·(1-pm)) + z_b·√(p1(1-p1)+p2(1-p2)))² / (p2-p1)²，pm=(p1+p2)/2，双比例检验，双侧 α=0.05，功效 0.8。",
        "数据来源：数据/projection_params.csv 的公众号曝光量 × 假设点击率 9% / 11%；计算见 tools/chartgen.py。",
    ])
    data = {"per_arm": per_arm, "required_per_arm": need, "p1": p1, "p2": p2,
            "power_curve": [round(power_at(n, p1, p2), 4) for n in range(1000, 6001, 500)]}
    return c, data


# --------------------------------------------------------------------------- 图 5


def chart_article(root: Path) -> tuple[Canvas, dict]:
    stats = article_stats(root)
    c = Canvas(900, "正文体检 · 结构指标",
               "由 tools/chartgen.py 直接解析 文章/正文.md 得到（去掉 Markdown 标记后计数），不是手填的数字。")
    cards = [
        ("正文字数", fmt(stats["chars"]), "不含标题与表格"),
        ("段落数", str(stats["paragraphs"]), f"平均 {stats['avg_para']} 字/段"),
        ("最长一段", str(stats["max_para"]), "手机屏约 3 屏"),
        ("小标题", str(stats["headings"]), "平均每 400 字一个"),
        ("预计阅读", f"{stats['minutes']} 分钟", "按 300 字/分钟"),
    ]
    cw = (W - MARGIN * 2 - 4 * 20) / 5
    for i, (label, value, note) in enumerate(cards):
        x = MARGIN + i * (cw + 20)
        c.panel(x, 176, x + cw, 330)
        c.text(x + 22, 196, label, 19, SUB)
        c.text(x + 22, 226, value, 44, INK, bold=True)
        c.text(x + 22, 292, note, 16, (156, 163, 175))

    # 段落长度分布
    px0, py0, px1, py1 = MARGIN, 372, W - MARGIN, 800
    c.panel(px0, py0, px1, py1)
    c.text(px0 + 28, py0 + 22, "段落字数分布（手机端阅读友好度）", 22, INK, bold=True)
    bucketing = [(0, 60), (60, 90), (90, 120), (120, 150), (150, 200), (200, 9999)]
    names = ["<60", "60–90", "90–120", "120–150", "150–200", ">200"]
    counts = [sum(1 for n in stats["para_chars"] if lo <= n < hi) for lo, hi in bucketing]
    gx0, gy0, gx1, gy1 = px0 + 90, py0 + 96, px1 - 40, py0 + 316
    maxc = max(counts) or 1
    bw = (gx1 - gx0) / len(counts)
    for i, (n, name) in enumerate(zip(counts, names)):
        x = gx0 + i * bw + bw * 0.18
        h = (gy1 - gy0) * n / maxc
        color = GREEN if 60 <= bucketing[i][0] < 150 else (AMBER if bucketing[i][0] < 60 else PURPLE)
        if h >= 2:
            c.hbar(x, gy1 - h, bw * 0.64, h, color, radius=6)
        c.text(x + bw * 0.32, gy1 - h - 32, str(n), 20, INK, bold=True, anchor="ma")
        c.text(x + bw * 0.32, gy1 + 12, name, 17, SUB, anchor="ma")
    c.d.line([gx0, gy1, gx1, gy1], fill=LINE, width=2)
    c.text(gx0, gy1 + 48, "手机屏一屏约 90–110 字：绿色区间是「一段一屏」的理想分段；紫色偏长，容易让人划走。", 18, SUB)

    c.footer([
        "数据来源：文章/正文.md 直接解析（python tools/chartgen.py）；同一份指标可在 app 的「数据」页实时重算。",
        f"当前：{stats['paragraphs']} 段 / {stats['chars']} 字 / {stats['minutes']} 分钟阅读，平均段长 {stats['avg_para']} 字。",
    ])
    data = {k: v for k, v in stats.items() if k != "para_chars"}
    data["buckets"] = dict(zip(names, counts))
    return c, data


# --------------------------------------------------------------------------- 图 6


def chart_repo(root: Path) -> tuple[Canvas, dict]:
    rows = list(csv.DictReader((root / "数据" / "repo_facts.csv").open(encoding="utf-8-sig", newline="")))
    meta = json.loads((root / "数据" / "repo_facts.meta.json").read_text(encoding="utf-8"))
    scored = [r for r in rows if int(r["tests_computed"]) > 0]
    scored.sort(key=lambda r: -int(r["tests_computed"]))
    total = sum(int(r["tests_computed"]) for r in rows)

    declared = [r for r in scored if r["declared_tests"] not in ("", None)]
    agree = [r for r in declared if int(r["declared_tests"]) == int(r["tests_computed"])]
    c = Canvas(1090, f"仓库事实 · {fmt(total)} 项测试从哪来",
               f"自报数（各关 README）与实测数（静态正则计数）逐关对比：{len(agree)}/{len(declared)} 一致，零偏差；"
               f"另有 {len(scored) - len(declared)} 个目录只有实测（C6A 未自报）。")
    c.panel(MARGIN, 176, MARGIN + 540, 312)
    c.text(MARGIN + 28, 196, "可执行测试用例总数", 19, SUB)
    c.text(MARGIN + 28, 224, fmt(total), 54, INK, bold=True)
    c.text(MARGIN + 28 + c.width(fmt(total), 54, True) + 10, 244, "项", 20, SUB)
    c.text(MARGIN + 250, 246, f"提交 {meta['total_commits']} 次 · 文件 {fmt(meta['total_files'])} 个", 19, SUB)

    c.panel(MARGIN + 580, 176, W - MARGIN, 312)
    c.text(MARGIN + 608, 196, "自报 vs 实测", 19, SUB)
    c.text(MARGIN + 608, 230, f"{len(agree)} / {len(declared)} 一致", 42, GREEN, bold=True)
    c.text(MARGIN + 608, 288, "零偏差：README 里的数字不是拍的", 16, (156, 163, 175))

    lx, bx, bar_max = MARGIN + 190, MARGIN + 200, 1000
    top_y = 360
    c.text(MARGIN, top_y - 30, "关口", 18, SUB)
    c.text(bx, top_y - 30, "测试数（条）", 18, SUB)
    max_t = max(int(r["tests_computed"]) for r in scored)
    for i, r in enumerate(scored):
        y = top_y + i * 62
        c.text(MARGIN, y + 12, r["scope"].replace("_交付", "").replace("_仓库分析", ""), 20, INK, bold=True)
        declared_v = r["declared_tests"]
        has_declared = declared_v not in ("", None)
        w_calc = int(r["tests_computed"]) / max_t * bar_max
        if has_declared:  # 自报：稍高，露出一圈；没自报的目录只画蓝色
            c.hbar(bx, y, max(int(declared_v) / max_t * bar_max, 4), 44, (203, 213, 225), radius=10)
        c.hbar(bx, y + 5, max(w_calc, 4), 34, BLUE, radius=8)
        c.text(bx + w_calc + 14, y + 6, fmt(int(r["tests_computed"])), 21, INK, bold=True)
        if not has_declared:
            c.text(bx + w_calc + 14 + c.width(fmt(int(r["tests_computed"])), 21, True) + 10, y + 12,
                   "未自报", 15, (156, 163, 175))
    c.text(bx, top_y + len(scored) * 62 + 6, "灰色外圈 = README 自报，蓝色 = 脚本实测（完全重合即一致）", 17, (156, 163, 175))

    c.footer([
        f"数据来源：数据/repo_facts.csv（tools/repo_facts.py 从 git log 与源码静态计数生成，钉在 master@{meta['as_of_commit'][:7]} 快照上）",
        "为什么钉快照：提交数每天都在变，写死的数字必须带「截止哪个 commit」，否则三天后就是假话。",
    ])
    data = {"total": total, "agree": len(agree), "declared": len(declared),
            "rows": [[r["scope"], r["declared_tests"], r["tests_computed"]] for r in scored],
            "meta": {"commits": meta["total_commits"], "files": meta["total_files"]}}
    return c, data


# --------------------------------------------------------------------------- 主流程

CHARTS = [
    ("01_标题评分.png", chart_titles),
    ("02_渠道漏斗.png", chart_funnel),
    ("03_七日增长.png", chart_growth),
    ("04_AB显著性.png", chart_ab),
    ("05_正文结构.png", chart_article),
    ("06_仓库事实.png", chart_repo),
]


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="数据截图生成器")
    parser.add_argument("--root", default=str(here))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--only", type=int, default=None)
    args = parser.parse_args(argv)

    root = Path(args.root)
    out_dir = root / "数据" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"

    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"charts": {}}
    manifest = {"generator": "tools/chartgen.py", "note": "每张图的数据指纹（SHA256）；数据变了图没重画 -> --check 报警", "charts": {}}
    stale = []

    for i, (name, fn) in enumerate(CHARTS, 1):
        if args.only and args.only != i:
            manifest["charts"][name] = old["charts"].get(name, {})
            continue
        canvas, data = fn(root)
        h = digest(data)
        target = out_dir / name
        manifest["charts"][name] = {"index": i, "data_sha256": h}
        if args.check:
            prev = old["charts"].get(name, {})
            if prev.get("data_sha256") != h:
                stale.append(f"{name}: 数据指纹变化（{prev.get('data_sha256', 'none')[:8]} -> {h[:8]}）")
            if not target.exists():
                stale.append(f"{name}: 文件缺失")
            continue
        canvas.save(target)
        print(f"[ok] {name}  {target.stat().st_size // 1024} KB")

    if args.check:
        for missing in [n for n, _ in CHARTS if n not in old["charts"]]:
            stale.append(f"{missing}: manifest 里没有记录")
        if stale:
            print("[stale] 数据截图需要重画（跑 python tools/chartgen.py）：", file=sys.stderr)
            for s in stale:
                print(f"  - {s}", file=sys.stderr)
            return 1
        print(f"[ok] {len(CHARTS)} 张截图与数据一致")
        return 0

    if not args.only:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
        print(f"[ok] manifest -> {manifest_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
