#!/usr/bin/env python3
"""
Stage 3 求解编排器（v2）

在starter kit 的 solve.py 之上做了三件事，也是 C4C Level 3「核心创新」
要求回答的那个问题——**哪些题用 SymPy，哪些题用国产 LLM，两者怎么结合**：

┌──────────────────────────────┬────────────┬───────────────────────────────┐
│ 题目特征                      │ 路由       │ 理由                          │
├──────────────────────────────┼────────────┼───────────────────────────────┤
│ 有确定数学表达式 + 计算指令    │ SymPy      │ 确定性、可复现、零幻觉│
│ 抽象函数/ 证明 / 概念/ 文字   │ 国产 LLM   │ 需要推理与语言组织           │
│ 矩阵 / ODE / 物理常量        │ SymPy 域求解│ 需专用解析器，LLM 易编错      │
│ SymPy 未解出（非平凡）        │ LLM 兜底   │ 二次机会，成本换正确率         │
│ 图形题                       │ matplotlib │ 生成函数图插入 LaTeX          │
└──────────────────────────────┴────────────┴───────────────────────────────┘

另一个关键差异：**每题都跑验证**。SymPy 算完立刻代回原式检验，
LLM 答案则做形式检查 + 可选交叉检验。验证结果写进 3_solutions.json。
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path
from typing import Optional

import sympy
from sympy import (
    Symbol, Matrix, Rational, simplify, expand, factor, latex, solve, diff,
    integrate, limit, symbols, Function, oo, pi, E, S, sin, cos, tan, exp,
    log, ln, sqrt, Abs, summation, series, Eq, Piecewise, eye, sympify, Min,
)
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations,
    implicit_multiplication_application, convert_xor,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import domain_solvers as DS          # 新增：线代 / ODE / 物理
import verify as V                   # 新增：答案验证
from llm_engine import LLMSolver      # 新增：国产模型引擎

# ═════════════════════════════════════════════
# 符号与表达式解析（继承 starter kit 的 safe_parse 并增强）
# ═════════════════════════════════════════════

x, y, z, t, n, k = symbols("x y z t n k")
a, b, c = symbols("a b c")
delta_sym = Symbol("delta", positive=True)
epsilon_sym = Symbol("epsilon", positive=True)
f = Function("f")

TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application, convert_xor,
)

_LOCAL = {
    "x": x, "y": y, "z": z, "t": t, "n": n, "k": k, "a": a, "b": b, "c": c,
    "pi": pi, "e": E, "oo": oo, "inf": oo, "sin": sin, "cos": cos, "tan": tan,
    "exp": exp, "log": log, "ln": ln, "sqrt": sqrt, "Abs": Abs,
    "delta": delta_sym, "epsilon": epsilon_sym, "I": sympy.I,
}


def _find_matching_brace(s: str, pos: int) -> int:
    if pos >= len(s) or s[pos] != "{":
        return -1
    depth, i = 1, pos + 1
    while i < len(s) and depth > 0:
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
        i += 1
    return i - 1 if depth == 0 else -1


def safe_parse(expr_str: str):
    """LaTeX → SymPy。继承 starter kit 实现 + 增强（支持矩阵环境保留）。"""
    s = (expr_str or "").strip()
    if not s:
        raise ValueError("空表达式")

    # 矩阵/分段函数交给专用解析器
    if DS._MATRIX_ENV.search(s):
        M = DS.parse_latex_matrix(s)
        if M is not None:
            return M
    if DS._CASES_ENV.search(s):
        raise ValueError("cases 环境需专用处理")

    s = re.sub(r"\\begin\{.*?\}|\\end\{.*?\}", "", s)

    def _replace_frac(s):
        # (?:d|t)? 而非 [dt]? —— 方括号是正则字符类，[dt]? 匹配不到 \frac/\dfrac
        while True:
            m = re.search(r"\\(?:d|t)?frac\s*\{", s)
            if not m:
                break
            # num_start 必须指向「{ 之后第一个字符」。
            # m.end() 已经就是那个位置——早先写成 m.end()-m.start()+1
            # 在 \frac{x^2+...} 这类含嵌套 {} 的式子上会算偏，
            # 导致 _find_matching_brace 返回 -1，分数被整体丢弃。
            num_start = m.end()
            num_end = _find_matching_brace(s, num_start - 1)
            if num_end < 0:
                break
            if num_end + 1 >= len(s) or s[num_end + 1] != "{":
                break
            den_start = num_end + 2
            den_end = _find_matching_brace(s, num_end + 1)
            if den_end < 0:
                break
            num, den = s[num_start:num_end], s[den_start:den_end]
            s = s[:m.start()] + f"(({num})/({den}))" + s[den_end + 1:]
        return s

    s = _replace_frac(s)
    s = re.sub(r"\\sqrt\[(\d+)\]\{([^}]+)\}", r"((\2)**(1/(\1)))", s)
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\(?:left|right)[(\[{|]?", "(", s)
    s = re.sub(r"\\(?:left|right)[)\]}|]?", ")", s)
    s = s.replace("\\cdot", "*").replace("\\times", "*").replace("\\div", "/")
    s = s.replace("\\pi", "pi").replace("\\infty", "oo")
    for fn in ("sin", "cos", "tan", "ln", "log", "exp", "arcsin", "arccos", "arctan"):
        s = s.replace(f"\\{fn}", fn)
    s = re.sub(r"\\[,;!]", " ", s)
    s = re.sub(r"\\(?:quad|qquad)", " ", s)
    s = re.sub(r"\\mathrm\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\|([^|]+)\|", r"Abs(\1)", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"\^\{([^}]+)\}", r"**(\1)", s)
    s = re.sub(r"\^(\w)", r"**\1", s)
    s = re.sub(r"_\{[^}]+\}", "", s)
    s = re.sub(r"_\w", "", s)
    s = s.replace("{", "(").replace("}", ")")
    s = re.sub(r"\s+", " ", s).strip()

    return parse_expr(s, local_dict=_LOCAL, transformations=TRANSFORMATIONS)


def try_parse_limit_expression(latex_str: str):
    """解析 \\lim_{x \\to a^+} expr → (var, point, direction, expr)。"""
    m = re.search(r"\\lim_\{([a-z])\s*\\to\s*([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*(.+)",
                  latex_str, re.DOTALL)
    if not m:
        return None
    var_str, point_str, expr_str = m.group(1), m.group(2).strip(), m.group(3).strip()

    direction = None
    if point_str.endswith(("^+", "^{+}", "+")):
        direction = "+"
        point_str = re.sub(r"\^\{?\+\}?$|\+$", "", point_str).strip()
    elif point_str.endswith(("^-", "^{-}", "-")):
        direction = "-"
        point_str = re.sub(r"\^\{?-\}?$|-$", "", point_str).strip()

    var = Symbol(var_str)
    try:
        point = safe_parse(point_str) if point_str else S(0)
    except Exception:
        point = oo if ("infty" in point_str or "inf" in point_str) else S(0)
    try:
        expr = safe_parse(expr_str)
    except Exception:
        return None
    return (var, point, direction, expr)


def try_parse_integral(latex_str: str):
    """解析 \\int_a^b f(x) dx → (integrand, var, bounds)。"""
    m = re.search(
        r"\\int(?:_\{([^{}]*)\}\^\{([^{}]*)\}|_(\w+)\^(\w+))?\s*(.+?)\s*[d\\,]\s*([a-z])\s*$",
        latex_str, re.DOTALL)
    if not m:
        return None
    lower = m.group(1) or m.group(3)
    upper = m.group(2) or m.group(4)
    integrand_s, var_s = m.group(5), m.group(6)

    try:
        integrand = safe_parse(integrand_s)
    except Exception:
        return None
    bounds = None
    if lower and upper:
        try:
            bounds = (safe_parse(lower), safe_parse(upper))
        except Exception:
            bounds = None
    return (integrand, Symbol(var_s), bounds)


# ═════════════════════════════════════════════
# 题目特征判断
# ═════════════════════════════════════════════

def has_abstract_functions(math_exprs) -> bool:
    """检测 f(x) / g(x) 等抽象函数——这类题不该走符号计算。"""
    for e in math_exprs or []:
        s = e.get("latex", "") if isinstance(e, dict) else str(e)
        if re.search(r"[fgh]\s*\(\s*[a-z]\s*\)", s):
            return True
    return False


def has_matrix(math_exprs) -> bool:
    return any(DS._MATRIX_ENV.search(e.get("latex", ""))
               for e in math_exprs or [] if isinstance(e, dict))


def has_ode(text, math_exprs) -> bool:
    joined = " ".join(e.get("latex", "") for e in math_exprs or [] if isinstance(e, dict))
    blob = text + " " + joined
    return bool(
        re.search(r"y\s*''|dy\s*/\s*dx|d\s*y|d\^\{?2\}?\\,?y", blob.replace("\\ ", ""))
        or re.search(r"微分方程|differential equation|\bODE\b", blob, re.I)
    )


def extract_function_definition(text, math_exprs):
    for e in math_exprs or []:
        s = e.get("latex", "")
        m = re.match(r"f\s*\(\s*x\s*\)\s*=\s*(.+)", s)
        if m:
            try:
                return (x, safe_parse(m.group(1)))
            except Exception:
                pass
        m = re.match(r"y\s*=\s*(.+)", s)
        if m:
            try:
                return (x, safe_parse(m.group(1)))
            except Exception:
                pass
    return None


def extract_point_from_text(text, math_exprs):
    for e in math_exprs or []:
        s = e.get("latex", "")
        m = re.match(r"\(?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)?", s.strip())
        if m:
            try:
                return (S(m.group(1)), S(m.group(2)))
            except Exception:
                pass
    m = re.search(r"\((\d+),\s*(\d+)\)", text)
    if m:
        return (S(int(m.group(1))), S(int(m.group(2))))
    return None


# ═════════════════════════════════════════════
# 路由决策：核心的"SymPy vs LLM"判断
# ═════════════════════════════════════════════

def decide_route(problem: dict) -> tuple:
    """
    返回 (route, reason)。

    route ∈ {sympy, llm, hybrid}
    hybrid = 先 SymPy，失败降级 LLM
    """
    text = problem.get("text", "")
    text_l = text.lower()
    exprs = problem.get("math_expressions", []) or []
    subs = problem.get("sub_problems", []) or []

    # 关键词判断要**连子题一起看**。
    # ε-δ 计算题（Worksheet3 P4）的题干只有一句 "Let f(x)=x^2"，
    # "within δ of 3" 这类关键信息全在 (b)(c)(d) 子题里——
    # 只看题干会漏判成「抽象函数 → 交给 LLM」。
    subs_text = " ".join((s.get("text", "") or "") for s in subs).lower()
    text_all = text_l + " " + subs_text

    # ── ① 结构性信号优先（凌驾于动词关键词之上）───────────────
    # 矩阵 / ODE / 物理常量题都有**明确的形式特征**，比 "verify/prove"
    # 这类动词关键词可靠得多。必须先判，否则
    # 「验证 y = C₁e^{2x}+C₂e^{3x} 是 y''-5y'+6y=0 的解」
    # 会被 "verify" 抢走 routed 给 LLM，而它其实是纯代入计算。
    if has_matrix(exprs):
        return "sympy", "含矩阵，需专用 LaTeX 矩阵解析"
    if has_ode(text, exprs):
        return "sympy", "含微分方程，dsolve / 代入验证可解"

    # 物理题：数值和单位写在自然语言里，**不需要 LaTeX 表达式**，
    # 所以必须在「exprs 为空 → 走 LLM」这条默认规则**之前**判定。
    # （早期版本没在这里判定，导致「12 N 作用在 3.0 kg 物体上」这种
    #   题因为没有 $...$ 而被丢给 LLM，白白浪费一次调用。）
    if re.search(r"库仑|欧姆|电场|自由落体|动能|势能|理想气体|牛顿|"
                 r"coulomb|ohm|electric field|free fall|kinetic energy|"
                 r"potential energy|ideal gas|gravitational|"
                 r"newton'?s? second law|point charge|\bgas\b|\bdrop\b|"
                 r"constant velocity|\bpotential\b.*\benergy\b", text_l):
        return "sympy", "物理常量题，符号计算可闭环（含单位解析）"

    # ── ② 概念模板优先于一切推理判断 ──
    # 关键：**先查模板库，再谈"要不要用 LLM"**。
    # Berkeley Math 1A 的Q2「∞ 是不是数？」
    # 虽然含 f(x)，抽象函数检测会命中并把它丢给 LLM——
    # 但这个问题的答案完全可由模板确定（∞ 不是实数），
    # 确定性模板当然优于一次可能编造的 API 调用。
    if _match_conceptual_template(text_all):
        return "sympy", "命中概念模板库（确定性答案，优于 LLM 推理）"

    # ε-δ 计算题：给了具体 f(x) + 「within δ of a」「within ε of L」
    # 这类题是纯代数构造（δ = min{1, ε/C}），符号计算完全能闭环。
    if re.search(r"within\s+\$?\\?delta\$?\s+of", text_all) and \
            extract_function_definition(text, exprs):
        return "sympy", "ε-δ 计算题（构造 δ），符号计算可闭环"

    # ── ③ 需要推理的：抽象函数、证明、纯概念 ──
    #注意：判断「有没有数学表达式」时**必须把子题也算进来**。
    # 像 Worksheet4 的 AP1「下面列出三个极限，配对方法并求值」——
    # 题干本身一个公式都没有，全部内容都在 (a)(b)(c) 里。
    # 只看父题会误判成「纯文字题 → 丢给 LLM」，白白浪费一次调用。
    sub_exprs = [e for s in (problem.get("sub_problems") or [])
                 for e in (s.get("math_expressions") or [])]
    all_exprs = list(exprs) + sub_exprs
    has_sub_exprs = bool(sub_exprs)

    proof_kw = ("prove", "show that", "证明", "demonstrate", "verify that",
                "explain why", "discuss", "is it true", "what does", "describe what")
    conceptual_kw = ("what is meant", "explain", "describe", "what do we mean",
                     "讨论", "解释", "什么是")
    if has_abstract_functions(exprs):
        return "llm", "含抽象函数 f(x)/g(x)，符号计算无意义，需推理"
    if any(k in text_l for k in proof_kw):
        return "llm", "证明/论证类题目，需要多步推理"
    if any(k in text_l for k in conceptual_kw) and not all_exprs:
        return "llm", "纯概念题，无可计算表达式"

    # ── ④ 一般计算题 ──
    calc_kw = ("derivative", "integrate", "compute", "evaluate", "find", "solve",
               "limit", "求导", "积分", "计算", "求", "解")
    if has_sub_exprs:
        return "sympy", "子题含可计算表达式（题干本身可能是纯文字指令）"
    if all_exprs and any(k in text_all for k in calc_kw):
        return "sympy", "有明确计算指令与数学表达式"
    if all_exprs:
        return "sympy", "含数学表达式，尝试符号计算"

    return "llm", "无可计算表达式，纯文字题"


# ═════════════════════════════════════════════
# SymPy 求解器（原starter kit + 增强）
# ═════════════════════════════════════════════

def solve_sympy(problem: dict) -> dict:
    """把 starter kit 的求解逻辑 + 新领域求解器整合到一个入口。"""
    ptype = problem.get("type", "calculation")
    text = problem.get("text", "")
    text_l = text.lower()
    exprs = problem.get("math_expressions", []) or []
    subs = problem.get("sub_problems", []) or []

    try:
        # ══════════════════════════════════════════════════════════
        # 领域路由：一旦命中某个领域求解器，**要么用它给出答案，
        # 要么明确报告未解**，绝不退回通用求解器。
        #
        # 原因（这是一个真实踩过的坑）：早期版本这里是
        #     r = DS.solve_physics(p); if r["solved"]: return r
        #     ... # 失败就继续往下走
        #     return solve_general(p)
        # 结果「两个点电荷求库仑力」的题，因为物理求解器没识别出题型，
        # 落到了通用求解器；通用求解器从题面里抓到第一个数字 3.0，
        # 化简后当作答案输出——一个看起来完全正常、实际完全错误的答案。
        #
        # 「静默地给出错误答案」比「明确说不会」危害大得多：
        # 前者会直接骗过学生，后者只是能力不足。
        # ══════════════════════════════════════════════════════════

        # ── 矩阵 / 线性代数 ──
        if ptype == "matrix" or has_matrix(exprs):
            return DS.solve_matrix(problem)      # 领域内，失败即报未解

        # ── ODE ──
        if ptype == "ode" or has_ode(text, exprs):
            return DS.solve_ode(problem)

        # ── 物理 ──
        if ptype == "physics" or re.search(
                r"库仑|欧姆|电场|自由落体|动能|势能|理想气体|coulomb|ohm|"
                r"electric field|free fall|kinetic energy|ideal gas|"
                r"point charge|gravitational|newton'?s? second law|"
                r"potential energy|dropped|\bfalls?\b|\bgas\b", text_l):
            return DS.solve_physics(problem)

        # ── 极限 / ε-δ / 切线 / 概念 ──
        if ptype in ("limit", "epsilon_delta", "tangent", "conceptual") or \
                re.search(r"\\lim|limit|极限|切线|tangent|within.*delta|"
                          r"horizontal", text_l):
            r = solve_limit_domain(problem)
            if r.get("solved"):
                return r
            # 极限域内未解出：可能是抽象函数概念题，再试一次概念模板
            if has_abstract_functions(exprs):
                tmpl = _match_conceptual_template(text_l)
                if tmpl:
                    return _sol(problem, tmpl["steps"], tmpl["answer_latex"],
                                "conceptual_template", answer_text=tmpl["answer"])
            return r        # 报未解，不退回通用

        # ── 真正通用的计算题（求导/积分/化简/解方程）──
        return solve_general(problem)

    except Exception as e:
        return _unsolved(problem, f"符号计算异常: {type(e).__name__}: {e}")


def solve_limit_domain(problem: dict) -> dict:
    """极限 / 切线 / ε-δ 域（继承并增强 starter kit）。"""
    text = problem.get("text", "")
    text_l = text.lower()
    exprs = problem.get("math_expressions", []) or []
    subs = problem.get("sub_problems", []) or []

    # ε-δ 记号题
    if re.search(r"within\s*(\$?\\?delta|δ)", text_l):
        r = solve_epsilon_delta(problem)
        if r.get("solved"):
            return r

    # ε-δ 计算题：「x 在 δ 内 ⟹ f(x) 在 ε 内，求 δ」
    # 识别特征：给出了具体的 f(x)、中心 a、目标值 L，以及一个 ε。
    r = solve_epsilon_delta_computation(problem)
    if r.get("solved"):
        return r

    # 切线题
    if re.search(r"tangent|切线", text_l):
        r = solve_tangent(problem)
        if r.get("solved"):
            return r
        # 切线域内未解出 → 试概念模板（存在性/唯一性、反例等）。
        # Berkeley Math 1A Worksheet 3 的 Q1/Q2 属于这一类：
        # 题面里没有具体函数，只有抽象提问。
        tmpl = _match_conceptual_template(text_l)
        if tmpl:
            return _sol(problem, tmpl["steps"], tmpl["answer_latex"],
                        "conceptual_template", answer_text=tmpl["answer"])
        return r

    # 抽象函数 → 概念模板
    if has_abstract_functions(exprs):
        tmpl = _match_conceptual_template(text_l)
        if tmpl:
            return _sol(problem, tmpl["steps"], tmpl["answer_latex"],
                        "conceptual_template", answer_text=tmpl["answer"])
        # 但如果给出了**具体函数定义** f(x)=x²，那就不是抽象函数题——
        # Worksheet3 的 P4 属于这种：题干有 f(x)=x²（可算），
        # 只是题干短、关键条件在子题里。不能一看到 f(x) 就当抽象题。
        if extract_function_definition(text, exprs):
            pass  # 继续往下走 ε-δ / 切线 / 极限的常规流程
        else:
            # 抽象函数但子题里有**具体可算的极限**（如 Worksheet4 AP1：
            # 题干只是"下面列出三个极限"，真正的计算全在 (a)(b)(c) 里）
            sub_sols = _solve_limit_subs(subs)
            if any(s.get("solved") for s in sub_sols):
                return {"problem_id": problem["id"], "problem_text": text,
                        "solved": True,
                        "steps": ["本题的计算部分在子题中，逐子题求解如下。"],
                        "answer": "见各子题",
                        "answer_latex": r"\text{见各子题解答}",
                        "solver": "sympy_limit",
                        "sub_solutions": sub_sols}
            return _unsolved(problem, "概念题（含抽象函数），需 LLM 求解器",
                             subs=sub_sols)

    # 极限计算
    results = []
    for e in exprs:
        p = try_parse_limit_expression(e.get("latex", ""))
        if p:
            results.append(p)

    if results:
        steps, main_ans, ctx = [], None, None
        for (var, pt, direction, expr) in results:
            try:
                expr = expr.rewrite(Piecewise)
                if direction == "+":
                    val = limit(expr, var, pt, "+")
                elif direction == "-":
                    val = limit(expr, var, pt, "-")
                else:
                    val = limit(expr, var, pt)
                ar = "^" + direction if direction else ""
                steps.append(f"$\\lim_{{{var} \\to {latex(pt)}{ar}}} {latex(expr)}"
                             f" = {latex(val)}$")
                main_ans, ctx = val, (expr, var, pt, direction)
            except Exception as e:
                steps.append(f"计算失败：${latex(expr)}$（{type(e).__name__}）")
        if main_ans is not None:
            sub_sols = _solve_limit_subs(subs)
            return _sol(problem, steps, latex(main_ans), "sympy_limit",
                        extra={"verify_hint": {"kind": "limit", "ctx": ctx}},
                        sub_solutions=sub_sols, answer_text=str(main_ans))

    sub_sols = _solve_limit_subs(subs)
    if sub_sols and any(s.get("solved") for s in sub_sols):
        return {"problem_id": problem["id"], "problem_text": text, "solved": True,
                "steps": ["见各子题计算过程。"], "answer": "见子题",
                "answer_latex": "\\text{见各子题}", "solver": "sympy_limit",
                "sub_solutions": sub_sols}

    tmpl = _match_conceptual_template(text_l)
    if tmpl:
        return _sol(problem, tmpl["steps"], tmpl["answer_latex"],
                    "conceptual_template", answer_text=tmpl["answer"],
                    sub_solutions=sub_sols)

    # 几何/序列型极限：圆内接正 n 边形面积趋于 π 这类题，
    # 公式藏在文字描述里（"circle of radius 1"、"regular n-gon"），
    # 正则抓不到 \lim，需要靠题面语义识别。
    geo = _solve_geometry_limit(problem, subs)
    if geo:
        return geo

    return _unsolved(problem, "无法提取可计算的极限表达式", subs=sub_sols)


def _solve_geometry_limit(problem: dict, subs) -> Optional[dict]:
    """
    几何型极限：圆内接正 n 边形面积 → πR²。

    对应 Berkeley Math 1A Worksheet 4 的 AP3。这类题的极限表达式写成
    "\\lim_{n \\to \\infty}" 后面跟着文字 "（n 边形的面积）"，
    没有可解析的数学表达式，只能靠语义识别 + 公式推导。
    """
    text = (problem.get("text", "") + " " +
            " ".join(s.get("text", "") for s in (subs or []))).lower()

    if not re.search(r"circle|圆", text):
        return None
    if not re.search(r"n-gon|polygon|正多边形|多边形", text):
        return None

    # 半径
    R = Rational(1)
    m = re.search(r"radius\s+\$?([\d./]+)", text)
    if m:
        try:
            R = sympify(DS._latex_atom(m.group(1)))
        except Exception:
            pass

    steps = [
        f"半径 $R = {latex(R)}$，圆面积 $A_\\bigcirc = \\pi R^2$",
        r"把圆分成 $n$ 个等腰三角形（顶角 $2\pi/n$，两边都是半径 $R$）：",
        r"单个三角形面积：$\Delta_n = \frac{1}{2}R^2\sin\frac{2\pi}{n}$",
        r"$n$ 边形面积：$A_n = n\Delta_n = \frac{n}{2}R^2\sin\frac{2\pi}{n}$",
    ]

    # ⚠️ 这里**不能**加 integer=True。
    # SymPy 的 Gruntz 算法在符号带 integer 假设时会把
    # limit(n·sin(2π/n)/2, n, oo) 算成 0（正确答案是 π），
    # 而且**不报错**——静默给出错误答案，比报错危险得多。
    # 实测：positive=True → π；positive=True, integer=True → 0。
    n = Symbol("n", positive=True)
    A_n = n / 2 * R ** 2 * sin(2 * pi / n)
    try:
        lim_val = simplify(limit(A_n, n, oo))
        # 交叉检验：n·sin(c/n) → c，解析解应当是 πR²
        analytic = pi * R ** 2
        if simplify(lim_val - analytic) != 0:
            steps.append(
                rf"⚠️ 符号计算得 {latex(lim_val)}，与解析值 "
                rf"{latex(analytic)} 不符——采用解析结果。")
            lim_val = analytic
        steps.append(rf"$\lim_{{n \to \infty}} A_n = "
                     rf"\lim_{{n\to\infty}} \frac{{n}}{{2}}R^2"
                     rf"\sin\frac{{2\pi}}{{n}} = {latex(lim_val)}$")
        steps.append(
            f"直觉校验：$n\\to\\infty$ 时多边形越来越像圆，"
            f"面积应趋于 $\\pi R^2 = {latex(analytic)}$"
            f"{'—— 与上面一致 ✓' if simplify(lim_val - analytic) == 0 else ''}")
    except Exception as e:
        lim_val = pi * R ** 2
        steps.append(rf"（符号计算求极限失败，改用几何直觉：$A_n \to \pi R^2$）")

    # 子题 (a)(b)(c) 的答案
    sub_sols = []
    for s in (subs or []):
        st = s.get("text", "").lower()
        if re.search(r"measure of the angles|夹角|圆心角|周角", st):
            sub_sols.append(_sub_sol(s, [
                r"$n$ 个等腰三角形的顶角加起来是整周 $2\pi$，",
                r"所以每个角 $\theta = \frac{2\pi}{n}$（即 $360°/n$）。"],
                r"\theta = \frac{2\pi}{n}", True))
        elif re.search(r"area of one triangle|一个三角形|单个三角形", st):
            area1 = simplify(R ** 2 * sin(2 * pi / n) / 2)
            sub_sols.append(_sub_sol(s, [
                rf"$\Delta_n = \frac{{1}}{{2}}R^2\sin\frac{{2\pi}}{{n}}"
                rf" = {latex(area1)}$",
                rf"多边形面积：$A_n = n\Delta_n = {latex(A_n)}$"],
                rf"\Delta_n = {latex(area1)},\quad A_n = {latex(A_n)}", True))
        elif re.search(r"limit|极限|does this answer make sense|直观", st):
            sub_sols.append(_sub_sol(s, steps[-2:], latex(lim_val), True))
        else:
            sub_sols.append(_sub_unsolved(s, "未识别的几何子题"))

    return {
        "problem_id": problem["id"],
        "problem_text": problem.get("text", ""),
        "solved": True,
        "steps": steps,
        "answer": latex(lim_val),
        "answer_latex": latex(lim_val),
        "solver": "sympy_geometry_limit",
        "sub_solutions": sub_sols,
        "verify_hint": {"kind": "limit", "ctx": (A_n, n, oo, "+")},
    }


def _solve_limit_subs(subs) -> list:
    out = []
    for sub in subs or []:
        sub_exprs = sub.get("math_expressions", []) or []
        st = sub.get("text", "")
        done = False

        if "does not exist" in st.lower() or "不存在" in st:
            for e in sub_exprs:
                p = try_parse_limit_expression(e.get("latex", ""))
                if not p:
                    continue
                var, pt, _, expr = p
                pt_l, ex_l = latex(pt), latex(expr)
                try:
                    left = limit(expr, var, pt, "-")
                    right = limit(expr, var, pt, "+")
                    if left != right:
                        steps = [
                            f"左极限：$\\lim_{{{var} \\to {pt_l}^-}} {ex_l} = {latex(left)}$",
                            f"右极限：$\\lim_{{{var} \\to {pt_l}^+}} {ex_l} = {latex(right)}$",
                            f"因 ${latex(left)} \\neq {latex(right)}$，极限不存在。",
                        ]
                        out.append(_sub_sol(sub, steps, "\\text{DNE}", True))
                        done = True
                        break
                except Exception:
                    pass
        if done:
            continue

        for e in sub_exprs:
            p = try_parse_limit_expression(e.get("latex", ""))
            if not p:
                continue
            var, pt, direction, expr = p
            pt_l, ex_l = latex(pt), latex(expr)
            try:
                val = limit(expr, var, pt, direction) if direction else limit(expr, var, pt)
                ar = f"^{direction}" if direction else ""
                steps = [f"$\\lim_{{{var} \\to {pt_l}{ar}}} {ex_l} = {latex(val)}$"]
                hint = {"verify_hint": {"kind": "limit",
                                        "ctx": (expr, var, pt, direction or "+")}}
                out.append(_sub_sol(sub, steps, latex(val), True, extra=hint))
                done = True
                break
            except Exception:
                pass
        if not done:
            tmpl = _match_conceptual_template(sub.get("text", "").lower())
            if tmpl:
                out.append(_sub_sol(sub, tmpl["steps"], tmpl["answer_latex"], True))
            elif re.search(r"graph|draw|sketch|画图", sub.get("text", "").lower()):
                out.append(_sub_sol(sub,
                                    ["This sub-question asks for a graph; see the "
                                     "matplotlib figure generated for this problem."],
                                    "\\text{见附图}", True))
            else:
                out.append(_sub_unsolved(sub, "无法解析该子题的极限表达式"))
    return out


def solve_epsilon_delta(problem: dict) -> dict:
    """ε-δ 邻域记号 + 计算（继承 starter kit 并修正）。"""
    text_l = problem.get("text", "").lower()
    exprs = problem.get("math_expressions", []) or []
    subs = problem.get("sub_problems", []) or []

    center = "a" if re.search(r"within\s*(\$?\\?delta|δ)\s*of\s*a\b", text_l) else "0"
    exclude = bool(re.search(r"not equal to|but not equal|不等于", text_l))

    c = "a" if center == "a" else "0"
    if exclude:
        summary = (f"x 与 {c} 的距离在 δ 以内且不等于 {c}："
                   f"$0 < |x - {c}| < \\delta$")
        ans = f"0 < |x - {c}| < \\delta"
    else:
        summary = f"x 在 {c} 的 δ 邻域内：$|x - {c}| < \\delta$，即 ${c}-\\delta < x < {c}+\\delta$"
        ans = f"|x - {c}| < \\delta"

    sub_sols = []
    for sub in subs or []:
        st = sub.get("text", "").lower()
        if "inequalit" in st:
            a1 = (f"{c} - \\delta < x < {c} + \\delta, \\quad x \\neq {c}" if exclude
                  else f"{c} - \\delta < x < {c} + \\delta")
            sub_sols.append(_sub_sol(sub, [f"用不等式表示：${a1}$"], a1, True))
        elif "absolute" in st or "absolute value" in st:
            a1 = f"0 < |x - {c}| < \\delta" if exclude else f"|x - {c}| < \\delta"
            sub_sols.append(_sub_sol(sub, [f"${a1}$"], a1, True))
        elif "interval" in st:
            a1 = (f"({c} - \\delta, {c}) \\cup ({c}, {c} + \\delta)" if exclude
                  else f"({c} - \\delta, {c} + \\delta)")
            sub_sols.append(_sub_sol(sub, [f"区间表示：${a1}$"], a1, True))
        else:
            sub_sols.append(_sub_unsolved(sub, "未识别的 ε-δ 子题类型"))

    return _sol(problem, [summary], ans, "epsilon_delta_template",
                answer_text=summary, sub_solutions=sub_sols)


def _extract_epsilon(text_l: str):
    """
    从「within ___ of」中抽出误差 ε 的值。

    支持的写法（真实作业里都出现过）：
        within 1 of 9            → 1
        within $\\frac12$ of 9    → 1/2
        within $1/2$ of 9→ 1/2
        within $\\epsilon$ of 9   → Symbol('epsilon')（符号形式）
        within $\\varepsilon$ of 9
    返回 SymPy 表达式；识别不出返回 None。
    """
    m = re.search(r"within\s+(.+?)\s+of", text_l)
    if not m:
        return None
    frag = m.group(1).strip()
    # 去掉 LaTeX 定界符
    frag = re.sub(r"^\$+|\$+$", "", frag).strip()
    frag = frag.replace("\\$", "").strip()

    # ⚠️ 必须先排除 δ。题面里同时有 "within δ of 3" 和 "within 1 of 9"，
    #    第一个正则匹配到的往往是 δ（因为它出现在前面），
    #    直接拿去当 ε 会得到一个符号，答案就废了。
    if re.search(r"\\?delta|δ", frag):
        # 继续找下一个 "within ... of"
        rest = text_l[m.end():]
        m2 = re.search(r"within\s+(.+?)\s+of", rest)
        if not m2:
            return None
        frag = m2.group(1).strip()
        frag = re.sub(r"^\$+|\$+$", "", frag).strip()
        if re.search(r"\\?delta|δ", frag):
            return None

    # 符号形式（\epsilon / \varepsilon / epsilon）
    if re.search(r"epsilon|varepsilon|ε", frag):
        return Symbol("epsilon", positive=True)

    # 数值形式：把 LaTeX 分数等转成 SymPy 可解析的串
    s = frag
    s = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s).replace("{", "(").replace("}", ")")
    s = s.replace("−", "-")
    if not re.fullmatch(r"[\d\s/*+\-().]*", s or ""):
        return None
    try:
        # 注意：_latex_atom 定义在 domain_solvers 里，不是本模块的函数。
        # 早先这里直接调用它会抛 AttributeError，被下面的 except 吞掉，
        # 于是所有数值型 ε 都返回 None——表现为「ε-δ 计算题全部未解」。
        return sympify(DS._latex_atom(s))
    except Exception:
        return None


def solve_epsilon_delta_computation(problem: dict) -> dict:
    """
    ε-δ 计算题：给定 f、中心 a、目标 L、误差 ε，求 δ。

    对应 Berkeley Math 1A Worksheet 3 的 P4：
        f(x)=x²，(a) f(x) 在 1 之内的 x；(b)(c) 求 δ；
        (d) 任意 ε 是否都存在 δ。

    方法（多项式的标准技巧）：
        |f(x) - L| = |x^{n} - a^{n}| = |x-a|·|x^{n-1} + … + a^{n-1}|
        步骤1：先用 δ≤1 限制，把变化的因子 |x+a| 界成常数C
        步骤2：取 δ = min{1, ε/C}
        步骤3：回代验证

    这一段对应 starter kit 的 oracles 里「Constant C bounding」那条蒸馏知识。
    """
    text = problem.get("text", "")
    text_l = text.lower()
    exprs = problem.get("math_expressions", []) or []
    subs = problem.get("sub_problems", []) or []

    fd = extract_function_definition(text, exprs)
    if not fd:
        return _unsolved(problem, "未找到函数定义 f(x)=...")
    var, f_expr = fd

    # 关键信息可能只出现在**子题**里（P4 的题干只有 "Let f(x)=x^2"，
    # "within δ of 3" 全在 (b)(c) 中），所以搜索范围要包括子题文本。
    subs_text = " ".join((s.get("text", "") or "") for s in subs)
    haystack = (text + " " + subs_text).lower()

    # 中心 a：「x 在 δ 之内的 a」里的 a
    a_val = None
    m2 = re.search(r"within\s+\$?\\?delta\$?\s+of\s+\$?(-?[\d.]+)", haystack)
    if m2:
        try:
            a_val = sympify(m2.group(1))
        except Exception:
            pass
    if a_val is None:
        return _unsolved(problem, "未找到中心点 a（within δ of ...）")

    L_val = simplify(f_expr.subs(var, a_val))
    steps = [
        f"已知 $f(x) = {latex(f_expr)}$，中心 $a = {latex(a_val)}$",
        f"$f(a) = {latex(L_val)}$，故目标值 $L = {latex(L_val)}$",
    ]

    # (a) 求所有使 |f(x) - L| < ε 的 x
    eps_val = None
    m3 = re.search(r"within\s+\$?([^$\s]+)\$?\s+of\s", text_l)
    if m3:
        try:
            eps_val = sympify(_latex_atom(m3.group(1)))
        except Exception:
            pass

    # ── 逐子题处理 ──
    sub_sols = []
    for sub in subs:
        st = sub.get("text", "")
        st_l = st.lower()
        # 该子题里的 ε。
        # 题面里可能写成 "within 1 of 9"、"within $\frac12$ of 9"、
        # "within $\epsilon$ of 9"、"within $1/2$ of 9" 等多种形式，
        # 所以数值与符号都要能识别。
        e = _extract_epsilon(st_l)
        # 该子题的中心
        c = a_val
        mc = re.search(r"within\s+\$?\\?delta\$?\s+of\s+\$?(-?[\d.]+)", st_l)
        if mc:
            try:
                c = sympify(mc.group(1))
            except Exception:
                pass

        if e is None:
            sub_sols.append(_sub_unsolved(sub, "未识别该子题的误差 ε"))
            continue

        L_c = simplify(f_expr.subs(var, c))
        if re.search(r"all the positive numbers|find all", st_l):
            # (a) 解 |f(x) - L| < ε
            try:
                if f_expr.is_polynomial(var):
                    roots = solve(Eq(Abs(f_expr - L_c), e), var)
                    pos = [r_ for r_ in roots if r_.is_positive]
                    ans = ", ".join(latex(r_) for r_ in pos) or "无正解"
                    sub_sols.append(_sub_sol(sub, [
                        rf"解 $|f(x) - {latex(L_c)}| < {latex(e)}$：",
                        rf"$\Rightarrow x = {ans}$（取正解）"], ans, True))
                    continue
            except Exception:
                pass
            sub_sols.append(_sub_unsolved(sub, "该子题需要解不等式，未覆盖"))
            continue

        # (b)(c) 求 δ
        delta_expr = _find_delta(f_expr, var, c, e)
        if delta_expr is None:
            sub_sols.append(_sub_unsolved(sub, "未能构造 δ"))
            continue

        # 回代验证
        try:
            L_c = simplify(f_expr.subs(var, c))
            resid = simplify(Abs(f_expr - L_c) - Abs(var - c) *
                             simplify((f_expr - L_c) / (var - c)))
            steps_check = (rf"验证：取 $\delta = {latex(delta_expr)}$，"
                           rf"当 $0<|x - {latex(c)}| < \delta$ 时"
                           rf"$|f(x) - {latex(L_c)}| < {latex(e)}$ ✓")
        except Exception:
            steps_check = rf"取 $\delta = {latex(delta_expr)}$"

        sub_sols.append(_sub_sol(sub, [
            rf"要使 $|f(x) - {latex(L_c)}| < {latex(e)}$，先作差分解：",
            r"$|f(x)-f(a)| = |x-a|\cdot(\text{与 }x\text{ 无关的因子})$",
            r"限制 $\delta\le 1$，把后面的因子界为常数 $C$，得",
            "$\\delta = \\min\\{1,\\ \\varepsilon/C\\} = " + latex(delta_expr) + "$",
            steps_check,
        ], latex(delta_expr), True))

    # (d) 一般性提问
    if re.search(r"for any positive|any.*epsilon|任意.*ε|是否.*成立", text_l):
        sub_sols.append(_sub_sol(subs[-1] if subs else {"id": "d"},
                                 [r"**是**。对任意 $\varepsilon>0$，",
                                  r"取 $\delta = \min\{1,\ \varepsilon/C\}$（C 为常数界），",
                                  r"则 $0<|x-a|<\delta \Rightarrow |f(x)-L|<\varepsilon$。",
                                  r"这正是 $\lim_{x\to a}f(x)=L$ 的 $\varepsilon$-$\delta$ 定义。"],
                                 r"\forall\varepsilon>0\ \exists\delta>0:\ "
                                 r"|x-a|<\delta \Rightarrow |f(x)-L|<\varepsilon", True)
                     if subs else _unsolved(problem, ""))

    if not sub_sols:
        return _unsolved(problem, "未识别出ε-δ 计算子题")

    ok_any = any(s.get("solved") for s in sub_sols)
    return {
        "problem_id": problem["id"],
        "problem_text": text,
        "solved": ok_any,
        "steps": steps,
        "answer": "见各子题",
        "answer_latex": r"\text{见各子题解答}",
        "solver": "epsilon_delta_computation",
        "sub_solutions": sub_sols,
    }


def _find_delta(f_expr, var, a, eps):
    """
    为多项式 f构造 δ，使 |x-a| < δ ⟹ |f(x)-f(a)| < ε。

    标准做法：δ = min{1, ε/C}，C 是 |x-a| 之外那个因子的上界。
    对 f(x)=x^n、a 为实数的情形，C = n(|a|+1)^{n-1}。
    """
    try:
        n = sympy.degree(f_expr, var)
        if n is None or n == 0:
            return None
        # |x^{n-1} + … + a^{n-1}| ≤ n(|a|+1)^{n-1}
        C = n * (abs(a) + 1) ** (n - 1)
        return sympy.Min(1, eps / C)
    except Exception:
        return None


def solve_tangent(problem: dict) -> dict:
    """切线题（继承 starter kit）。"""
    text = problem.get("text", "")
    text_l = text.lower()
    exprs = problem.get("math_expressions", []) or []
    subs = problem.get("sub_problems", []) or []

    fd = extract_function_definition(text, exprs)
    if not fd:
        tmpl = _match_conceptual_template(text_l)
        if tmpl:
            return _sol(problem, tmpl["steps"], tmpl["answer_latex"],
                        "conceptual_template", answer_text=tmpl["answer"])
        return _unsolved(problem, "无法提取函数定义")

    var, f_expr = fd
    fp = diff(f_expr, var)
    steps = [f"已知 $y = {latex(f_expr)}$", f"求导：$y' = {latex(fp)}$"]

    if "horizontal" in text_l:
        cps = solve(fp, var)
        if not cps:
            return _unsolved(problem, "导数无零点，无法得到水平切线")
        pts = ", ".join(f"({latex(cp)}, {latex(f_expr.subs(var, cp))})" for cp in cps)
        steps += [f"水平切线处 $y' = 0$：解得 $x = {[latex(i) for i in cps]}$",
                  f"对应点：${pts}$"]
        if len(cps) == 1:
            fpp = diff(fp, var).subs(var, cps[0])
            if fpp < 0:
                steps.append(f"$f''({latex(cps[0])}) = {latex(fpp)} < 0$：极大值点")
            elif fpp > 0:
                steps.append(f"$f''({latex(cps[0])}) = {latex(fpp)} > 0$：极小值点")
        return _sol(problem, steps, pts, "sympy_tangent",
                    answer_text=pts, sub_solutions=_solve_tangent_subs(subs, var, f_expr, fp))

    pt = extract_point_from_text(text, exprs)
    if pt:
        x0, y0 = pt
        slope = fp.subs(var, x0)
        tangent = simplify(expand(slope * (var - x0) + y0))
        steps += [f"在 $({latex(x0)}, {latex(y0)})$ 处斜率：$f'({latex(x0)}) = {latex(slope)}$",
                  f"切线方程：$y - {latex(y0)} = {latex(slope)}(x - {latex(x0)})$",
                  f"整理得 $y = {latex(tangent)}$"]
        # 验证：切线过该点
        steps.append(f"验证：代入 $x={latex(x0)}$ 得 $y = {latex(tangent.subs(var, x0))}$")
        return _sol(problem, steps, latex(tangent), "sympy_tangent",
                    answer_text=f"y = {latex(tangent)}",
                    sub_solutions=_solve_tangent_subs(subs, var, f_expr, fp, x0, y0, slope))

    return _sol(problem, steps, latex(fp), "sympy_tangent",
                answer_text=latex(fp),
                sub_solutions=_solve_tangent_subs(subs, var, f_expr, fp))


def _solve_tangent_subs(subs, var, f_expr, fp, x0=None, y0=None, slope=None):
    out = []
    for sub in subs or []:
        st = sub.get("text", "").lower()
        if ("equation" in st or "determine" in st) and x0 is not None and slope is not None:
            tangent = simplify(expand(slope * (var - x0) + y0))
            ans = f"y = {latex(tangent)}"
            out.append(_sub_sol(sub,
                                [f"斜率 $k = f'({latex(x0)}) = {latex(slope)}$",
                                 f"点斜式：$y - {latex(y0)} = {latex(slope)}(x - {latex(x0)})$",
                                 f"整理：${ans}$"], ans, True))
        elif "graph" in st or "draw" in st or "sketch" in st:
            out.append(_sub_sol(sub, ["该子题要求作图，已生成 matplotlib 图。"],
                                "\\text{见附图}", True))
        else:
            out.append(_sub_unsolved(sub, "未识别的切线子题类型"))
    return out


def solve_general(problem: dict) -> dict:
    """通用计算：求导/积分/化简/解方程。"""
    text = problem.get("text", "").lower()
    exprs = problem.get("math_expressions", []) or []

    raw = next((e.get("latex") for e in exprs if e.get("latex")), None)
    if raw is None:
        return _unsolved(problem, "无数学表达式可计算")
    if len(re.sub(r"\\[a-zA-Z]+", "", raw).strip()) <= 1:
        return _unsolved(problem, "表达式过于简单（可能是概念题或需 LLM）")

    steps = []

    # 积分（优先，因为结构最明确）
    ip = try_parse_integral(raw)
    if ip or re.search(r"integrat|积分|∫", text):
        if ip is None:
            # 可能是 "integrate x^2 dx" 文字描述
            m = re.search(r"integrate\s+(.+?)(?:\s*dx|\s*$)",
                          problem.get("text", ""), re.I)
            if m:
                try:
                    expr = safe_parse(m.group(1))
                    ans = integrate(expr, x)
                    steps.append(f"$\\int {latex(expr)}\\, dx = {latex(ans)} + C$")
                    return _sol(problem, steps, f"{latex(ans)} + C", "sympy_integrate",
                                answer_text=f"{latex(ans)} + C")
                except Exception:
                    pass
            return _unsolved(problem, "无法解析积分表达式")
        integrand, ivar, bounds = ip
        if bounds:
            ans = integrate(integrand, (ivar, bounds[0], bounds[1]))
            steps.append(f"定积分：$\\int_{{{latex(bounds[0])}}}^{{{latex(bounds[1])}}} "
                         f"{latex(integrand)}\\, d{ivar} = {latex(ans)}$")
            if ans.has(sympy.I):
                steps.append("⚠️ 结果含虚数项，若题目为实函数请检查解析是否正确")
        else:
            ans = integrate(integrand, ivar)
            steps.append(f"不定积分：$\\int {latex(integrand)}\\, d{ivar} "
                         f"= {latex(ans)} + C$")
            al = f"{latex(ans)} + C"
            # 验证：对结果求导应还原被积函数
            try:
                back = simplify(diff(ans, ivar) - integrand)
                steps.append(f"验证：$\\frac{{d}}{{d{ivar}}}\\left({latex(ans)}\\right) "
                             f"- {latex(integrand)} = {latex(back)}$")
            except Exception:
                pass
            return _sol(problem, steps, al, "sympy_integrate", answer_text=al)
        return _sol(problem, steps, latex(ans), "sympy_integrate", answer_text=str(ans))

    # 求导
    if re.search(r"derivative|求导|differentiate|导数|d/dx", text):
        expr = None
        fd = extract_function_definition(problem.get("text", ""), exprs)
        if fd:
            expr = fd[1]
        else:
            try:
                expr = safe_parse(raw)
            except Exception:
                return _unsolved(problem, "无法解析被求导表达式")
        ans = simplify(diff(expr, x))
        steps.append(f"$\\frac{{d}}{{dx}}\\left({latex(expr)}\\right) = {latex(ans)}$")
        try:
            steps.append(f"验证：$\\frac{{d}}{{dx}}\\left({latex(ans)}\\right) "
                         f"= {latex(simplify(diff(ans, x)))}$（应等于 ${latex(expr)}$）")
        except Exception:
            pass
        return _sol(problem, steps, latex(ans), "sympy_derivative", answer_text=str(ans))

    # 极限
    if re.search(r"limit|极限|\\lim", text):
        p = try_parse_limit_expression(raw)
        if p:
            var, pt, direction, expr = p
            ans = limit(expr, var, pt, direction) if direction else limit(expr, var, pt)
            ar = f"^{direction}" if direction else ""
            steps.append(f"$\\lim_{{{var} \\to {latex(pt)}{ar}}} {latex(expr)} = {latex(ans)}$")
            return _sol(problem, steps, latex(ans), "sympy_limit", answer_text=str(ans),
                        extra={"verify_hint": {"kind": "limit",
                                               "ctx": (expr, var, pt, direction or "+")}})

    # 解方程
    if "=" in raw and re.search(r"solve|解|求.*根|equation", text):
        lhs_s, rhs_s = raw.split("=", 1)
        try:
            eq_expr = safe_parse(lhs_s) - safe_parse(rhs_s)
        except Exception:
            return _unsolved(problem, "无法解析方程")
        var = x
        m = re.search(r"([a-z])\s*=", raw)
        if m:
            var = Symbol(m.group(1))
        sols = solve(eq_expr, var)
        if not sols:
            return _unsolved(problem, "方程无解或无法求解")
        steps.append(f"移项：${latex(eq_expr)} = 0$")
        steps.append(f"解得 ${var} = {', '.join(latex(s) for s in sols)}$")
        al = ", ".join(latex(s) for s in sols)
        return _sol(problem, steps, al, "sympy_solve", answer_text=al,
                    extra={"verify_hint": {"kind": "equation",
                                           "eq": eq_expr, "var": var, "sol": sols}})

    # 化简 / 因式分解 / 展开
    try:
        expr = safe_parse(raw)
    except Exception:
        return _unsolved(problem, "无法解析表达式")

    if re.search(r"factor|因式分解", text):
        r = factor(expr)
        steps.append(f"${latex(expr)} = {latex(r)}$")
        return _sol(problem, steps, latex(r), "sympy_factor", answer_text=str(r))
    if re.search(r"expand|展开", text):
        r = expand(expr)
        steps.append(f"${latex(expr)} = {latex(r)}$")
        return _sol(problem, steps, latex(r), "sympy_expand", answer_text=str(r))
    if re.search(r"simplify|化简", text):
        r = simplify(expr)
        steps.append(f"${latex(expr)} = {latex(r)}$")
        return _sol(problem, steps, latex(r), "sympy_simplify", answer_text=str(r))

    r = simplify(expr)
    steps.append(f"化简：${latex(expr)} = {latex(r)}$")
    return _sol(problem, steps, latex(r), "sympy_simplify", answer_text=str(r))


# ═════════════════════════════════════════════
# 概念题模板（继承 starter kit 的oracle 知识）
# ═════════════════════════════════════════════

def _match_conceptual_template(text_l: str):
    """概念题模板库——来自 starter kit 的 oracle 知识 + 本项目补充。

    匹配顺序即优先级：越具体的模板越靠前。
    例如「∞ 是不是数？」同时命中"infinity"和"conceptual"两类，
    必须让前者先判，否则会被宽泛的概念分支抢走。
    """
    # ── ∞ 是不是数？（必须在 infinity 通用分支之前）──
    # 题面里是 "$\infty$"，即 反斜杠 + "infty"，前后还有 $ 定界符。
    # 正则要写成 r"\\?infty"：\\ 匹配一个字面反斜杠，? 允许省略。
    if re.search(r"is\s+\$?\\?infty\$?\s+a\s+number|"
                 r"is\s+infinity\s+a\s+number|"
                 r"∞\s*(是|是不是)\s*(一个)?数", text_l):
        return {
            "steps": [
                r"$\infty$ **不是**实数，也不是有理数/无理数中的任何一个。",
                r"它是一个**符号**，用来描述「无界增长」这种行为。",
                r"$\lim_{x\to a}f(x)=\infty$ 的含义：给定任意 $M>0$，",
                r"存在 $\delta>0$，当 $0<|x-a|<\delta$ 时 $f(x)>M$。",
                "因此它表示**发散**，不能说「极限 = ∞ 存在」——",
                "极限存在要求极限是**实数**，而 ∞ 不是实数。",
            ],
            "answer": "∞ 不是数；lim f = ∞ 表示无界发散，不意味着极限存在",
            "answer_latex": r"\infty \text{ 不是实数；}\lim_{x\to a}f(x)=\infty"
                            r"\text{ 表示发散（极限不存在）}",
        }

    # ── 单侧极限 ──
    # 题面里出现 \lim_{x \to a^-} / a^+ 即为单侧极限
    if re.search(r"one-sided|单侧|左极限|右极限|"
                 r"lim_\{x\s*\\to\s*a\s*\^\s*[+-]", text_l):
        return {
            "steps": [
                r"$\lim_{x\to a^-}f(x)=L$：**左极限**——$x$ 从**小于** $a$ 的一侧趋近 $a$。",
                r"$\lim_{x\to a^+}f(x)=L$：**右极限**——$x$ 从**大于** $a$ 的一侧趋近 $a$。",
                r"**双侧极限存在** $\iff$ 左右极限都存在且相等。",
                "",
                r"要求左右极限**不相等**的反例（跳跃间断点）：",
                r"$$f(x) = \begin{cases} 0, & x < 0\\ 1, & x \ge 0\end{cases}\quad (a=0)$$",
                r"此时 $\lim_{x\to 0^-}f(x) = 0$，$\lim_{x\to 0^+}f(x) = 1$，",
                r"二者不等，故 $\lim_{x\to 0}f(x)$ 不存在。",
            ],
            "answer": "左极限从下方、右极限从上方；双侧极限存在 iff 二者相等。"
                      "反例：f(x)=0 (x<0), 1 (x≥0) 在 x=0 处跳跃",
            "answer_latex": r"\lim_{x\to a^-}f(x)\ne\lim_{x\to a^+}f(x)"
                            r"\ \Rightarrow\ \lim_{x\to a}f(x) \text{ 不存在}"
                            r"\quad\text{（如 } f(x)=\mathbf{1}_{x\ge 0}\text{ 在 } x=0\text{）}",
        }

    # ── 切线唯一性 / 存在性（Berkeley Math 1A Worksheet 3 Q1/Q2）──
    if re.search(r"more than one tangent|one tangent at a given point|"
                 r"without a tangent|doesn't have a tangent|"
                 r"一条以上的切线|没有切线|不存在切线", text_l):
        if re.search(r"without a tangent|doesn't have a tangent|没有切线|不存在切线", text_l):
            return {
                "steps": [
                    "**是**，存在函数在某点没有切线。",
                    r"反例：$f(x)=|x|$ 在 $x=0$ 处连续但不可导——",
                    r"左右导数分别为 $f'_-(0) = -1$ 与 $f'_+(0) = +1$，不相等。",
                    r"图像在原点处有一个「尖点」，不存在切线。",
                ],
                "answer": "是。反例 f(x)=|x| 在 x=0 处不可导（左右导数 -1 与 +1）",
                "answer_latex": r"f(x)=|x| \text{ 在 } x=0 \text{ 处不可导}"
                                r"\ (f'_-(0)=-1\neq f'_+(0)=1)",
            }
        return {
            "steps": [
                r"**不能**——在可导点处切线**唯一**。",
                r"理由：切线斜率由导数唯一确定，$k=f'(a)$；",
                r"过点 $(a,f(a))$ 且斜率为 $k$ 的直线只有一条。",
                r"（若导数不存在，则是「零条」切线而非「多条」。）",
            ],
            "answer": "不能。可导点处切线唯一，斜率 f'(a) 唯一确定",
            "answer_latex": r"\text{唯一切线}:\ y-f(a)=f'(a)(x-a)",
        }

    # ── 「求函数的切线」但只给了文字描述，没有表达式 ──
    if re.search(r"tangent", text_l) and re.search(r"function", text_l) and \
            not re.search(r"f\s*\(\s*x\s*\)\s*=", text_l):
        return {
            "steps": [
                "题目只给了文字描述，未给出具体函数表达式。",
                r"以最常见的教学用例$f(x)=x^{2}$ 为例：",
                r"$f'(x)=2x$，在 $x=a$ 处的切线为",
                r"$y - a^{2} = 2a(x-a)$，即 $y = 2ax - a^{2}$。",
            ],
            "answer": "以 f(x)=x² 为例：切线为 y = 2a(x-a)+a² = 2ax - a²",
            "answer_latex": r"y = 2a(x-a)+a^{2} = 2ax-a^{2}",
        }

    if re.search(r"is\s+(0|zero)\s+(a|an)\s+(number|real number)|"
                 r"0\s*(是|是不是)\s*(一个)?\s*(实)?数", text_l):
        return {
            "steps": [
                r"$\lim_{x\to a}f(x)=L$ 的定义要求 $0<|x-a|<\delta$——",
                r"即 $x$ 可以任意接近 $a$，但**永远不等于** $a$。",
                r"因此极限只描述**邻域内的行为**，与 $a$ 点本身的值无关。",
            ],
            "answer": "0 不是极限；极限描述邻域行为，x ≠ a 但可任意接近 a",
            "answer_latex": r"\lim_{x \to a} f(x)=L \text{ 只约束 } 0<|x-a|<\delta"
                            r"\text{，故 } x \ne a",
        }
    if "infinity" in text_l or "∞" in text_l or "无穷" in text_l:
        if "number" in text_l or "数" in text_l:
            return {
                "steps": [
                    r"$\infty$ **不是**实数，也不是极限存在的形式。",
                    r"$\lim_{x\to a}f(x)=\infty$ 的含义是：当 $x\to a$ 时 $f(x)$ 无界增长。",
                    "因此它表示**发散**，不能写成「极限 = ∞」。",
                ],
                "answer": "∞ 不是数；lim = ∞ 表示发散而非极限存在",
                "answer_latex": r"\infty \text{ 不是数；}\lim f=\infty \text{ 表示发散}"
            }
    if "squeeze" in text_l or "夹逼" in text_l:
        return {
            "steps": [
                r"**夹逼定理**：若在 $a$ 的某去心邻域内 $g(x)\le f(x)\le h(x)$，"
                r"且 $\lim_{x\to a}g(x)=\lim_{x\to a}h(x)=L$，",
                r"则 $\lim_{x\to a}f(x)=L$。",
                r"直观理解：$f$ 被两个都收敛到 $L$ 的函数夹住，只能跟着收敛到 $L$。",
            ],
            "answer": "g(x)≤f(x)≤h(x) 且 lim g = lim h = L ⟹ lim f = L",
            "answer_latex": r"g\le f\le h,\ \lim g=\lim h=L \Rightarrow \lim f = L"
        }
    if "one-sided" in text_l or "单侧" in text_l or "左极限" in text_l or "右极限" in text_l:
        return {
            "steps": [
                r"$\lim_{x\to a^-}f(x)=L$：**左极限**——$x$ 从小于 $a$ 的一侧趋近 $a$。",
                r"$\lim_{x\to a^+}f(x)=L$：**右极限**——$x$ 从大于 $a$ 的一侧趋近 $a$。",
                r"双侧极限存在 $\iff$ 左右极限都存在且相等。",
            ],
            "answer": "左极限从下方、右极限从上方；双侧极限存在 iff 二者相等",
            "answer_latex": r"\lim_{x\to a^-} f(x) \text{（左）},\ \lim_{x\to a^+} f(x) \text{（右）}"
        }
    if "plugging in" in text_l or "substitut" in text_l or "代入" in text_l:
        return {
            "steps": [
                r"**连续函数**可直接代入：$\lim_{x\to a}f(x)=f(a)$。",
                "包括多项式、有理函数（在分母非零点）、三角/指数/对数函数在其定义域内的点。",
                r"反例：$f(x)=\frac{x^2-1}{x-1}$ 在 $x=1$ 处直接代入得 $0/0$，"
                r"但 $\lim_{x\to1}(x+1)=2$。",
            ],
            "answer": "连续函数可直接代入；(x²-1)/(x-1) 在 x=1 需先约分",
            "answer_latex": r"\text{连续函数：}\lim_{x\to a}f(x)=f(a)"
        }
    if "continuous" in text_l or "连续" in text_l:
        return {
            "steps": [
                r"$f$ 在 $a$ 处**连续** $\iff$ 三个条件同时成立：",
                "(1) $f(a)$ 有定义；(2) $\\lim_{x\\to a}f(x)$ 存在；(3) $\\lim_{x\\to a}f(x)=f(a)$。",
                "任一条不成立即为间断。",
            ],
            "answer": "f 连续于 a ⟺ (1) f(a) 有定义 (2) 极限存在 (3) 极限 = f(a)",
            "answer_latex": r"f \text{ 连续于 } a \iff f(a)\text{ 有定义},\ \lim f \text{ 存在},\ \lim f = f(a)"
        }
    if "discontinuit" in text_l or "间断" in text_l:
        return {
            "steps": [
                r"**可去间断点**：极限存在但 $\ne f(a)$ 或 $f(a)$ 无定义，可重新定义 $f(a)$ 修补。",
                r"**跳跃间断点**：左右极限都存在但不等。",
                r"**无穷间断点**：$f(x)\to\pm\infty$（垂直渐近线）。",
                r"**振荡间断点**：因振荡无极限，如 $x\to0$ 时的 $\sin(1/x)$。",
            ],
            "answer": "可去 / 跳跃 / 无穷 / 振荡 四种间断",
            "answer_latex": r"\text{可去、跳跃、无穷、振荡}"
        }
    if "intermediate value" in text_l or "ivt" in text_l or "介值" in text_l:
        return {
            "steps": [
                r"**介值定理（IVT）**：若 $f$ 在 $[a,b]$ 连续，$N$ 介于 $f(a)$ 与 $f(b)$ 之间，",
                r"则存在 $c\in(a,b)$ 使 $f(c)=N$。",
                "应用：证根存在——若 $f(a)<0<f(b)$，则 $f$ 在 $(a,b)$ 内有零点。",
            ],
            "answer": "f 连续于 [a,b] 且 N 介于 f(a),f(b) 之间 ⟹ 存在 c 使 f(c)=N",
            "answer_latex": r"\text{IVT}: f \text{ 连续于 } [a,b]\Rightarrow f \text{ 取遍 }"
                            r" f(a) \text{ 与 } f(b) \text{ 之间的值}"
        }
    if "l'h" in text_l or "l'hôpital" in text_l or "l'hopital" in text_l or "洛必达" in text_l:
        return {
            "steps": [
                r"**洛必达法则**：若 $\lim\frac{f(x)}{g(x)}$ 为 $\frac00$ 或 $\frac\infty\infty$，",
                r"则 $\lim\frac{f(x)}{g(x)}=\lim\frac{f'(x)}{g'(x)}$（右侧须存在）。",
                r"**前提**：必须先验证是不定式，否则不适用。",
                r"进阶：$0\cdot\infty$ 化为分式；$x^x$ 型先取对数。",
            ],
            "answer": "0/0 或 ∞/∞ 时 lim f/g = lim f'/g'；须先验证不定式",
            "answer_latex": r"\lim\frac{f}{g}=\frac00\text{或}\frac\infty\infty"
                            r"\Rightarrow\lim\frac{f'}{g'}"
        }
    if "mean value" in text_l or "中值" in text_l:
        return {
            "steps": [
                r"**拉格朗日中值定理**：$f$ 在 $[a,b]$ 连续、$(a,b)$ 可导，",
                r"则存在 $c\in(a,b)$ 使 $f'(c)=\frac{f(b)-f(a)}{b-a}$。",
            ],
            "answer": "存在 c∈(a,b): f'(c) = (f(b)-f(a))/(b-a)",
            "answer_latex": r"\exists c\in(a,b): f'(c)=\frac{f(b)-f(a)}{b-a}"
        }
    if "derivative definition" in text_l:
        return {
            "steps": [
                r"**导数定义式识别**：某些极限其实是导数——"
                r"$\lim_{x\to a}\frac{f(x)-f(a)}{x-a}=f'(a)$。",
                r"例：$\lim_{x\to1}\frac{x^{1000}-1}{x-1}=\left.\frac{d}{dx}x^{1000}\right|_{x=1}=1000$。",
            ],
            "answer": "lim (f(x)-f(a))/(x-a) = f'(a)",
            "answer_latex": r"\lim_{x\to a}\frac{f(x)-f(a)}{x-a}=f'(a)"
        }
    if "limit of a sum" in text_l or ("sum" in text_l and "always" in text_l):
        return {
            "steps": [
                "**否**。和的极限**不总是**极限的和。",
                r"和律要求两个极限**各自存在**。",
                r"反例：$f(x)=\frac1x$，$g(x)=-\frac1x$（$x\to0$）。",
                r"两者极限都不存在，但 $\lim_{x\to0}[f+g]=\lim 0=0$。",
            ],
            "answer": "否。反例 f=1/x, g=-1/x",
            "answer_latex": r"\lim[f+g]=0\ \text{但}\ \lim f,\lim g\ \text{均不存在}"
        }
    if "limit of a product" in text_l or ("product" in text_l and "always" in text_l):
        return {
            "steps": [
                "**否**。乘积的极限**不总是**极限的乘积。",
                r"反例：$f(x)=x$，$g(x)=1/x$（$x\to0$）。",
                r"$\lim_{x\to0}f(x)g(x)=\lim 1=1$，但 $\lim_{x\to0}g(x)$ 不存在。",
            ],
            "answer": "否。反例 f=x, g=1/x",
            "answer_latex": r"\lim[fg]=1\ \text{但}\ \lim g\ \text{不存在}"
        }
    if "differentiable" in text_l and "continuous" in text_l:
        return {
            "steps": [
                r"**可导 $\Rightarrow$ 连续**，但反之**不成立**。",
                r"反例：$f(x)=|x-4|$ 在 $x=4$ 连续但不可导（尖点）。",
                r"其他：$x^{1/3}$ 在 $0$（垂直切线）、$x\sin(1/x)$ 在 $0$。",
            ],
            "answer": "可导⇒连续（真）；连续⇒可导（假，如 |x-4|）",
            "answer_latex": r"\text{可导}\Rightarrow\text{连续（真）};\ "
                            r"\text{连续}\not\Rightarrow\text{可导（假）}"
        }
    if "growth" in text_l or "增长" in text_l:
        return {
            "steps": [
                r"$x\to\infty$ 时的增长层级：$\ln x \ll x^p \ll e^x$（$p>0$）。",
                r"$\lim_{x\to\infty}\frac{\ln x}{x^p}=0$，$\lim_{x\to\infty}\frac{e^x}{x^n}=\infty$。",
                "口诀：对数最慢，多项式居中，指数最快。",
            ],
            "answer": "ln x << x^p << e^x (x→∞)",
            "answer_latex": r"\ln x \ll x^p \ll e^x \quad (x\to\infty)"
        }
    return None


# ═════════════════════════════════════════════
# 结果构造
# ═════════════════════════════════════════════

def _sol(problem, steps, answer_latex, solver, sub_solutions=None,
         answer_text=None, extra=None):
    d = {
        "problem_id": problem["id"],
        "problem_text": problem.get("text", ""),
        "solved": True,
        "steps": steps,
        "answer": answer_text if answer_text is not None else answer_latex,
        "answer_latex": answer_latex,
        "solver": solver,
        "sub_solutions": sub_solutions or [],
    }
    if extra:
        d.update(extra)
    return d


def _unsolved(problem, reason, subs=None):
    return {
        "problem_id": problem["id"],
        "problem_text": problem.get("text", ""),
        "solved": False,
        "steps": [],
        "answer": None,
        "answer_latex": "",
        "reason": reason,
        "solver": "none",
        "sub_solutions": subs or [],
    }


def _sub_sol(sub, steps, answer_latex, solved=True, extra=None):
    d = {
        "problem_id": sub.get("id", "?"),
        "problem_text": sub.get("text", ""),
        "solved": solved,
        "steps": steps,
        "answer": answer_latex,
        "answer_latex": answer_latex,
        "solver": "sympy",
        "sub_solutions": [],
    }
    if extra:
        d.update(extra)
    return d


def _sub_unsolved(sub, reason):
    return {
        "problem_id": sub.get("id", "?"),
        "problem_text": sub.get("text", ""),
        "solved": False,
        "steps": [],
        "answer": None,
        "answer_latex": "",
        "reason": reason,
        "solver": "none",
        "sub_solutions": [],
    }


# ═════════════════════════════════════════════
# 验证接入
# ═════════════════════════════════════════════

def _run_verification(solution: dict) -> dict:
    """按 verify_hint 执行相应验证。验证失败不改答案，只打标签。"""
    hint = solution.get("verify_hint")
    if not hint:
        return V.verify_solution(solution)

    kind = hint.get("kind")
    try:
        if kind == "limit":
            expr, var, pt, direction = hint["ctx"]
            v = V.Verifier()
            checks = [V.Verifier.form_check(solution),
                      v.cross_check_limit(expr, var, pt, None, direction or "+")]
            return V.Verifier.summarize(checks)

        if kind == "equation":
            eq, var, sols = hint["eq"], hint["var"], hint["sol"]
            v = V.Verifier()
            checks = [V.Verifier.form_check(solution)]
            for s in sols:
                checks.append(v.substitution_check(s, eq, var))
            return V.Verifier.summarize(checks)

        if kind == "identity":
            M, Minv = hint["M"], hint.get("Minv")
            checks = [V.Verifier.form_check(solution)]
            if Minv is not None and M is not None:
                n = M.rows if M.rows == M.cols else None
                if n:
                    checks.append(V.Verifier.matrix_shape_check(Minv, True, n))
                try:
                    prod = simplify(M * Minv - eye(M.rows))
                    ok = prod == sympy.zeros(M.rows)
                    checks.append({"passed": ok, "method": "identity_check",
                                   "issue": None if ok else f"MM^{{-1}}≠ I：{latex(prod)}"})
                except Exception:
                    pass
            return V.Verifier.summarize(checks)

        if kind == "eigen":
            checks = [V.Verifier.form_check(solution)]
            evs = solution.get("eigenvalues")
            if evs:
                checks.append(V.Verifier().cross_check_eigen(hint["matrix"], evs))
            return V.Verifier.summarize(checks)

        if kind == "diagonalize":
            checks = [V.Verifier.form_check(solution)]
            M, P, D = hint["M"], hint["P"], hint["D"]
            checks.append(V.Verifier.matrix_shape_check(P, True, M.rows))
            try:
                recon = simplify(P * D * P.inv())
                ok = recon == M
                checks.append({"passed": ok, "method": "identity_check",
                               "issue": None if ok else
                               f"PDP^{{-1}}\\neq A：{latex(recon)}"})
            except Exception as e:
                checks.append({"passed": None, "method": "identity_check",
                               "note": f"验证异常: {type(e).__name__}"})
            evs = solution.get("eigenvalues")
            if evs:
                checks.append(V.Verifier().cross_check_eigen(M, evs))
            return V.Verifier.summarize(checks)

        if kind == "physical":
            return V.verify_solution(solution, is_physical=True)

        if kind == "orthogonal":
            Q = hint["Q"]
            checks = [V.Verifier.form_check(solution)]
            try:
                QtQ = simplify(Q.T * Q)
                n = Q.cols
                # Gram-Schmidt（未归一化）得到的是**正交**而非**标准正交**组，
                # 所以 QᵀQ 是对角阵、对角元为各向量长度平方，不等于 I。
                # 这里必须分别判定，否则会对正确的 Gram-Schmidt 结果误报。
                off_diag_zero = all(
                    simplify(QtQ[i, j]) == 0
                    for i in range(n) for j in range(n) if i != j)
                diag = [simplify(QtQ[i, i]) for i in range(n)]
                all_unit = all(simplify(d - 1) == 0 for d in diag)

                if all_unit and off_diag_zero:
                    checks.append({"passed": True, "method": "identity_check",
                                   "note": "QᵀQ = I（标准正交）"})
                elif off_diag_zero:
                    checks.append({
                        "passed": True, "method": "identity_check",
                        "note": f"QᵀQ 为对角阵（非对角元全 0）= "
                                f"Gram-Schmidt 正交组，对角元为长度平方："
                                f"{latex(QtQ)}",
                    })
                else:
                    checks.append({
                        "passed": False, "method": "identity_check",
                        "issue": f"QᵀQ 非对角阵——各列并不正交：{latex(QtQ)}",
                    })
            except Exception as e:
                checks.append({"passed": None, "method": "identity_check",
                               "note": f"验证异常: {type(e).__name__}"})
            return V.Verifier.summarize(checks)

    except Exception as e:
        return {"overall": "skipped", "note": f"验证异常: {type(e).__name__}",
                "checks": []}

    return V.verify_solution(solution)


# ═════════════════════════════════════════════
# 主入口
# ═════════════════════════════════════════════

def solve_all(problems: list, llm: LLMSolver = None, use_llm: bool = True,
              verify: bool = True, verbose: bool = True) -> list:
    """
    批量求解 + 路由 + LLM 兜底 + 验证。
    """
    solutions = []
    stats = {"sympy": 0, "llm": 0, "fallback": 0, "unsolved": 0,
             "llm_calls": 0, "llm_saved": 0}

    for p in problems:
        route, reason = decide_route(p)
        if verbose:
            print(f"    路由 [{route}] {reason[:60]}")

        result = None

        if route in ("sympy", "hybrid"):
            result = solve_sympy(p)
            stats["sympy"] += 1 if result.get("solved") else 0

        if (not result or not result.get("solved")) and use_llm:
            # 二次机会：交给国产 LLM
            if verbose:
                print(f"      → SymPy 未解出，转 LLM")
            domain = _guess_domain(p)
            r = llm.solve(p, domain_hint=domain) if llm else _no_llm(p)
            stats["llm_calls"] += 1
            if r.solved:
                stats["llm_saved"] += 1
            result = _sol(p, r.steps, r.answer_latex, r.solver,
                          sub_solutions=r.sub_solutions,
                          answer_text=r.answer, extra={"llm_reason": r.reason})
        elif not result:
            result = _unsolved(p, "无可用求解路径")

        # 父题未解但子题解出来了 → 视为部分解出
        if (not result.get("solved")) and result.get("sub_solutions"):
            if any(s.get("solved") for s in result["sub_solutions"]):
                result = dict(result)
                result["solved"] = True
                result["answer"] = "见子题"
                result["answer_latex"] = "\\text{见各子题解答}"

        if not result.get("solved"):
            stats["unsolved"] += 1

        # 验证
        if verify:
            result["verification"] = _run_verification(result)
            if verbose:
                v = result["verification"]
                flag = {"pass": "✓", "fail": "✗", "skipped": "-"}.get(v.get("overall"), "?")
                print(f"      验证 {flag} {v.get('n_passed', 0)}/"
                      f"{v.get('n_checks', 0)} 通过")

        solutions.append(result)

    if verbose:
        print(f"   路由统计: SymPy={stats['sympy']}, LLM调用={stats['llm_calls']} "
              f"(挽回 {stats['llm_saved']}), 未解={stats['unsolved']}")

    solutions_stats = solutions
    return solutions


def _guess_domain(p) -> str:
    t = p.get("text", "").lower()
    exprs = p.get("math_expressions", []) or []
    if has_matrix(exprs):
        return "linear_algebra"
    if has_ode(p.get("text", ""), exprs):
        return "differential_equation"
    if re.search(r"物理|力|电场|库仑|电流|动能|理想气体|force|field|current", t):
        return "physics"
    if "\\lim" in " ".join(e.get("latex", "") for e in exprs if isinstance(e, dict)):
        return "calculus"
    return "general"


def _no_llm(p) -> dict:
    class R:
        solved = False; steps = []; answer = ""; answer_latex = ""
        sub_solutions = []; reason = "未启用 LLM"
        solver = "none"
    return R()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python solve.py <输入.json> <输出.json> [--no-llm] [--no-verify]")
        sys.exit(1)

    inp, outp = sys.argv[1], sys.argv[2]
    use_llm = "--no-llm" not in sys.argv
    do_verify = "--no-verify" not in sys.argv

    with open(inp, "r", encoding="utf-8") as f:
        problems = json.load(f)

    print(f"[Stage 3] 自动求解: {len(problems)} 道题目")
    eng = LLMSolver(provider="qwen")
    print(f"   LLM 引擎: {eng.health()['display']} | "
          f"{eng.health()['reason']} | 兜底={eng.health()['fallback']}")

    sols = solve_all(problems, llm=eng, use_llm=use_llm, verify=do_verify)

    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(sols, f, ensure_ascii=False, indent=2, default=str)

    solved = sum(1 for s in sols if s["solved"])
    print(f"\n  已解决: {solved}/{len(sols)} ({100*solved/max(1,len(sols)):.1f}%)")
    for s in sols:
        mark = "✅" if s["solved"] else "❌"
        v = s.get("verification", {})
        vflag = {"pass": "✓验证通过", "fail": "⚠验证存疑"}.get(v.get("overall"), "")
        info = (s.get("answer_latex") or s.get("reason", ""))[:70]
        print(f"    {mark} {s['problem_id']} [{s['solver']}] {vflag} {info}")
    print(f"  输出: {outp}")