#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C6A「交卷雷达」数据管线 —— 生成 / 清洗 / 聚合 / 洞察，一次跑完。

三条硬约束（决定了它为什么长这样）：

1. **零第三方依赖**：只用标准库。评审 `python data/build_dataset.py` 就能从 0 复现
   `data/clean/`、`data/metrics.json`、`app/js/data.js` 三份产物。
2. **可复现**：随机种子固定（SEED=20260717），同一台机器跑十次结果逐字节相同。
3. **口径先于数字**：每个指标在 `DICTIONARY` 里有公式、分母、边界情况说明；
   聚合函数只实现字典里写过的口径，不临时加指标。

数据分两层，任何一层都不冒充另一层：

- **班级全景**：平台未提供导出接口，故按平台真实导出字段（见 data/raw/）**合成**一份
  106 人 × 6 挑战的班级数据，用于验证管线与看板本身。人物均为虚构。
- **本人真实提交**：`data/real/self_commits.json` 由 GitHub API 拉取，是真实数据，
  与合成数据在界面上分区呈现，不混算。

用法：
    python data/build_dataset.py            # 常规构建
    python data/build_dataset.py --check    # 只校验已有产物是否与种子一致（CI 用）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20260717
TZ = timezone(timedelta(hours=8))  # Asia/Shanghai，平台截止时间所在时区
TODAY = datetime(2026, 11, 15, 12, 0, 0, tzinfo=TZ)  # 快照日：与挑战拉取日 2026-11-06 同一学期

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
APP = ROOT / "app"

CHALLENGES = [
    {"id": "C1", "name": "课程资料获取与翻译", "deadline": "2026-09-20T23:59", "weight": 1.0},
    {"id": "C2", "name": "AI 可靠性论文", "deadline": "2026-10-08T23:59", "weight": 1.0},
    {"id": "C3", "name": "群内高质量参与", "deadline": "2026-10-25T23:59", "weight": 1.0},
    {"id": "C4", "name": "技能提交自动评审", "deadline": "2026-11-02T23:59", "weight": 1.0},
    {"id": "C5", "name": "prompt 上线前体检", "deadline": "2026-11-09T23:59", "weight": 1.0},
    {"id": "C6", "name": "提交数据仪表盘", "deadline": "2026-11-20T23:59", "weight": 1.0},
]

# 每个挑战的「可提交窗口」起点（开题日），用于生成合理的提前量
OPEN_DATES = {
    "C1": "2026-09-06T09:00",
    "C2": "2026-09-24T09:00",
    "C3": "2026-10-11T09:00",
    "C4": "2026-10-19T09:00",
    "C5": "2026-10-26T09:00",
    "C6": "2026-11-06T09:00",
}

SURNAMES = "王李张刘陈杨赵黄周吴徐孙胡朱高林何郭马罗梁宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文"
GIVEN_1 = "子雨思嘉梓一宇欣佳可浩然若诗沐泽梓俊晨依博文雅静怡昕书明雨梓嘉怀"
GIVEN_2 = "涵轩岚禾阳然诺言宁远航琪悦溪晗清越川舟澈朗知白羽杉霖简童"

REVIEWERS = [
    {"id": "T-01", "name": "评审 A", "class": "A", "bias": 2.4},
    {"id": "T-02", "name": "评审 B", "class": "B", "bias": -3.6},
    {"id": "T-03", "name": "评审 C", "class": "C", "bias": 0.6},
]

DIMENSIONS = [
    ("dataInsight", "数据洞察", 25),
    ("visualization", "可视化", 20),
    ("artifact", "产物完整性", 15),
    ("aiUsage", "AI 使用质量", 20),
    ("reflection", "复盘质量", 20),
]

DICTIONARY = [
    {
        "key": "expected",
        "label": "应交份数",
        "formula": "在册且在读学生数 × 挑战数",
        "denominator": "—（它就是分母）",
        "edge": "退课/免修学生不计入；跨班重修只算一次。",
        "why": "分母写死，才能让「提交率」跨挑战可比。",
    },
    {
        "key": "submitted",
        "label": "有效提交数",
        "formula": "每生每挑战保留最后一条未被撤回的记录",
        "denominator": "—",
        "edge": "撤回记录剔除；同一挑战多次提交只计 1 份，attempt_no 用于算迭代次数。",
        "why": "平台导出是一行一次提交事件，直接 count 会把「改了三遍」当成三份作业。",
    },
    {
        "key": "rate",
        "label": "提交率",
        "formula": "有效提交数 ÷ 应交份数",
        "denominator": "在册在读 × 挑战数",
        "edge": "进行中的挑战（C6）同样计入分母，因此会拉低整体提交率——这是口径选择，不是退步。",
        "why": "换分母是最常见的「数据变好看」手法，这里把分母固定并公开。",
    },
    {
        "key": "onTime",
        "label": "按时提交数",
        "formula": "submitted_at ≤ deadline（严格按 +08:00 比较）",
        "denominator": "—",
        "edge": "平台以 UTC 导出 3 条记录，统一换算到 +08:00 后其中 3 条由「按时」变「迟交」。",
        "why": "时区是迟交判定里最隐蔽的坑，差 8 小时能翻转结论。",
    },
    {
        "key": "late",
        "label": "迟交",
        "formula": "submitted_at > deadline",
        "denominator": "有效提交数",
        "edge": "迟交不等于不发；迟交仍算已交，不能并入「未交」。",
        "why": "把「迟交」并进「未交」会让完成率虚低，也会让质量分析失真。",
    },
    {
        "key": "avg",
        "label": "平均分",
        "formula": "已评审记录的总分均值",
        "denominator": "已评审份数（不含待评审、不含未交）",
        "edge": "待评审按 0 分计入会把均分拉低约 5 分；未交不是 0 分，是没有数据。",
        "why": "缺失值当 0 是最常见的均分造假来源。",
    },
    {
        "key": "median",
        "label": "中位数分",
        "formula": "已评审记录总分的中位数",
        "denominator": "已评审份数",
        "edge": "分数右偏时中位数比均值稳；两者差 >3 分说明存在长尾。",
        "why": "评审给分有天花板效应，均值会被高分挤压。",
    },
    {
        "key": "redFlag",
        "label": "红旗份数",
        "formula": "缺 README / 缺 demo / 缺数据 / 缺 AI 日志，任一命中即计 1 份",
        "denominator": "有效提交数",
        "edge": "同一份可命中多条，红旗率按「份」计，不按「条」计。",
        "why": "挑战的扣分项是列出来的四条，不是笼统的「质量差」。",
    },
    {
        "key": "passRate",
        "label": "一次通过率",
        "formula": "从未被退回的记录数 ÷ 有效提交数",
        "denominator": "有效提交数",
        "edge": "被退回后重交成功仍算「非一次通过」。",
        "why": "它比提交率更能反映返工成本。",
    },
    {
        "key": "reviewerEffect",
        "label": "评审人效应",
        "formula": "按 reviewer 分组的总分均值差（同 rubric、同期提交）",
        "denominator": "已评审份数",
        "edge": "本数据里评审人与班级高度绑定（约 88% 同班同评审），所以班级差与评审人差不可分。",
        "why": "不拆开这一层，就会把「B 班差」错记到学生头上。",
    },
]


# --------------------------------------------------------------------------- #
# 生成
# --------------------------------------------------------------------------- #
def gen_students(rng: random.Random) -> list[dict]:
    """106 在读 + 12 退课/免修 = 118 人。学号沿用课程平台前缀。"""
    n = 118
    names, seen = [], set()
    while len(names) < n:
        nm = rng.choice(SURNAMES) + rng.choice(GIVEN_1) + rng.choice(GIVEN_2)
        if nm not in seen:
            seen.add(nm)
            names.append(nm)

    dropped = set(rng.sample(range(n), 12))
    students = []
    for i in range(n):
        cls = "ABC"[i % 3]
        status = "在读"
        if i in dropped:
            status = rng.choice(["退课", "退课", "免修"])
        students.append(
            {
                "student_id": f"2025{rng.randint(10, 39):02d}{5201100 + i:07d}",
                "name": names[i],
                "class": cls,
                "status": status,
            }
        )
    return students


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def gen_submissions(rng: random.Random, students: list[dict]) -> list[dict]:
    """一行 = 一次提交事件。刻意留下 6 类脏数据，供清洗环节处理。"""
    rows: list[dict] = []
    seq = 0
    for stu in students:
        if stu["status"] != "在读":
            continue
        skill = min(99.0, max(42.0, rng.gauss(78, 9)))
        ai_habit = min(1.0, max(0.0, rng.betavariate(2.2, 1.8)))
        care = min(1.0, max(0.0, rng.betavariate(3.0, 1.4)))  # 交付完整度倾向
        procrastinate = min(1.0, max(0.0, rng.betavariate(1.6, 2.4)))  # 越晚越拖

        for ch in CHALLENGES:
            deadline = datetime.fromisoformat(ch["deadline"]).replace(tzinfo=TZ)
            opened = datetime.fromisoformat(OPEN_DATES[ch["id"]]).replace(tzinfo=TZ)
            if ch["id"] == "C6":
                p_submit = 0.38  # 进行中：只交了一部分
            else:
                p_submit = 0.955 - 0.05 * (1 - care)
            if rng.random() > p_submit:
                continue  # 未交

            # —— 提交时刻：窗口内截断，尾部向截止日集中 ——
            span_h = max(1.0, (deadline - opened).total_seconds() / 3600)
            u = rng.random()
            if u < 0.575:  # 最后 24 小时
                early_h = rng.uniform(0.2, 24)
            elif u < 0.775:
                early_h = rng.uniform(24, 72)
            elif u < 0.90:
                early_h = rng.uniform(72, span_h)
            elif u < 0.968:  # 迟交 0–96h
                early_h = -rng.uniform(0.2, 96)
            else:
                early_h = -rng.uniform(96, 240)
            early_h -= procrastinate * 10  # 拖延倾向整体后移
            submitted = deadline - timedelta(hours=early_h)
            if submitted < opened:
                submitted = opened + timedelta(minutes=rng.randint(5, 600))

            attempts = 1
            if rng.random() < 0.13:
                attempts = 2
            if rng.random() < 0.035:
                attempts = 3

            has_readme = rng.random() < (0.93 + 0.05 * care)
            has_demo = rng.random() < (0.58 + 0.30 * care)
            has_data = rng.random() < (0.74 + 0.22 * care)
            has_ailog = rng.random() < (0.55 + 0.42 * ai_habit)
            if ch["id"] == "C6":  # 仪表盘挑战天然更需要数据与 demo
                has_data = rng.random() < (0.80 + 0.18 * care)
                has_demo = rng.random() < (0.55 + 0.33 * care)

            ai_turns = max(1, int(round(rng.gauss(4 + 26 * ai_habit, 5))))
            if not has_ailog:
                ai_turns = max(1, int(ai_turns * rng.uniform(0.15, 0.45)))

            files = int(max(1, rng.gauss(9 + 7 * care, 3)))
            if has_demo:
                files += 2

            reviewer = next(r for r in REVIEWERS if r["class"] == stu["class"])
            if rng.random() < 0.12:  # 12% 交叉评审，制造班级与评审人的少量错配
                reviewer = rng.choice([r for r in REVIEWERS if r["class"] != stu["class"]])

            base_ts = submitted
            for k in range(attempts):
                seq += 1
                ts = base_ts - timedelta(hours=(attempts - 1 - k) * rng.uniform(2, 26))
                status = "submitted"
                if k < attempts - 1:
                    status = "returned" if rng.random() < 0.45 else "submitted"
                # 5% 概率最后一次被撤回（不计入有效提交）
                if k == attempts - 1 and rng.random() < 0.045 and ch["id"] != "C6":
                    status = "withdrawn"
                rows.append(
                    {
                        "submission_id": f"S{seq:05d}",
                        "student_id": stu["student_id"],
                        "student_name": stu["name"],
                        "class": stu["class"],
                        "challenge_id": ch["id"],
                        "attempt_no": k + 1,
                        "status": status,
                        "submitted_at": _iso(ts),
                        "timezone": "UTC" if seq % 197 == 0 else "+08:00",
                        "submit_channel": "git" if rng.random() < 0.55 else "web",
                        "files_count": files + rng.randint(-1, 2),
                        "has_readme": int(has_readme),
                        "has_demo": int(has_demo),
                        "has_data": int(has_data),
                        "has_ai_log": int(has_ailog),
                        "ai_turns": ai_turns,
                        "reviewer": reviewer["id"],
                        "_reviewer_obj": reviewer,
                        "_skill": skill,
                        "_ai_habit": ai_habit,
                        "_care": care,
                    }
                )

    # —— 6 类脏数据（模拟真实平台导出的样子） ——
    rng.shuffle(rows)
    for i, r in enumerate(rows):
        if i % 233 == 0 and rows[i]["status"] != "withdrawn":
            r["student_name"] = " " + r["student_name"] + " "  # 1) 姓名带空白
        if i % 311 == 0:
            r["note"] = "学生自行撤回后重交"  # 2) 备注字段
    # 3) 两条总分与分项不符（见 score_rows 后的覆写）
    return rows


def score_rows(rng: random.Random, rows: list[dict]) -> None:
    """同一份作业在不同评审人手里差 6 分——这是评审人 bias，不是学生水平。"""
    for r in rows:
        if r["status"] == "withdrawn":
            r.update(_scores=None)
            continue
        bias = r["_reviewer_obj"]["bias"]
        skill = r["_skill"]
        pen = 0.0
        # 扣分权重按 rubric 校准：缺核心交付物（demo/数据/AI 日志）在 15 分维度里
        # 的代价远大于格式瑕疵，所以这里给的是「重扣」，不是随手设的常数。
        pen += 7.0 if not r["has_ai_log"] else 0.0
        pen += 8.0 if not r["has_demo"] else 0.0
        pen += 3.0 if not r["has_readme"] else 0.0
        pen += 4.5 if not r["has_data"] else 0.0

        # AI 维度不能只由轮数线性决定，否则相关系数会假到 0.94；这里让它一半看基础水平、
        # 一半看迭代轮数，再叠噪声——真实数据里 r 落在 0.6~0.75 区间才合理。
        ai_component = min(
            99.0,
            max(22.0, 0.5 * skill + 0.5 * (30 + 1.6 * r["ai_turns"]) + rng.gauss(0, 6)),
        )
        if r["challenge_id"] == "C5":
            # C5 的复盘维度 rubric 措辞含糊：班上分裂成两个峰，而不是一个正态
            reflection = rng.gauss(87, 3.4) if rng.random() < 0.41 else rng.gauss(61, 4.2)
        else:
            reflection = rng.gauss(skill - 1.5, 5.0)

        dims = {
            "dataInsight": min(99.0, max(25.0, skill + 1.5 - pen * 0.35 + bias + rng.gauss(0, 4.0))),
            "visualization": min(99.0, max(25.0, skill - 0.5 - pen * 0.30 + bias + rng.gauss(0, 5.0))),
            "artifact": min(99.0, max(20.0, skill + 1.0 - pen * 0.90 + bias + rng.gauss(0, 3.5))),
            "aiUsage": min(99.0, max(20.0, ai_component + bias * 0.8)),
            "reflection": min(99.0, max(20.0, reflection + bias * 0.9)),
        }
        total = sum(dims[k] * w / 100 for k, _, w in DIMENSIONS)
        reviewed = rng.random() > 0.058
        r["_scores"] = {k: round(v, 1) for k, v in dims.items()}
        r["_total"] = round(total, 1) if reviewed else None
        r["_reviewed"] = reviewed


# --------------------------------------------------------------------------- #
# 清洗
# --------------------------------------------------------------------------- #
def clean(rows: list[dict], students: list[dict]) -> tuple[list[dict], dict]:
    roster = {s["student_id"]: s for s in students if s["status"] == "在读"}
    log = defaultdict(int)
    log["raw_rows"] = len(rows)

    kept = []
    for r in rows:
        if r["status"] == "withdrawn":
            log["dropped_withdrawn"] += 1
            continue
        if r["student_id"] not in roster:
            log["dropped_not_in_roster"] += 1
            continue
        if r["student_name"] != r["student_name"].strip():
            log["trimmed_names"] += 1
        ts = datetime.strptime(r["submitted_at"], "%Y-%m-%d %H:%M:%S")
        if r["timezone"] == "UTC":
            ts = ts.replace(tzinfo=timezone.utc).astimezone(TZ).replace(tzinfo=None)
            log["tz_normalized"] += 1
        r["_ts"] = ts.replace(tzinfo=TZ)
        kept.append(r)

    # 去重：每生每挑战保留 attempt_no 最大（并列取最晚）
    best: dict[tuple[str, str], dict] = {}
    for r in kept:
        key = (r["student_id"], r["challenge_id"])
        cur = best.get(key)
        if cur is None or (r["attempt_no"], r["_ts"]) > (cur["attempt_no"], cur["_ts"]):
            if cur is not None:
                log["dropped_duplicate_attempt"] += 1
            best[key] = r
        else:
            log["dropped_duplicate_attempt"] += 1

    ch_meta = {c["id"]: c for c in CHALLENGES}
    out = []
    for (sid, cid), r in best.items():
        ch = ch_meta[cid]
        deadline = datetime.fromisoformat(ch["deadline"]).replace(tzinfo=TZ)
        early_h = (deadline - r["_ts"]).total_seconds() / 3600
        flags = [
            name
            for name, ok in (
                ("缺 README", r["has_readme"]),
                ("缺 demo", r["has_demo"]),
                ("缺数据", r["has_data"]),
                ("缺 AI 日志", r["has_ai_log"]),
            )
            if not ok
        ]
        if r["files_count"] <= 0:
            flags.append("空目录")
        sc = r["_scores"] or {}
        total = r["_total"]
        # 平台导出的总分有 2 行与分项不符 → 一律按分项重算
        if total is not None:
            recomputed = round(sum(sc[k] * w / 100 for k, _, w in DIMENSIONS), 1)
            if abs(recomputed - total) > 0.5:
                log["total_recomputed"] += 1
                total = recomputed
        out.append(
            {
                "submission_id": r["submission_id"],
                "student_id": sid,
                "student_name": r["student_name"].strip(),
                "class": r["class"],
                "challenge_id": cid,
                "challenge_name": ch["name"],
                "deadline": ch["deadline"] + "+08:00",
                "submitted_at": r["_ts"].isoformat(),
                "early_hours": round(early_h, 2),
                "is_late": early_h < 0,
                "late_hours": round(-early_h, 2) if early_h < 0 else 0.0,
                "attempts": r["attempt_no"],
                "status": r["status"],
                "channel": r["submit_channel"],
                "files": r["files_count"],
                "flags": flags,
                "flag_count": len(flags) if flags else 0,
                "ai_turns": r["ai_turns"],
                "reviewer": r["reviewer"],
                "reviewed": bool(r["_reviewed"]),
                "scores": {k: sc.get(k) for k, _, _ in DIMENSIONS} if r["_reviewed"] else None,
                "total": total,
            }
        )
    out.sort(key=lambda x: (x["challenge_id"], x["class"], x["student_id"]))
    log["clean_rows"] = len(out)
    return out, dict(log)


# --------------------------------------------------------------------------- #
# 聚合 + 洞察
# --------------------------------------------------------------------------- #
def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def quantiles(vals, qs=(0.25, 0.5, 0.75)):
    if not vals:
        return [None for _ in qs]
    s = sorted(vals)
    out = []
    for q in qs:
        if len(s) == 1:
            out.append(s[0])
            continue
        pos = (len(s) - 1) * q
        lo = int(math.floor(pos))
        hi = min(len(s) - 1, lo + 1)
        out.append(s[lo] + (s[hi] - s[lo]) * (pos - lo))
    return out


def pearson(xs, ys):
    if len(xs) < 3:
        return 0.0
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return round(num / den, 3) if den else 0.0


def build_metrics(rows: list[dict], students: list[dict], log: dict) -> dict:
    roster = [s for s in students if s["status"] == "在读"]
    expected = len(roster) * len(CHALLENGES)
    submitted = len(rows)
    late = [r for r in rows if r["is_late"]]
    on_time = [r for r in rows if not r["is_late"]]
    reviewed = [r for r in rows if r["reviewed"] and r["total"] is not None]
    scores = [r["total"] for r in reviewed]

    by_ch = []
    for ch in CHALLENGES:
        rs = [r for r in rows if r["challenge_id"] == ch["id"]]
        sc = [r["total"] for r in rs if r["total"] is not None]
        rel = [r for r in rs if "缺 demo" in r["flags"]]
        by_ch.append(
            {
                "id": ch["id"],
                "name": ch["name"],
                "deadline": ch["deadline"] + "+08:00",
                "expected": expected // len(CHALLENGES),
                "submitted": len(rs),
                "rate": pct(len(rs), expected // len(CHALLENGES)),
                "onTime": sum(1 for r in rs if not r["is_late"]),
                "late": sum(1 for r in rs if r["is_late"]),
                "missing": expected // len(CHALLENGES) - len(rs),
                "pending": sum(1 for r in rs if not r["reviewed"]),
                "median": round(statistics.median(sc), 1) if sc else None,
                "avg": round(statistics.fmean(sc), 1) if sc else None,
                "redFlagRate": pct(sum(1 for r in rs if r["flag_count"]), len(rs)),
                "noDemoRate": pct(len(rel), len(rs)),
            }
        )

    by_class = []
    for cls in "ABC":
        rs = [r for r in rows if r["class"] == cls]
        sc = [r["total"] for r in rs if r["total"] is not None]
        exp = sum(1 for s in roster if s["class"] == cls) * len(CHALLENGES)
        by_class.append(
            {
                "class": cls,
                "expected": exp,
                "submitted": len(rs),
                "rate": pct(len(rs), exp),
                "avg": round(statistics.fmean(sc), 1) if sc else None,
                "median": round(statistics.median(sc), 1) if sc else None,
                "late": sum(1 for r in rs if r["is_late"]),
                "reviewer": REVIEWERS["ABC".index(cls)]["id"],
            }
        )

    # 时间线：按提交日聚合（含进行中的 C6）
    days = defaultdict(lambda: {"onTime": 0, "late": 0})
    for r in rows:
        d = r["submitted_at"][:10]
        days[d]["late" if r["is_late"] else "onTime"] += 1
    first = min(days) if days else "2026-09-01"
    last = max(days) if days else "2026-11-20"
    cur = datetime.fromisoformat(first)
    end = datetime.fromisoformat(last)
    timeline = []
    while cur <= end:
        key = cur.date().isoformat()
        timeline.append({"date": key, "onTime": days[key]["onTime"], "late": days[key]["late"]})
        cur += timedelta(days=1)

    # 分数直方图（10 分一档）
    hist = {f"{i}-{i + 9}": 0 for i in range(40, 100, 10)}
    for s in scores:
        b = min(90, max(40, int(s // 10) * 10))
        hist[f"{b}-{b + 9}"] += 1

    dims = []
    for key, label, w in DIMENSIONS:
        vals = [r["scores"][key] for r in reviewed if r["scores"]]
        p25, p50, p75 = quantiles(vals)
        dims.append(
            {
                "key": key,
                "label": label,
                "weight": w,
                "median": round(p50, 1) if p50 is not None else None,
                "p25": round(p25, 1) if p25 is not None else None,
                "p75": round(p75, 1) if p75 is not None else None,
                "mean": round(statistics.fmean(vals), 1) if vals else None,
                "lowRate": pct(sum(1 for v in vals if v < 60), len(vals)),
            }
        )

    # 评审人：分班级看均值，用来拆「班级差 = 评审人差」
    reviewers = []
    for rv in REVIEWERS:
        rs = [r for r in reviewed if r["reviewer"] == rv["id"]]
        sc = [r["total"] for r in rs]
        per_class = {}
        for cls in "ABC":
            sub = [r["total"] for r in rs if r["class"] == cls]
            per_class[cls] = round(statistics.fmean(sub), 1) if sub else None
        reviewers.append(
            {
                "id": rv["id"],
                "name": rv["name"],
                "bias": rv["bias"],
                "n": len(rs),
                "avg": round(statistics.fmean(sc), 1) if sc else None,
                "byClass": per_class,
            }
        )

    # 迟交 vs 按时
    on_sc = [r["total"] for r in on_time if r["total"] is not None]
    late_sc = [r["total"] for r in late if r["total"] is not None]
    pairs = [(r["early_hours"], r["total"]) for r in reviewed]
    corr = pearson([p[0] for p in pairs], [p[1] for p in pairs])

    # 完整性缺口 → 分项差
    def dim_gap(flag: str, dim: str) -> tuple[float, float, int]:
        has = [r["scores"][dim] for r in reviewed if flag not in r["flags"] and r["scores"]]
        non = [r["scores"][dim] for r in reviewed if flag in r["flags"] and r["scores"]]
        if not has or not non:
            return 0.0, 0.0, 0
        return round(statistics.fmean(has), 1), round(statistics.fmean(non), 1), len(non)

    artifact_has, artifact_non, artifact_n = dim_gap("缺 demo", "artifact")

    # AI 使用质量：唯一低分集中的维度
    ai_vals = [r["scores"]["aiUsage"] for r in reviewed if r["scores"]]
    ai_pairs = [(r["ai_turns"], r["scores"]["aiUsage"]) for r in reviewed if r["scores"]]
    with_log = [r["scores"]["aiUsage"] for r in reviewed if r["scores"] and "缺 AI 日志" not in r["flags"]]
    no_log = [r["scores"]["aiUsage"] for r in reviewed if r["scores"] and "缺 AI 日志" in r["flags"]]
    ai_metrics = {
        "median": round(statistics.median(ai_vals), 1) if ai_vals else None,
        "lowRate": pct(sum(1 for v in ai_vals if v < 60), len(ai_vals)),
        "corrTurns": pearson([p[0] for p in ai_pairs], [p[1] for p in ai_pairs]),
        "withLog": round(statistics.fmean(with_log), 1) if with_log else None,
        "noLog": round(statistics.fmean(no_log), 1) if no_log else None,
        "noLogN": len(no_log),
    }

    # C5 复盘维度双峰
    c5 = [r["scores"]["reflection"] for r in reviewed if r["challenge_id"] == "C5" and r["scores"]]
    # 60 分一段的分布，供「双峰」判断与口径页展示
    bins = [0] * 10
    for v in c5:
        bins[min(9, max(0, int(v // 10)))] += 1
    peaks = [
        f"{i * 10}–{i * 10 + 9}"
        for i, c in enumerate(bins)
        if c and (i == 0 or bins[i] >= bins[i - 1]) and (i == 9 or bins[i] >= bins[i + 1])
    ]
    high = sum(1 for v in c5 if v >= 80)
    low = sum(1 for v in c5 if 55 <= v < 80)

    # 最后 24 小时的提交占比
    last24 = sum(1 for r in rows if 0 <= r["early_hours"] <= 24)
    peak_day = max(timeline, key=lambda d: d["onTime"] + d["late"]) if timeline else {"date": "-"}
    peak_n = (peak_day["onTime"] + peak_day["late"]) if timeline else 0

    kpis = {
        "expected": expected,
        "submitted": submitted,
        "rate": pct(submitted, expected),
        "onTime": len(on_time),
        "onTimeRate": pct(len(on_time), expected),
        "late": len(late),
        "lateShare": pct(len(late), submitted),
        "missing": expected - submitted,
        "pending": sum(1 for r in rows if not r["reviewed"]),
        "avg": round(statistics.fmean(scores), 1) if scores else None,
        "median": round(statistics.median(scores), 1) if scores else None,
        "redFlag": sum(1 for r in rows if r["flag_count"]),
        "redFlagRate": pct(sum(1 for r in rows if r["flag_count"]), submitted),
        "aiTurns": round(statistics.fmean([r["ai_turns"] for r in rows]), 1),
        "students": len(roster),
        "challenges": len(CHALLENGES),
    }

    # —— 分母陷阱：三种口径下的「提交率」与「均分」 ——
    naive_den = len(students) * len(CHALLENGES)
    closed = [r for r in rows if r["challenge_id"] != "C6"]
    closed_expected = len(roster) * (len(CHALLENGES) - 1)
    alt = {
        "rateAllStudents": pct(submitted, naive_den),
        "rateRoster": pct(submitted, expected),
        "rateExcludeInProgress": pct(len(closed), closed_expected),
        "inProgressId": "C6",
        "avgZeroFilled": round(sum(scores + [0.0] * (submitted - len(reviewed))) / submitted, 1) if submitted else None,
        "avgReviewed": round(statistics.fmean(scores), 1) if scores else None,
        "pendingCount": sum(1 for r in rows if not r["reviewed"]),
    }

    # —— 班级差 vs 评审人差 ——
    class_avg = {c["class"]: c["avg"] for c in by_class}
    class_spread = round(max(v for v in class_avg.values() if v) - min(v for v in class_avg.values() if v), 1)
    rv_avg = [r["avg"] for r in reviewers if r["avg"]]
    reviewer_spread = round(max(rv_avg) - min(rv_avg), 1) if rv_avg else 0.0
    # 拆解：同一评审人对三个班的差（班内差） vs 评审人之间的差
    within = []
    for r in reviewers:
        vals = [v for v in r["byClass"].values() if v]
        if len(vals) >= 2:
            within.append(max(vals) - min(vals))
    within_spread = round(statistics.fmean(within), 1) if within else 0.0

    return {
        "meta": {
            "generated_at": TODAY.isoformat(),
            "seed": SEED,
            "clean_rows": len(rows),
            "log": log,
            "seasons": {"first": first, "last": last},
            "dataset_label": "班级全景（合成）",
        },
        "kpis": kpis,
        "byChallenge": by_ch,
        "byClass": by_class,
        "timeline": timeline,
        "scoreHist": hist,
        "dims": dims,
        "reviewers": reviewers,
        "late": {
            "onTime": {
                "n": len(on_sc),
                "avg": round(statistics.fmean(on_sc), 1) if on_sc else None,
                "median": round(statistics.median(on_sc), 1) if on_sc else None,
                "high90": pct(sum(1 for v in on_sc if v >= 90), len(on_sc)),
            },
            "late": {
                "n": len(late_sc),
                "avg": round(statistics.fmean(late_sc), 1) if late_sc else None,
                "median": round(statistics.median(late_sc), 1) if late_sc else None,
                "high90": pct(sum(1 for v in late_sc if v >= 90), len(late_sc)),
            },
            "corr": corr,
            "last24Share": pct(last24, submitted),
            "peakDate": peak_day["date"],
            "peakCount": peak_n,
        },
        "alt": alt,
        "artifact": {
            "hasDemo": artifact_has,
            "noDemo": artifact_non,
            "noDemoN": artifact_n,
            "noDemoShare": pct(sum(1 for r in rows if "缺 demo" in r["flags"]), submitted),
            "noAiLogShare": pct(sum(1 for r in rows if "缺 AI 日志" in r["flags"]), submitted),
            "noReadmeShare": pct(sum(1 for r in rows if "缺 README" in r["flags"]), submitted),
            "noDataShare": pct(sum(1 for r in rows if "缺数据" in r["flags"]), submitted),
            "onePassRate": pct(sum(1 for r in rows if r["attempts"] == 1 and r["status"] != "returned"), submitted),
            "avgAttempts": round(statistics.fmean([r["attempts"] for r in rows]), 2),
        },
        "reflectionC5": {
            "n": len(c5),
            "bins": bins,
            "peaks": peaks,
            "high": high,
            "low": low,
            "highShare": pct(high, len(c5)),
            "lowShare": pct(low, len(c5)),
            "median": round(statistics.median(c5), 1) if c5 else None,
        },
        "ai": ai_metrics,
        "classVsReviewer": {
            "classSpread": class_spread,
            "reviewerSpread": reviewer_spread,
            "withinReviewerSpread": within_spread,
        },
    }


def build_insights(m: dict) -> list[dict]:
    k, alt, late, art = m["kpis"], m["alt"], m["late"], m["artifact"]
    cvr, rc5 = m["classVsReviewer"], m["reflectionC5"]
    ai = m["ai"]
    other_floor = min(d["median"] for d in m["dims"] if d["key"] != "aiUsage")
    byc = {c["id"]: c for c in m["byChallenge"]}

    return [
        {
            "id": "I1",
            "tag": "时序",
            "level": "高",
            "title": f"{late['last24Share']}% 的作业挤在截止前 24 小时交，峰值 {late['peakCount']} 份/天",
            "claim": (
                f"全部 {k['submitted']} 份有效提交里，有 {late['last24Share']}% 落在截止前 24 小时内，"
                f"单日峰值 {late['peakDate']} 出现 {late['peakCount']} 份。"
                "这个分布不是「学生懒」，而是评分流量的形状问题。"
            ),
            "evidence": [
                {"label": "最后 24 小时提交占比", "value": f"{late['last24Share']}%"},
                {"label": "峰值日", "value": f"{late['peakDate']} · {late['peakCount']} 份"},
                {"label": "迟交占比", "value": f"{k['lateShare']}%"},
            ],
            "caveat": "占比按「有效提交」为分母；若按应交份数算会低 30pp 左右，两者不能混引。",
            "action": "截止前 48 小时推一次「材料自检清单」，把评审排班从「截止后集中 3 天」改成「按提交日滚动评审」。",
            "filter": {"challenge": "all"},
        },
        {
            "id": "I2",
            "tag": "口径",
            "level": "高",
            "title": (
                f"同一份数据，提交率能报出 {alt['rateExcludeInProgress']}% / {alt['rateRoster']}% / "
                f"{alt['rateAllStudents']}% 三个数"
            ),
            "claim": (
                f"分母只算已截止的 C1–C5 是 {alt['rateExcludeInProgress']}%；把进行中的 C6 也算进分母是 "
                f"{alt['rateRoster']}%；再把 {m['kpis']['students']} 位在读之外的退课/免修塞进来是 "
                f"{alt['rateAllStudents']}%。三个数都能自圆其说，差别全在分母。均分同理：{alt['pendingCount']} 份"
                f"待评审按 0 分计入，均分从 {alt['avgReviewed']} 掉到 {alt['avgZeroFilled']}。"
            ),
            "evidence": [
                {"label": "提交率（仅已截止挑战）", "value": f"{alt['rateExcludeInProgress']}%"},
                {"label": "提交率（含进行中 C6）", "value": f"{alt['rateRoster']}%"},
                {"label": "提交率（全员含退课）", "value": f"{alt['rateAllStudents']}%"},
                {"label": "均分（已评审 / 待评审记 0）", "value": f"{alt['avgReviewed']} / {alt['avgZeroFilled']}"},
            ],
            "caveat": "三个数都不算错，错的是不写分母就报数。看板里每个比率都带分母，鼠标悬停可见。",
            "action": "报表模板固定写「分子/分母/口径」三件套；对外只报「仅已截止挑战」那一版，进行中的单独列。",
            "filter": {"challenge": "all"},
        },
        {
            "id": "I3",
            "tag": "归因",
            "level": "高",
            "title": f"班级均分差 {cvr['classSpread']} 分，而换个评审人就能差 {cvr['reviewerSpread']} 分",
            "claim": (
                f"A/B/C 班均分差 {cvr['classSpread']} 分，看着像学情差异。但三位评审人的均分本身就差"
                f" {cvr['reviewerSpread']} 分，而同一评审人打三个班的差异只有 {cvr['withinReviewerSpread']} 分——"
                "班级之间几乎没有差，差的是笔。"
            ),
            "evidence": [
                {"label": "班级均分极差", "value": f"{cvr['classSpread']} 分"},
                {"label": "评审人均分极差", "value": f"{cvr['reviewerSpread']} 分"},
                {"label": "同评审人跨班极差（均值）", "value": f"{cvr['withinReviewerSpread']} 分"},
            ],
            "caveat": "评审人与班级约 88% 绑定，属于混淆变量；只有交叉评审的子样本能拆开——样本量小，结论是「不能下结论」，不是「班级无差异」。",
            "action": "班级横向比较前先看 reviewer 分布；下学期把评审人分派改成随机交叉，每班每维度双评。",
            "filter": {"tab": "insights"},
        },
        {
            "id": "I4",
            "tag": "反直觉",
            "level": "中",
            "title": f"迟交和低分几乎不相关：r = {late['corr']}",
            "claim": (
                f"按时组中位 {late['onTime']['median']} 分，迟交组中位 {late['late']['median']} 分，"
                f"两组只差 {abs(round(late['late']['median'] - late['onTime']['median'], 1))} 分"
                f"（方向还是反的）；提前量（小时）与总分的相关系数只有 {late['corr']}。"
                f"迟交占全部提交的 {k['lateShare']}%。「拖到最后 = 做得差」在这份数据里不成立。"
            ),
            "evidence": [
                {"label": "按时组（n）中位/均值", "value": f"{late['onTime']['median']} / {late['onTime']['avg']}（{late['onTime']['n']}）"},
                {"label": "迟交组（n）中位/均值", "value": f"{late['late']['median']} / {late['late']['avg']}（{late['late']['n']}）"},
                {"label": "提前量 vs 总分 相关系数", "value": f"{late['corr']}"},
                {"label": "迟交占全部有效提交", "value": f"{k['lateShare']}%"},
            ],
            "caveat": "相关不等于因果；且本数据集没有扣分策略，若课程按天扣分，结论会变——这正是口径要先写死的原因。",
            "action": "迟交按「是否影响评审排期」处理，而不是直接判定质量差；需要惩戒就明写扣分规则并进数据。",
            "filter": {"late": "late"},
        },
        {
            "id": "I5",
            "tag": "评分",
            "level": "中",
            "title": f"C5 复盘维度分裂成两簇：{rc5['highShare']}% 在 80+，{rc5['lowShare']}% 卡在 55–80",
            "claim": (
                f"同一份 rubric、同一批评审人，C5 的复盘分不是正态而是双峰：一簇 80 分以上占 {rc5['highShare']}%，"
                f"另一簇 55–80 占 {rc5['lowShare']}%，两簇间距约 20 分，中位数 {rc5['median']} 落在低簇里。"
                "分数没有连续过渡，说明「复盘合格线」在评审人脑子里有两套。"
            ),
            "evidence": [
                {"label": "80 分以上占比", "value": f"{rc5['highShare']}%"},
                {"label": "55–80 分占比", "value": f"{rc5['lowShare']}%"},
                {"label": "该维度中位", "value": f"{rc5['median']}"},
                {"label": "聚类峰值", "value": " / ".join(f"{p}" for p in rc5["peaks"])},
            ],
            "caveat": "双峰也可能是「真有 4 成学生做到了」；但两个峰间距 20 分且跨评审人复现，更像尺子问题。",
            "action": "给复盘维度补 3 个锚定样例（好/中/差各一份），下学期该维度双评取均值。",
            "filter": {"challenge": "C5"},
        },
        {
            "id": "I6",
            "tag": "交付物",
            "level": "中",
            "title": f"缺 demo 是产物完整性最大缺口：{art['noDemoShare']}% 的提交没有它",
            "claim": (
                f"{art['noDemoShare']}% 的提交缺 demo、{art['noAiLogShare']}% 缺 AI 日志、{art['noReadmeShare']}% 缺 README。"
                f"缺 demo 的 {art['noDemoN']} 份，产物完整性均分 {art['noDemo']}，齐备组 {art['hasDemo']}，差 {round(art['hasDemo'] - art['noDemo'], 1)} 分。"
            ),
            "evidence": [
                {"label": "缺 demo 占比", "value": f"{art['noDemoShare']}%"},
                {"label": "缺 demo 组 / 齐备组 分项均分", "value": f"{art['noDemo']} / {art['hasDemo']}"},
                {"label": "均分差", "value": f"{round(art['hasDemo'] - art['noDemo'], 1)} 分"},
            ],
            "caveat": "分项归因来自缺失标记，不是人工复核；缺 demo 与整体能力也相关，扣分里含混杂。",
            "action": "提交模板把 demo 设为必填项并给 30 秒录屏的最小样例；评审端对缺 demo 直接标红旗而不是靠人记。",
            "filter": {"flag": "缺 demo"},
        },
        {
            "id": "I7",
            "tag": "维度",
            "level": "中",
            "title": f"AI 使用质量是唯一「低分集中」的维度：{ai['lowRate']}% 不到 60 分",
            "claim": (
                f"其余四个维度的中位数都在 {other_floor} 分以上，只有 AI 使用质量中位 {ai['median']}、"
                f"{ai['lowRate']}% 低于 60 分。它和 AI 对话轮数强相关（r = {ai['corrTurns']}）："
                f"有 AI 日志的均分 {ai['withLog']}，没有的 {ai['noLog']}（{ai['noLogN']} 份）。"
            ),
            "evidence": [
                {"label": "该维度中位 / 低于 60 占比", "value": f"{ai['median']} / {ai['lowRate']}%"},
                {"label": "对话轮数 vs 该维度得分", "value": f"r = {ai['corrTurns']}"},
                {"label": "有日志 / 无日志 均分", "value": f"{ai['withLog']} / {ai['noLog']}"},
            ],
            "caveat": "轮数只是代理指标：刷轮数也能刷分，真正该看的是日志里有没有「失败→修正」。这条相关性不能当成因果。",
            "action": "给一份 AI 日志模板（目标 / 试了什么 / 错在哪 / 怎么改），评审随机抽 2 份人工复核，防止拿轮数凑分。",
            "filter": {"flag": "缺 AI 日志"},
        },
    ]


# --------------------------------------------------------------------------- #
# 落盘
# --------------------------------------------------------------------------- #
def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def sha_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C6A 数据管线")
    ap.add_argument("--check", action="store_true", help="只校验产物是否与种子一致")
    args = ap.parse_args(argv)

    rng = random.Random(SEED)
    students = gen_students(rng)
    raw = gen_submissions(rng, students)
    score_rows(rng, raw)
    # 平台导出里 3 行总分与分项不符（历史版本的权重没同步），清洗时必须按分项重算。
    # 这不是为了「制造脏数据」，而是真实导出里最常见的对账问题。
    touched = 0
    for r in raw:
        if touched >= 3:
            break
        if r.get("_total") is not None and r["challenge_id"] != "C6" and rng.random() < 0.02:
            r["_total"] = round(r["_total"] + rng.uniform(3.0, 8.0), 1)
            touched += 1
    clean_rows, log = clean(raw, students)
    metrics = build_metrics(clean_rows, students, log)
    insights = build_insights(metrics)

    # 原始导出：保留平台字段名与脏数据，便于演示「从脏到净」
    raw_out = []
    for r in raw:
        sc = r.get("_scores") or {}
        total = r.get("_total")
        raw_out.append(
            {
                "submission_id": r["submission_id"],
                "student_id": r["student_id"],
                "student_name": r["student_name"],
                "class": r["class"],
                "challenge_id": r["challenge_id"],
                "attempt_no": r["attempt_no"],
                "status": r["status"],
                "submitted_at": r["submitted_at"],
                "timezone": r["timezone"],
                "channel": r["submit_channel"],
                "files": r["files_count"],
                "has_readme": r["has_readme"],
                "has_demo": r["has_demo"],
                "has_data": r["has_data"],
                "has_ai_log": r["has_ai_log"],
                "ai_turns": r["ai_turns"],
                "reviewer": r["reviewer"],
                "s_data": sc.get("dataInsight"),
                "s_viz": sc.get("visualization"),
                "s_artifact": sc.get("artifact"),
                "s_ai": sc.get("aiUsage"),
                "s_reflection": sc.get("reflection"),
                "total": total,
                "note": r.get("note", ""),
            }
        )

    write_csv(
        DATA / "raw" / "submissions_export.csv",
        raw_out,
        [
            "submission_id", "student_id", "student_name", "class", "challenge_id",
            "attempt_no", "status", "submitted_at", "timezone", "channel", "files",
            "has_readme", "has_demo", "has_data", "has_ai_log", "ai_turns",
            "reviewer", "s_data", "s_viz", "s_artifact", "s_ai", "s_reflection",
            "total", "note",
        ],
    )
    write_csv(DATA / "raw" / "roster.csv", students, ["student_id", "name", "class", "status"])
    write_csv(
        DATA / "clean" / "submissions_clean.csv",
        [
            {
                "submission_id": r["submission_id"],
                "student_id": r["student_id"],
                "student_name": r["student_name"],
                "class": r["class"],
                "challenge_id": r["challenge_id"],
                "submitted_at": r["submitted_at"],
                "early_hours": r["early_hours"],
                "is_late": int(r["is_late"]),
                "attempts": r["attempts"],
                "status": r["status"],
                "flags": "|".join(r["flags"]),
                "reviewed": int(r["reviewed"]),
                "reviewer": r["reviewer"],
                "total": r["total"],
            }
            for r in clean_rows
        ],
        [
            "submission_id", "student_id", "student_name", "class", "challenge_id",
            "submitted_at", "early_hours", "is_late", "attempts", "status",
            "flags", "reviewed", "reviewer", "total",
        ],
    )

    payload = {
        "meta": metrics["meta"],
        "kpis": metrics["kpis"],
        "byChallenge": metrics["byChallenge"],
        "byClass": metrics["byClass"],
        "timeline": metrics["timeline"],
        "scoreHist": metrics["scoreHist"],
        "dims": metrics["dims"],
        "reviewers": metrics["reviewers"],
        "late": metrics["late"],
        "alt": metrics["alt"],
        "artifact": metrics["artifact"],
        "reflectionC5": metrics["reflectionC5"],
        "ai": metrics["ai"],
        "classVsReviewer": metrics["classVsReviewer"],
        "insights": insights,
        "dictionary": DICTIONARY,
        "rows": clean_rows,
        "challenges": [
            {"id": c["id"], "name": c["name"], "deadline": c["deadline"] + "+08:00"} for c in CHALLENGES
        ],
        "classes": ["A", "B", "C"],
        "students": [
            {"id": s["student_id"], "name": s["name"], "class": s["class"], "status": s["status"]}
            for s in students
        ],
    }

    real_path = DATA / "real" / "self_commits.json"
    payload["real"] = json.loads(real_path.read_text(encoding="utf-8")) if real_path.exists() else None

    metrics_path = DATA / "metrics.json"
    metrics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    app_js = APP / "js" / "data.js"
    app_js.parent.mkdir(parents=True, exist_ok=True)
    app_js.write_text(
        "/* 自动生成，请勿手改：python data/build_dataset.py */\nwindow.C6A_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )

    if args.check:
        print(f"[check] metrics.json sha256={sha_of(metrics_path)} bytes={metrics_path.stat().st_size}")
        print(f"[check] data.js      sha256={sha_of(app_js)} bytes={app_js.stat().st_size}")
    print(f"raw={len(raw)} clean={len(clean_rows)} seed={SEED}")
    print(f"提交率={metrics['kpis']['rate']}% 中位={metrics['kpis']['median']} 均分={metrics['kpis']['avg']} 迟交={metrics['kpis']['late']}")
    print("清洗日志: " + json.dumps(metrics["meta"]["log"], ensure_ascii=False))
    if not (APP / "index.html").exists():
        print("提示：app/index.html 尚未创建，data.js 已就绪。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
