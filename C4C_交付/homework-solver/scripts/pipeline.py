#!/usr/bin/env python3
"""
一键流水线（编排器 v2）：串联 Stage 1-5，从作业文件到 PDF。

    python pipeline.py <输入文件> <输出目录> [选项]

选项:
    --compile            编译 PDF（需要 LaTeX 环境）
    --course NAME       课程名称（默认: Mathematics）
    --student NAME      学生姓名（默认: Student）
    --title TITLE       作业标题（默认: Homework Solutions）
    --provider NAME     国产模型 provider: qwen|kimi|deepseek|claude（默认 qwen）
    --model NAME        模型名（默认取 provider 的推荐模型）
    --offline           离线模式：不调用 LLM API，只用规则兜底
    --no-llm            完全禁用 LLM（纯 SymPy 跑通）
    --no-verify         关闭答案验证
    --verbose详细输出

示例:
    # 最简：跑通示例作业
    python pipeline.py examples/sample_homework.md output/

    # 真实作业 + 编译 PDF
    python pipeline.py examples/homework_linear_algebra.md output/ \
        --compile --course "Linear Algebra" --student "Meteorain"

    # 用 Kimi 引擎 + 中文课程
    python pipeline.py my_homework.pdf out/ --provider kimi --student "张三"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest import ingest
from parse_problems import parse_problems
from solve import solve_all
from render_latex import render_document, compile_pdf, generate_figures
from llm_engine import LLMSolver


def run_pipeline(
    input_path: str,
    output_dir: str,
    course: str = "Mathematics",
    student: str = "Student",
    title: str = "Homework Solutions",
    do_compile: bool = False,
    provider: str = "qwen",
    model: str = None,
    offline: bool = False,
    use_llm: bool = True,
    use_verify: bool = True,
    verbose: bool = True,
) -> dict:
    """执行完整流水线 Stage 1→5。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    bar = "=" * 66
    print(bar)
    print("🚀 作业自动求解流水线（国产模型版）")
    print(f"   输入: {input_path}")
    print(f"   输出: {output_dir}")
    print(bar)

    # ── LLM 引擎自检 ─────────────────────────────
    llm = LLMSolver(provider=provider, model=model, offline=offline or not use_llm)
    h = llm.health()
    print(f"\n🧠 推理引擎: {h['display']} / {h['model']}")
    print(f"   状态: {'✅ 已就绪' if h['ready'] else f'⚠ {h[chr(114)+chr(101)+chr(97)+chr(115)+chr(111)+chr(110)]}'}")
    if not h["ready"]:
        print(f"   兜底: {h['fallback']}（流水线仍可端到端跑通）")
    if not use_llm:
        print("   注意: --no-llm 已启用，仅使用 SymPy + 规则兜底")

    # ── Stage 1: 文档摄入 ──────────────────────
    print("\n📄 Stage 1: 文档摄入")
    try:
        ingested = ingest(input_path)
        (out / "1_ingested.json").write_text(
            json.dumps(ingested, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   ✅ 格式 {ingested['format']}｜字符 {ingested['char_count']}｜"
              f"分段 {len(ingested['sections'])}")
    except Exception as e:
        print(f"   ❌ 摄入失败: {e}")
        return {"status": "failed", "stage": 1, "error": str(e)}

    # ── Stage 2: 题目解析 ──────────────────────
    print("\n🔍 Stage 2: 题目解析与分类")
    try:
        problems = parse_problems(ingested)
        (out / "2_parsed.json").write_text(
            json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   ✅ 识别 {len(problems)} 道题")
        by_type = {}
        for p in problems:
            by_type[p["type"]] = by_type.get(p["type"], 0) + 1
        print(f"   题型分布: " +
              "  ".join(f"{k}×{v}" for k, v in sorted(by_type.items())))
        if verbose:
            for p in problems:
                nsub = f" ({len(p['sub_problems'])}子题)" if p["sub_problems"] else ""
                print(f"      · {p['id']}: [{p['type']}]{nsub}")
    except Exception as e:
        print(f"   ❌ 解析失败: {e}")
        traceback.print_exc()
        return {"status": "failed", "stage": 2, "error": str(e)}

    if not problems:
        print("\n⚠️ 未识别到题目。请检查输入格式。")
        print("   支持题号: 'Problem N' / '题 N' / 'N.' / 'N)' / 'Q.N' / 'Exercises N'")
        return {"status": "failed", "stage": 2, "error": "no problems parsed"}

    # ── Stage 3: 求解 + 验证 ───────────────────
    print("\n🧮 Stage 3: 自动求解（SymPy + 国产 LLM 混合路由）")
    try:
        solutions = solve_all(problems, llm=llm, use_llm=use_llm,
                              verify=use_verify, verbose=verbose)
        (out / "3_solutions.json").write_text(
            json.dumps(solutions, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        solved = sum(1 for s in solutions if s["solved"])
        print(f"   ✅ 求解 {solved}/{len(solutions)}")
        for s in solutions:
            mark = "✅" if s["solved"] else "❌"
            v = s.get("verification", {})
            vflag = {"pass": "✓", "fail": "⚠"}.get(v.get("overall"), "")
            info = (s.get("answer_latex") or s.get("reason", ""))[:56]
            print(f"      {mark} {s['problem_id']} [{s['solver']}] {vflag} {info}")
    except Exception as e:
        print(f"   ❌ 求解失败: {e}")
        traceback.print_exc()
        return {"status": "failed", "stage": 3, "error": str(e)}

    # ── Stage 4: LaTeX 生成 ────────────────────
    print("\n📝 Stage 4: LaTeX 生成")
    try:
        figures = generate_figures(solutions, out / "figures")
        tex, cjk = render_document(solutions, course=course, student=student,
                                   title=title, figures=figures,
                                   verification_on=use_verify)
        tex_path = out / "homework.tex"
        tex_path.write_text(tex, encoding="utf-8")
        print(f"   ✅ {tex_path}（CJK={cjk}，图 {len(figures)} 张）")
    except Exception as e:
        print(f"   ❌ LaTeX 生成失败: {e}")
        traceback.print_exc()
        return {"status": "failed", "stage": 4, "error": str(e)}

    # ── Stage 5: PDF 编译 ──────────────────────
    pdf_info = None
    if do_compile:
        print("\n📑 Stage 5: PDF 编译")
        ok, pdf_info = compile_pdf(str(tex_path), str(out), cjk=cjk)
        if ok:
            print(f"   ✅ 引擎={pdf_info['engine']}｜页数={pdf_info.get('pages')}｜"
                  f"大小={pdf_info.get('size', 0):,} bytes")
            print(f"   输出: {pdf_info['pdf']}")
        else:
            print(f"   ⚠️ 编译未成功（已尝试: {pdf_info['tried']}）")
            print("   可改用：上传 homework.tex 到 Overleaf，或安装 tectonic/MiKTeX")
    else:
        print("\n📑 Stage 5: PDF 编译（跳过，加 --compile 启用）")

    # ── 汇总 ──────────────────────────────────
    elapsed = time.time() - t0
    solved = sum(1 for s in solutions if s["solved"])
    v_pass = sum(1 for s in solutions
                 if (s.get("verification") or {}).get("overall") == "pass")
    v_fail = sum(1 for s in solutions
                 if (s.get("verification") or {}).get("overall") == "fail")

    print("\n" + bar)
    print("📊 流水线完成")
    print(f"   耗时: {elapsed:.1f}s")
    print(f"   求解: {solved}/{len(solutions)} ({100*solved/max(1,len(solutions)):.1f}%)")
    print(f"   验证: 通过 {v_pass}｜存疑 {v_fail}")
    print(f"   产物:")
    for f in sorted(out.iterdir()):
        if f.is_file():
            print(f"      {f.name} ({f.stat().st_size:,} bytes)")
        elif f.is_dir():
            n = len(list(f.iterdir()))
            print(f"      {f.name}/ ({n} 个文件)")
    print(bar)

    return {
        "status": "ok",
        "total": len(solutions),
        "solved": solved,
        "solve_rate": solved / max(1, len(solutions)),
        "verify_pass": v_pass,
        "verify_fail": v_fail,
        "elapsed": elapsed,
        "output_dir": str(out),
        "tex": str(tex_path),
        "pdf": (pdf_info or {}).get("pdf"),
        "pdf_pages": (pdf_info or {}).get("pages"),
        "provider": h["display"],
        "llm_ready": h["ready"],
        "figures": len(figures),
    }


def main():
    ap = argparse.ArgumentParser(
        description="作业自动求解流水线：文件 → 解析 → 求解 → LaTeX → PDF（国产模型版）")
    ap.add_argument("input", help="输入文件 (md/pdf/docx/tex/图片)")
    ap.add_argument("output_dir", help="输出目录")
    ap.add_argument("--compile", action="store_true", help="编译 PDF")
    ap.add_argument("--course", default="Mathematics", help="课程名称")
    ap.add_argument("--student", default="Student", help="学生姓名")
    ap.add_argument("--title", default="Homework Solutions", help="作业标题")
    ap.add_argument("--provider", default="qwen",
                    choices=["qwen", "kimi", "deepseek", "claude"],
                    help="国产模型 provider（默认 qwen）")
    ap.add_argument("--model", default=None, help="模型名（默认取 provider 推荐）")
    ap.add_argument("--offline", action="store_true",
                    help="离线模式，不调用 LLM API")
    ap.add_argument("--no-llm", action="store_true", help="禁用 LLM")
    ap.add_argument("--no-verify", action="store_true", help="关闭答案验证")
    ap.add_argument("--verbose", action="store_true", help="详细输出")
    args = ap.parse_args()

    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在 — {args.input}")
        sys.exit(1)

    res = run_pipeline(
        input_path=args.input,
        output_dir=args.output_dir,
        course=args.course,
        student=args.student,
        title=args.title,
        do_compile=args.compile,
        provider=args.provider,
        model=args.model,
        offline=args.offline,
        use_llm=not args.no_llm,
        use_verify=not args.no_verify,
        verbose=args.verbose,
    )

    if res.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()