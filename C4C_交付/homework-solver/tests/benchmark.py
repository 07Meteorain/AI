#!/usr/bin/env python3
"""
基准测试脚本：在多个测试集上跑流水线，输出可对比的统计报告。

这是「与 Claude 基线对比」这个交付要求的自动化工具——
手工数对错容易出错，也不���于复现。

用法:
    python tests/benchmark.py                       # 跑全部测试集
    python tests/benchmark.py --no-llm# 纯 SymPy
    python tests/benchmark.py --json report.json    # 导出 JSON
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ingest import ingest# noqa: E402
from parse_problems import parse_problems      # noqa: E402
from solve import solve_all                     # noqa: E402
from llm_engine import LLMSolver               # noqa: E402

# Claude starter kit 的官方基线（见 CHALLENGE.md）
CLAUDE_BASELINE = {
    "test1_tangent_epsilon_delta": {"solved": 8, "total": 8, "rate": 1.0},
    "test2_limits": {"solved": 9, "total": 10, "rate": 0.9},
    "total": {"solved": 17, "total": 18, "rate": 0.944},
}

TESTS = [
    ("test1_tangent_epsilon_delta", "test_cases/test1_tangent_epsilon_delta.md",
     "Berkeley Math 1A WS3：切线 & ε-δ"),
    ("test2_limits", "test_cases/test2_limits.md",
     "Berkeley Math 1A WS4：极限"),
    ("linear_algebra", "examples/homework_linear_algebra.md",
     "线性代数 12 题（新增学科）"),
    ("physics_ode", "examples/homework_physics_ode.md",
     "物理 +微分方程 14 题（新增学科）"),
]


def run_one(name, rel_path, label, use_llm, verify):
    path = ROOT / rel_path
    if not path.exists():
        return {"name": name, "error": f"文件不存在: {rel_path}"}

    t0 = time.time()
    try:
        ing = ingest(str(path))
        problems = parse_problems(ing)
        llm = LLMSolver(provider="qwen", offline=not use_llm)
        sols = solve_all(problems, llm=llm, use_llm=use_llm,
                         verify=verify, verbose=False)
    except Exception as e:
        import traceback
        return {"name": name, "label": label, "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-800:]}

    total = len(sols)
    solved = sum(1 for s in sols if s.get("solved"))
    v_pass = sum(1 for s in sols
                 if (s.get("verification") or {}).get("overall") == "pass")
    v_fail = sum(1 for s in sols
                 if (s.get("verification") or {}).get("overall") == "fail")

    # 求解器分布
    dist = {}
    for s in sols:
        k = s.get("solver", "unknown")
        dist[k] = dist.get(k, 0) + 1

    # 答案质量：抽查是否为空
    empty = sum(1 for s in sols
                if s.get("solved") and not (s.get("answer_latex") or s.get("answer")))

    return {
        "name": name, "label": label,
        "total": total, "solved": solved,
        "rate": round(solved / max(1, total), 4),
        "verify_pass": v_pass, "verify_fail": v_fail,
        "empty_answers": empty,
        "solver_distribution": dict(sorted(dist.items(), key=lambda kv: -kv[1])),
        "elapsed": round(time.time() - t0, 2),
        "unsolved": [s["problem_id"] for s in sols if not s.get("solved")],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="禁用 LLM，只用 SymPy")
    ap.add_argument("--no-verify", action="store_true", help="关闭验证")
    ap.add_argument("--json", default=None, help="导出 JSON 报告")
    args = ap.parse_args()

    print("=" * 72)
    print("C4C 流水线基准测试")
    print(f"   LLM: {'关闭（纯 SymPy）' if args.no_llm else 'qwen（无 Key 时自动降级）'}")
    print(f"   验证: {'关闭' if args.no_verify else '开启'}")
    print("=" * 72)

    results = []
    for name, rel, label in TESTS:
        r = run_one(name, rel, label, not args.no_llm, not args.no_verify)
        results.append(r)
        if "error" in r:
            print(f"\n[✗] {name}: {r['error']}")
            continue
        print(f"\n[{r['solved']}/{r['total']}] {name} — {label}")
        print(f"     求解率 {r['rate']*100:.1f}%｜验证 通过{r['verify_pass']} "
              f"存疑 {r['verify_fail']}｜耗时 {r['elapsed']}s")
        print(f"     求解器: {', '.join(f'{k}×{v}' for k, v in r['solver_distribution'].items())}")
        if r["empty_answers"]:
            print(f"     ⚠ 空答案 {r['empty_answers']} 处")
        if r["unsolved"]:
            print(f"     未解: {', '.join(r['unsolved'])}")

    # ── 与 Claude 基线对比 ──
    print("\n" + "=" * 72)
    print("与 Claude starter kit 基线对比（核心域：微积分极限）")
    print("=" * 72)
    print(f"{'测试集':<32}{'本项目':>12}{'Claude 基线':>14}{'差异':>10}")
    print("-" * 72)

    for key in ("test1_tangent_epsilon_delta", "test2_limits"):
        r = next((x for x in results if x["name"] == key), None)
        if not r or "error" in r:
            continue
        base = CLAUDE_BASELINE[key]
        mine = f"{r['solved']}/{r['total']}"
        theirs = f"{base['solved']}/{base['total']}"
        diff = r["rate"] - base["rate"]
        mark = "持平" if abs(diff) < 1e-9 else (f"+{diff*100:.1f}pt" if diff > 0
                                          else f"{diff*100:.1f}pt")
        print(f"{r['label'][:30]:<32}{mine:>12}{theirs:>14}{mark:>10}")

    core = [x for x in results
            if x["name"] in ("test1_tangent_epsilon_delta", "test2_limits")
            and "error" not in x]
    if core:
        ts = sum(x["total"] for x in core)
        sv = sum(x["solved"] for x in core)
        rate = sv / ts
        print("-" * 72)
        print(f"{'核心域合计':<32}{f'{sv}/{ts}':>12}"
              f"{f'{CLAUDE_BASELINE['total']['solved']}/{CLAUDE_BASELINE['total']['total']}':>14}"
              f"{rate*100 - 94.4:+9.1f}pt")
        print(f"\n目标：≥ 94.4%（Claude 基线）    实际：{rate*100:.1f}%")
        print("✅ 已达到/超过基线" if rate >= 0.944 else "❌ 未达到基线")

    # ── 扩展学科 ──
    ext = [x for x in results if x["name"] in ("linear_algebra", "physics_ode")
           and "error" not in x]
    if ext:
        ts = sum(x["total"] for x in ext)
        sv = sum(x["solved"] for x in ext)
        print(f"\n扩展学科（非极限，starter kit 基线仅 40%）: {sv}/{ts} = {sv/ts*100:.1f}%")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"results": results, "claude_baseline": CLAUDE_BASELINE},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 报告已写入: {out}")


if __name__ == "__main__":
    main()