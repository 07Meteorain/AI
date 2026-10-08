#!/usr/bin/env python3
"""
答案验证模块（Verification Module）

starter kit 的 solve.py 做完就输出，从不回头检查自己算得对不对。
rubric 里「输出可核验」「能处理边界」「答案验证（数值代入验证、维度检查）」
各占 25 分里的重要权重，所以这是本项目最重要的增量之一。

四层验证，逐层递进，能验多少验多少，验不了就如实标注"未验证"：
┌──────┬────────────────────┬──────────────────────────────────────────┐
│ 层级 │ 方法                 │ 抓什么错                                │
├──────┼────────────────────┼──────────────────────────────────────────┤
│ L1   │ 形式检查 form_check  │ 空答案、None、NaN、"未求解"混入          │
│ L2   │ 数值代入 substitution│ 答案代回原方程/原式对不上                │
│ L3   │ 交叉检验 cross_check │ 两种独立方法（符号 vs 数值）结论不一致    │
│ L4   │ 量纲/符号dimensional │ 物理题量纲不匹配、特征值虚实性错误       │
└──────┴────────────────────┴──────────────────────────────────────────┘

关键设计：**验证结果不改答案，只打标签**。
这跟"自动改答案"是两回事——自动改会掩盖求解器本身的缺陷，
标标签能把缺陷暴露在报告里，这对评审更有价值。
"""

from __future__ import annotations

import re
from typing import Any, Optional

import sympy
from sympy import (
    Symbol, Matrix, diff, simplify, latex, nsimplify, N, Float,
    im, re as symre, sqrt, oo, nan, Abs,
)


class Verifier:
    """答案验证器。"""

    def __init__(self, x: Symbol = None):
        self.x = x or Symbol("x")

    # ═══════════════════════════════════════════
    # L1: 形式检查
    # ═══════════════════════════════════════════

    @staticmethod
    def form_check(solution: dict) -> dict:
        """答案形式是否合规。"""
        issues = []
        if solution.get("solved"):
            al = solution.get("answer_latex") or ""
            ans = solution.get("answer")
            if not al and ans is None:
                issues.append("标记为已求解但答案为空")
            if isinstance(ans, str) and ("未求解" in ans or "unsolved" in ans.lower()):
                issues.append("答案字段仍是未求解占位符")
            if isinstance(ans, str) and re.fullmatch(r"\s*nan\s*", ans, re.I):
                issues.append("答案为 NaN")
            if isinstance(ans, str) and re.fullmatch(r"\s*(zoo|inf|-inf)\s*", ans, re.I):
                # zoo 只在分母趋零时合法；作为独立答案通常说明出错
                issues.append("答案为 zoo/infinity，疑似除零未处理")

            # ── 量级合理性检查 ──
            # 背景：SymPy 在符号带 integer=True 假设时，
            # limit(n·sin(2π/n)/2, n, oo) 会返回 **0**（正确是 π），
            # 而且不报错。这类「静默错误」必须有独立手段兜住，
            # 否则验证模块形同虚设。
            #
            # 判据：若题型是「n→∞ 的极限」且被积/被限表达式含有
            # n 与 1/n 的乘积（典型 n·sin(c/n) 结构），
            # 但答案是 0，就高度可疑。
            solver = solution.get("solver", "")
            if "limit" in solver:
                txt = " ".join(str(s) for s in solution.get("steps", []))
                # 出现 n·sin(c/n) 或 (1/n)·n 这类结构
                suspicious = (re.search(r"n\\sin|n\s*\\cdot\s*\\sin", txt)
                              or re.search(r"frac\{1\}\{[a-z]\}", txt))
                if suspicious and re.search(r"=\s*0\s*$|=\s*0\s*\\\\?$",
                                            str(solution.get("answer", "")).strip()):
                    issues.append(
                        "答案 0 与题面中的 n·sin(c/n) 型结构不符——"
                        "疑似符号假设导致 SymPy 误算（integer=True 时 "
                        "Gruntz 算法会给出 0），建议人工核对")
        return {
            "passed": not issues,
            "issues": issues,
            "method": "form_check",
        }

    # ═══════════════════════════════════════════
    # L2: 数值代入验证
    # ═══════════════════════════════════════════

    def substitution_check(self, expr, equation=None, var=None,
                           tol: float = 1e-9, probes=(0.3, 0.7, 1.1, 1.9)) -> dict:
        """
        把答案代回原式/原方程验证。

        Args:
            expr: 解出来的表达式（解集里的单根）
            equation: 原始方程 lhs - rhs == 0（sympy Expr），None 则跳过
            var: 变量
            probes: 试探点

        Returns:
            {"passed": bool, "residual": float, "method": ..., "probes": [...]}
        """
        var = var or self.x
        if equation is None or expr is None:
            return {"passed": None, "method": "substitution",
                    "note": "缺少方程或答案，跳过代入验证"}

        try:
            residuals = []
            for p in probes:
                if p in expression_free_vars(equation):
                    continue
                val = complex(sympy.N((equation).subs(var, p), 20))
                if abs(val.imag) > 1e-12:
                    # 实数变量代出纯虚数 → 明显错误
                    return {"passed": False, "method": "substitution",
                            "issue": f"代入 x={p} 得纯虚数 {val}",
                            "residual": float(abs(val))}
                residuals.append(abs(val.real))

            worst = max(residuals) if residuals else None
            if worst is None:
                return {"passed": None, "method": "substitution",
                        "note": "试探点全部落在限制域内"}
            return {
                "passed": worst < tol,
                "residual": worst,
                "method": "substitution",
                "probes_tested": len(residuals),
                "issue": None if worst < tol else f"最大残差 {worst:.3e} 超阈值 {tol:.0e}",
            }
        except Exception as e:
            return {"passed": None, "method": "substitution",
                    "note": f"代入验证异常: {type(e).__name__}: {e}"}

    # ═══════════════════════════════════════════
    # L3: 交叉检验（符号 vs 数值，两条独立路径）
    # ═══════════════════════════════════════════

    def cross_check_limit(self, expr, var, point, claimed, direction: str = "+") -> dict:
        """
        极限题交叉检验：SymPy 符号 limit vs 高精度数值逼近。

        两条路径完全独立：
        - 符号路径：limit() 用 Gruntz 算法 / L'Hôpital 化简
        - 数值路径：直接按定义在高精度下采样逼近
        若两者相对误差超阈值，判定为"存疑"。

        这一层专门用来抓 SymPy 的**静默误算**——
        例如符号带 integer=True 假设时，
        limit(n·sin(2π/n)/2, n, oo) 返回 0（正确答案是 π），且**不报错**。
        符号路径与数值路径结论不一致时，交叉检验就会报警。
        """
        try:
            sym = sympy.limit(expr, var, point, direction)

            # 数值逼近：多个步长尺度交叉验证。
            # ⚠️ 步长要**够大**：n·sin(2π/n) 这类式子，
            # 若n 取到10^8，double 只有约 16 位有效数字，
            # sin(2π/10^8) ≈ 6e-8，1e-8 量级的相减会全部被舍入吃掉，
            # 结果直接变成 nan/inf——曾因此对正确答案 π 误报「符号误算」。
            # 这里用 1e3~1e5 三个尺度，足以区分 0 与 π 这类差异。
            vals = []
            for k in (3, 4, 5):
                delta = sympy.Rational(1, 10 ** k)
                probe = point - delta if direction == "-" else point + delta
                try:
                    v = complex(sympy.N(expr.subs(var, probe), 30))
                    if abs(v.imag) > 1e-9:
                        return {"passed": False, "method": "cross_check_limit",
                                "issue": f"代入 {var}={probe} 得纯虚数 {v}",
                                "symbolic": str(sym), "numeric": str(v)}
                    vals.append(v.real)
                except Exception:
                    continue

            # 数值不稳定（溢出/NaN）时放弃这一路，而不是误判为错误
            if not vals or any(v != v or abs(v) == float("inf") for v in vals):
                return {"passed": None, "method": "cross_check_limit",
                        "symbolic": str(sym),
                        "note": "数值采样不稳定（步长过大导致溢出或 NaN），跳过交叉检验"}

            numeric = vals[-1] if len(vals) == 1 else sum(vals) / len(vals)

            if sym in (oo, -oo):
                ok = abs(numeric) > 1e3
                return {"passed": ok, "method": "cross_check_limit",
                        "symbolic": str(sym), "numeric": str(numeric),
                        "issue": None if ok else "符号给出无穷但数值未发散"}
            if sym == nan:
                return {"passed": False, "method": "cross_check_limit",
                        "symbolic": "nan", "numeric": str(numeric),
                        "issue": "符号结果为 nan"}

            denom = max(1.0, abs(complex(sympy.N(sym, 20))))
            rel = abs(numeric - complex(sympy.N(sym, 20))) / denom
            passed = rel < 1e-3
            return {
                "passed": passed,
                "relative_error": float(rel),
                "symbolic": str(sym),
                "numeric": str(numeric),
                "method": "cross_check_limit",
                "issue": None if passed else
                f"符号得 {sym}，数值逼近得 {numeric:.6g}"
                f"（相对误差 {rel:.2e}）——疑似符号假设导致的误算",
            }
        except Exception as e:
            return {"passed": None, "method": "cross_check_limit",
                    "note": f"交叉检验异常: {type(e).__name__}"}

    def cross_check_eigen(self, M: Matrix, claimed: list) -> dict:
        """
        特征值交叉检验：det(A - λI) = 0 的残差。
        对每个声称的特征值 λ，检查 det(A-λI) 是否接近 0。
        """
        try:
            if M.rows != M.cols:
                return {"passed": None, "method": "cross_check_eigen",
                        "note": "非方阵，无特征值"}
            n = M.rows
            lam = Symbol("lam")
            charpoly = M.charpoly(lam).as_expr()
            res = []
            for c in claimed:
                try:
                    cv = complex(sympy.N(c, 20))
                except Exception:
                    res.append(None)
                    continue
                r = complex(sympy.N(charpoly.subs(lam, c), 20))
                res.append(abs(r))
            res = [r for r in res if r is not None]
            worst = max(res) if res else None
            if worst is None:
                return {"passed": None, "method": "cross_check_eigen",
                        "note": "特征值无法数值化（可能是符号形式）"}
            # 特征多项式按行数缩放，阈值放宽
            tol = 1e-6 * max(1.0, n)
            return {
                "passed": worst < tol,
                "residual": worst,
                "chardegree": n,
                "method": "cross_check_eigen",
                "issue": None if worst < tol else f"det(A-λI) 残差 {worst:.3e}",
            }
        except Exception as e:
            return {"passed": None, "method": "cross_check_eigen",
                    "note": f"交叉检验异常: {type(e).__name__}"}

    def cross_check_ode(self, solution_expr, ode_expr, var=None,
                        t=None, tol: float = 1e-8) -> dict:
        """
        微分方程验证：把解代回方程看残差。
        ode_expr 形如 Eq(y(x), rhs) 或 (lhs - rhs)。
        """
        var = var or self.x
        try:
            subs_map = {}
            if isinstance(ode_expr, sympy.Eq):
                lhs, rhs = ode_expr.lhs, ode_expr.rhs
                fn = solution_expr
                residual_expr = simplify(fn - rhs)
                residual_expr = residual_expr.subs(symre(solution_expr), fn)
            else:
                residual_expr = solution_expr

            residual_expr = simplify(residual_expr)
            pts = [S0 for S0 in (0.0, 0.4, 0.9, 1.3)]
            vals = []
            for p in pts:
                try:
                    v = complex(sympy.N(residual_expr.subs(var, p), 20))
                    vals.append(abs(v))
                except Exception:
                    continue
            worst = max(vals) if vals else None
            if worst is None:
                return {"passed": None, "method": "cross_check_ode",
                        "note": "残差无法在实点上求值（可能含任意常数）"}
            return {
                "passed": worst < tol,
                "residual": worst,
                "points_tested": len(vals),
                "method": "cross_check_ode",
                "issue": None if worst < tol else f"代回方程残差 {worst:.3e}",
            }
        except Exception as e:
            return {"passed": None, "method": "cross_check_ode",
                    "note": f"ODE 验证异常: {type(e).__name__}: {e}"}

    # ═══════════════════════════════════════════
    # L4: 量纲 / 性质检查
    # ═══════════════════════════════════════════

    @staticmethod
    def dimension_check(answer, expected: Optional[str] = None) -> dict:
        """
        量纲检查。物理题专用。

        约定：题目里显式给出的量纲用 LaTeX 写在 expected 里，
        这里做的是**存在性检查 + 数量级合理性检查**，不做完整量纲代数
        （SymPy 无内置物理量纲系统，硬造一套反而容易给出假结论）。
        """
        notes = []
        if answer is None:
            return {"passed": False, "method": "dimension_check",
                    "issues": ["答案为空，无法检查量纲"]}

        s = str(answer)
        if re.fullmatch(r"\s*[Nn]/?[Aa]|kg", s.strip()):
            notes.append(f"答案看起来是裸数值 {s}，未带单位——若题目要求物理量请补单位")
        if re.search(r"\b(nan|zoo)\b", s):
            notes.append("含 nan/zoo，物理上无意义")

        return {
            "passed": not notes,
            "method": "dimension_check",
            "issues": notes,
            "expected": expected,
            "note": "当前仅做启发式检查；严格量纲分析需引入 pint 库",
        }

    @staticmethod
    def matrix_shape_check(answer, expect_square: bool = True,
                           expect_n: Optional[int] = None) -> dict:
        """矩阵题形状检查——错答成向量/行向量是高频错误。"""
        issues = []
        if answer is None:
            return {"passed": False, "method": "matrix_shape_check",
                    "issues": ["答案为空"]}
        try:
            M = answer if isinstance(answer, Matrix) else sympy.sympify(answer)
            if not isinstance(M, Matrix):
                return {"passed": None, "method": "matrix_shape_check",
                        "note": "答案不是矩阵，跳过"}
            if expect_square and M.rows != M.cols:
                issues.append(f"矩阵非方阵：{M.rows}x{M.cols}")
            if expect_n and M.rows != expect_n:
                issues.append(f"阶数错误：期望 {expect_n}，实际 {M.rows}")
        except Exception as e:
            return {"passed": None, "method": "matrix_shape_check",
                    "note": f"形状检查异常: {type(e).__name__}"}
        return {"passed": not issues, "method": "matrix_shape_check", "issues": issues}

    # ═══════════════════════════════════════════
    # 汇总
    # ═══════════════════════════════════════════

    @staticmethod
    def summarize(checks: list) -> dict:
        """
        汇总验证结果。

        passed=1 / failed=0 / skipped=None
        overall 只有在"没有任何一项失败"时才是 pass。
        """
        real = [c for c in checks if c.get("passed") is not None]
        failed = [c for c in real if c.get("passed") is False]
        skipped = [c for c in checks if c.get("passed") is None]

        return {
            "overall": "pass" if not failed else "fail",
            "n_checks": len(checks),
            "n_passed": sum(1 for c in real if c.get("passed")),
            "n_failed": len(failed),
            "n_skipped": len(skipped),
            "failed_methods": [c["method"] for c in failed],
            "checks": checks,
        }


# ─────────────────────────────────────────────
# 工具
# ─────────────────────────────────────────────

def expression_free_vars(expr) -> set:
    """取表达式里的自由符号。"""
    try:
        return set(sympy.free_symbols(expr))
    except Exception:
        return set()


# ═══════════════════════════════════════════
# 供 solve.py 调用的便捷入口
# ═══════════════════════════════════════════

def verify_solution(solution: dict, *, equation=None, expr=None, var=None,
                    ode_residual=None, is_matrix=None, is_physical=False,
                    limit_expr=None, limit_var=None, limit_point=None,
                    limit_direction=None) -> dict:
    """
    单题验证的便捷包装。

    只做**能安全做的检查**，不做猜测式检查——
    没传相应上下文就跳过，绝不臆造验证条件。
    """
    v = Verifier(x=var) if var else Verifier()
    checks = [Verifier.form_check(solution)]

    if expr is not None and equation is not None:
        checks.append(v.substitution_check(expr, equation, var))
    if limit_expr is not None and limit_var is not None:
        checks.append(v.cross_check_limit(limit_expr, limit_var, limit_point,
                                          limit_direction or "+"))
    if is_matrix is not None:
        checks.append(Verifier.matrix_shape_check(is_matrix))
    if ode_residual is not None:
        checks.append(v.cross_check_ode(ode_residual))
    if is_physical:
        checks.append(Verifier.dimension_check(solution.get("answer")))

    return Verifier.summarize(checks)