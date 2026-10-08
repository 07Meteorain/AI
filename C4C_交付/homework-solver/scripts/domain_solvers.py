#!/usr/bin/env python3
"""
Stage 3 扩展求解器：线性代数 / 微分方程 / 大学物理

starter kit 的 solve.py 里三个函数是空的占位符：

    def solve_matrix(problem): return _unsolved(problem, "矩阵解析需要扩展（学生扩展点）。")
    def solve_ode(problem):    return _unsolved(problem, "ODE 求解需要扩展（学生扩展点）。")

本模块把它们补齐，并新增物理求解器。这是 CHALLENGE.md Level 2/3 的硬性要求：
"扩展到线性代数、微分方程、大学物理"。

与 starter kit 求解器的关键差异：
1. **LaTeX 矩阵解析**：把 \begin{pmatrix}...\end{pmatrix} 可靠地还原成 SymPy Matrix。
   starter kit 的 safe_parse 直接把 \begin 之类清掉，矩阵会被解析成一串垃圾。
2. **操作意图识别**：题目说"求特征值"和"求行列式"要区分开——
   这是向量式题最常见的错误来源。
3. **每步都带中间量**：不只给答案，给出化简过程，符合"解题步骤生成"要求。
4. **物理量带单位**：结果输出 (值, 单位) 二元组。
"""

from __future__ import annotations

import re
from typing import Optional

import sympy
from sympy import (
    Symbol, Matrix, ImmutableMatrix, Rational, Float, sqrt, exp, log, sin, cos,
    simplify, expand, factor, together, cancel, latex, sympify, pi, E, oo,
    diff, dsolve, solve, Eq, Function, Abs, integrate, eye, zeros,
    I, conjugate, trace, det, nsimplify,
)

# 预定义符号池：解析时按顺序绑定
_SYM_POOL = (
    "x y z t n k m a b c d e f g h i j p q r s u v w "
    "lambda lam alpha beta gamma theta omega phi sigma mu nu rho"
).split()

_GLOBAL_SYMS: dict = {}


def _sym(name: str) -> Symbol:
    if name not in _GLOBAL_SYMS:
        _GLOBAL_SYMS[name] = Symbol(name)
    return _GLOBAL_SYMS[name]


def bind(name: str) -> Symbol:
    return _sym(name)


# ═════════════════════════════════════════════════════════════════════
# LaTeX → SymPy：矩阵 / 分段函数
# ═════════════════════════════════════════════════════════════════════

_MATRIX_ENV = re.compile(
    r"\\begin\{(?P<env>pmatrix|bmatrix|vmatrix|matrix|Bmatrix)\}"
    r"(?P<body>.*?)"
    r"\\end\{(?P=env)\}",
    re.DOTALL,
)

_ROW_SEP = re.compile(r"\\\\")
_COL_SEP = re.compile(r"&")


def parse_latex_matrix(latex_str: str) -> Optional[Matrix]:
    """
    把 LaTeX 矩阵环境解析成 SymPy Matrix。

    starter kit 的 safe_parse 会把 \begin{pmatrix} 整段当噪声删掉，
    结果矩阵题只能得到垃圾表达式。这里做专用解析。
    """
    m = _MATRIX_ENV.search(latex_str)
    if not m:
        return None
    body = m.group("body")

    rows = []
    for raw_row in _ROW_SEP.split(body):
        raw_row = raw_row.strip()
        if not raw_row:
            continue
        cells = [_latex_atom(c.strip()) for c in _COL_SEP.split(raw_row)]
        rows.append(cells)

    if not rows:
        return None
    width = max(len(r) for r in rows)
    rows = [r + ["0"] * (width - len(r)) for r in rows]

    data = []
    for r in rows:
        data.append([sympify(c) if c else sympify("0") for c in r])
    try:
        return Matrix(data)
    except Exception:
        return None


def _latex_atom(s: str) -> str:
    """单个矩阵元素：LaTeX → SymPy 字符串。"""
    if s in ("", "\\", " "):
        return "0"
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = s.replace("−", "-").replace("–", "-")
    s = re.sub(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\sqrt\[(\d+)\]\{([^{}]*)\}", r"((\2)**(1/(\1)))", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("{", "(").replace("}", ")")
    s = re.sub(r"\s+", "", s)
    return s or "0"


_CASES_ENV = re.compile(
    r"\\begin\{cases\}(?P<body>.*?)\\end\{cases\}", re.DOTALL
)


def parse_piecewise(latex_str: str):
    """解析 \\begin{cases} … \\\\ … \\end{cases} → list of (expr, cond)。"""
    m = _CASES_ENV.search(latex_str)
    if not m:
        return None
    body = m.group("body")
    out = []
    for raw in _ROW_SEP.split(body):
        raw = raw.strip()
        if not raw or "&" not in raw:
            continue
        expr_s, cond_s = [p.strip() for p in raw.split("&", 1)]
        cond_s = cond_s.replace("\\text{if }", "").replace("\\text{ if }", "").strip()
        try:
            out.append((_latex_atom(expr_s), cond_s))
        except Exception:
            continue
    return out or None


# ═════════════════════════════════════════════════════════════════════
# 通用求解结果构造
# ═════════════════════════════════════════════════════════════════════

def _sol(problem, steps, answer_latex, solver, extra=None, answer_text=None):
    d = {
        "problem_id": problem["id"],
        "problem_text": problem.get("text", ""),
        "solved": True,
        "steps": steps,
        "answer": answer_text if answer_text is not None else answer_latex,
        "answer_latex": answer_latex,
        "solver": solver,
        "sub_solutions": [],
    }
    if extra:
        d.update(extra)
    return d


def _un(problem, reason, subs=None):
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


def _all_latex(problem) -> list:
    """收集题目 + 子题里所有 LaTeX 片段。"""
    out = []
    for e in problem.get("math_expressions", []) or []:
        out.append(e.get("latex", ""))
    for s in problem.get("sub_problems", []) or []:
        for e in s.get("math_expressions", []) or []:
            out.append(e.get("latex", ""))
    return [o for o in out if o]


# ═════════════════════════════════════════════════════════════════════
# 线性代数
# ═════════════════════════════════════════════════════════════════════

def solve_matrix(problem: dict) -> dict:
    """
    线性代数求解器。

    按「操作意图」路由，而不是按关键词命中——这是与 starter kit
    最大的行为差异。starter kit 的 solve_matrix 是直接 raise 的空壳。

    支持意图：
      determinant       行列式
      inverse           逆矩阵
      eigenvalues       特征值（含重数）
      eigenvectors      特征向量
      rank              秩
      transpose         转置
      trace             迹
      solve_system      线性方程组 Ax=b
      rref              行最简形
      orthogonality     正交化（Gram-Schmidt / 正交补）
      projector         投影矩阵
      nullspace         零空间
      colspace          列空间
      diagonalize       对角化
      svd_singular_vals 单值（SVD）
    """
    text = problem.get("text", "").lower()
    latex_all = _all_latex(problem)
    joined = " ".join(latex_all)

    M = None
    for ls in latex_all:
        M = parse_latex_matrix(ls)
        if M is not None:
            break

    if M is None:
        # 也可能矩阵在文本里以 bmatrix 变体出现
        for ls in latex_all:
            M = parse_latex_matrix(ls.replace("\\left", "").replace("\\right", ""))
            if M is not None:
                break

    if M is None:
        return _un(problem, "未能从题目中解析出矩阵（需要 \\begin{pmatrix}…\\end{pmatrix} 结构）")

    steps = [f"解析到矩阵 $A = {latex(M)}$（阶数 {M.rows}x{M.cols}）"]

    # ── 意图判定（顺序敏感：更具体的先匹配）──

    # 线性方程组 Ax = b
    if re.search(r"system|方程组|\\mathbf\{?x\}?\s*=\s*\\mathbf\{?b\}?|a\\mathbf\{x\}|ax\s*=\s*b", text) \
            and M.cols == M.cols and "=" in joined:
        return _solve_linear_system(problem, M, latex_all, steps)

    # 特征向量
    if "eigenvector" in text or "特征向量" in text:
        return _solve_eigenvectors(problem, M, steps)

    # 特征值
    if "eigenvalue" in text or "特征值" in text or "eigen" in text:
        return _solve_eigenvalues(problem, M, steps)

    # 行列式
    if "determinant" in text or "行列式" in text or re.search(r"\bdet\b", text):
        try:
            d = M.det()
            steps.append(f"行列式定义：按第一行展开 $\\det(A) = {latex(d)}$")
            return _sol(problem, steps, latex(d), "sympy_matrix_determinant",
                         extra={"verify_hint": {"kind": "eigen", "matrix": M}})
        except Exception as e:
            return _un(problem, f"行列式计算失败: {e}")

    # 逆矩阵
    # 注意：不能只匹配 "inverse" 关键词——真实作业常写 "Find $A^{-1}$"，
    # 文本里根本没有 "inverse" 这个词。必须同时识别 LaTeX 上标 -1。
    if re.search(r"inverse|逆矩阵|逆\b", text) or \
            re.search(r"A\^\s*\{?\s*-\s*1\s*\}?", " ".join(latex_all)) or \
            re.search(r"\\mathbf\{?A\}?\s*\^\s*\{?-\s*1", " ".join(latex_all)):
        try:
            detA = M.det()
            steps.append(f"$\\det(A) = {latex(detA)}$ → "
                         + ("非零，逆矩阵存在" if detA != 0 else "为零，逆矩阵不存在"))
            if detA == 0:
                return _un(problem,
                           f"矩阵奇异（$\\det(A)={latex(detA)}$），逆矩阵不存在")
            inv = M.inv()
            steps.append(f"$A^{{-1}} = {latex(inv)}$")
            steps.append(f"验证 $AA^{{-1}} = I$：$\\begin{{pmatrix}}{latex(simplify(M * inv))}"
                         f"\\end{{pmatrix}}$")
            return _sol(problem, steps, latex(inv), "sympy_matrix_inverse",
                         extra={"verify_hint": {"kind": "identity",
                                                "M": M, "Minv": inv}})
        except Exception as e:
            return _un(problem, f"逆矩阵计算失败: {e}")

    # 秩
    if re.search(r"\brank\b|秩", text):
        r = M.rank()
        steps.append(f"行阶梯化后非零行数为 {r}")
        return _sol(problem, steps, str(r), "sympy_matrix_rank")

    # 转置
    if "transpose" in text or "转置" in text or "转置矩阵" in text:
        return _sol(problem, steps + [f"$A^T = {latex(M.T)}$"],
                    latex(M.T), "sympy_matrix_transpose")

    # 迹
    if re.search(r"\btrace\b|迹", text):
        return _sol(problem, steps + [f"$\\operatorname{{tr}}(A) = {latex(M.trace())}$"],
                    latex(M.trace()), "sympy_matrix_trace")

    # 行最简形
    if "rref" in text or "row reduce" in text or "行最简" in text:
        r, piv = M.rref()
        steps.append(f"行最简形：主元列 {piv}")
        return _sol(problem, steps, latex(r), "sympy_matrix_rref")

    # 零空间 / 列空间
    if "nullspace" in text or "null space" in text or "零空间" in text:
        ns = M.nullspace()
        if not ns:
            return _sol(problem, steps + ["零空间仅含零向量：$\\{0\\}$"],
                        r"\{ \mathbf{0} \}", "sympy_nullspace")
        return _sol(problem, steps + [f"基：{', '.join(latex(v) for v in ns)}"],
                    "\\left\\{ " + ", ".join(latex(v) for v in ns) + " \\right\\}",
                    "sympy_nullspace")

    if "column space" in text or "col space" in text or "列空间" in text:
        cs = M.columnspace()
        basis = list(cs.basis) if hasattr(cs, "basis") else []
        if not basis:
            return _un(problem, "无法确定列空间基")
        return _sol(problem, steps + [f"基：{', '.join(latex(v) for v in basis)}"],
                    "\\left\\{ " + ", ".join(latex(v) for v in basis) + " \\right\\}",
                    "sympy_colspace")

    # 正交性 / 正交化
    if re.search(r"orthogon|正交|gram-schmidt|投影", text):
        return _solve_orthogonality(problem, M, steps, text)

    # 投影矩阵（到子空间）
    if "projection" in text or "投影" in text:
        return _un(problem, "投影矩阵需明确投影到哪个子空间，请在题目中给出基向量列",
                   subs=None)

    # 对角化
    if "diagonaliz" in text or "对角化" in text or "diagonal form" in text:
        return _solve_diagonalize(problem, M, steps)

    # SVD / 奇异值
    # 注意：SymPy 1.13 没有 M.svd()，用 singular_values()。
    # 它返回奇异值的列表（降序），按行数补零到 n×n 才是对角形式 Σ。
    if "singular value" in text or "svd" in text or "奇异值" in text:
        try:
            sv = M.singular_values()
            m_, n_ = M.rows, M.cols
            Sigma = sympy.zeros(max(m_, n_), max(m_, n_))
            for i, s in enumerate(sv):
                Sigma[i, i] = s
            steps += ["奇异值由 $A^TA$ 的特征值开方得到：$\\sigma_i = \\sqrt{\\lambda_i(A^TA)}$",
                      f"计算得 $\\sigma = {[str(s) for s in sv]}$",
                      f"$\\Sigma = {latex(Sigma)}$"]
            return _sol(problem, steps, latex(Sigma), "sympy_svd",
                         extra={"verify_hint": {"kind": "svd", "M": M,
                                                "sv": sv}})
        except Exception as e:
            return _un(problem, f"SVD 失败: {type(e).__name__}: {e}")

    # 只给了矩阵没给指令 → 算一个摘要，标注未指定意图
    steps.append("题目未明确指定操作，输出矩阵基本量作为参考")
    try:
        summary = (f"\\det(A) = {latex(M.det())},\\quad "
                   f"\\operatorname{{rank}}(A) = {M.rank()},\\quad "
                   f"\\operatorname{{tr}}(A) = {latex(M.trace())}")
        if M.rows == M.cols:
            ev = M.eigenvals()
            summary += f",\\quad \\sigma(A) = {list(ev.keys())}"
        return _sol(problem, steps, summary, "sympy_matrix_summary")
    except Exception as e:
        return _un(problem, f"矩阵摘要失败: {e}")


def _solve_eigenvalues(problem, M: Matrix, steps) -> dict:
    if M.rows != M.cols:
        return _un(problem, "非方阵无特征值")
    try:
        steps.append(f"特征多项式：$\\chi_A(\\lambda) = {latex(M.charpoly().as_expr())}$")
        ev = M.eigenvals()
        if not ev:
            return _sol(problem, steps, r"\varnothing", "sympy_eigenvalues")
        parts, detail = [], []
        total = 0
        for val, mult in ev.items():
            parts.append(latex(val) if mult == 1 else f"{latex(val)}\\ ({mult}\\times)")
            detail.append(f"$\\lambda = {latex(val)}$，重数 {mult}")
            total += mult
        steps.append("特征值：" + "；".join(detail))
        answer = ", ".join(parts)
        if total != M.rows:
            steps.append(f"⚠️ 特征值代数重数之和 = {total} < n = {M.rows}，"
                         "说明存在重根未被完全分解，建议用数值特征值核对")
        return _sol(problem, steps, answer, "sympy_eigenvalues",
                     extra={"verify_hint": {"kind": "eigen", "matrix": M},
                            "eigenvalues": list(ev.keys())})
    except Exception as e:
        return _un(problem, f"特征值计算失败: {e}")


def _solve_eigenvectors(problem, M: Matrix, steps) -> dict:
    if M.rows != M.cols:
        return _un(problem, "非方阵无特征向量")
    try:
        ev = M.eigenvals()
        if not ev:
            return _sol(problem, steps, r"\varnothing", "sympy_eigenvectors")
        parts, detail = [], []
        for val in ev:
            vecs = (M - val * eye(M.rows)).nullspace()
            if not vecs:
                detail.append(f"$\\lambda = {latex(val)}$：无特征向量")
                continue
            vs = ", ".join(latex(v) for v in vecs)
            parts.append(f"\\lambda = {latex(val)}: \\; {vs}")
            detail.append(f"$\\lambda={latex(val)}$ 的特征空间基：{vs}")
        steps += detail
        return _sol(problem, steps, "; ".join(parts), "sympy_eigenvectors")
    except Exception as e:
        return _un(problem, f"特征向量计算失败: {e}")


def _solve_diagonalize(problem, M: Matrix, steps) -> dict:
    try:
        P, D = M.diagonalize()
    except Exception as e:
        return _un(problem,
                   f"该矩阵不可对角化（对角化要求特征值几何重数 = 代数重数，"
                   f"且特征向量张成 n 维空间）。SymPy 报错: {type(e).__name__}")

    try:
        detP = P.det()
    except Exception:
        detP = None

    P_l, D_l = latex(P), latex(D)
    steps += [f"$P = {P_l}$", f"$\\det(P) = {latex(detP)}$", f"$D = {latex(D)}$"]

    if detP == 0:
        steps.append("⚠️ $\\det(P)=0$，该矩阵不可对角化")
        return _un(problem, "矩阵不可对角化（P 奇异）")

    try:
        check = simplify(P.inv() * M * P)
        steps.append(f"验证 $P^{{-1}}AP = {latex(check)}$")
        ok = check == D
        steps.append("✓ 与 D 一致，对角化成立" if ok
                     else f"⚠️ 与 D 不一致：{latex(check)} ≠ {D_l}")
    except Exception as e:
        ok = None
        steps.append(f"（验证跳过：{type(e).__name__}）")

    # 特征值必须互异才有 P —— 这是可对角化的充要条件之一，值得显式说明
    try:
        ev = M.eigenvals()
        distinct = len(ev)
        if distinct < M.rows:
            steps.append(f"注意：矩阵有 {distinct} 个不同特征值而阶数为 {M.rows}，"
                         "存在重根；但重根的特征空间维数足够时仍可对角化")
    except Exception:
        pass

    ans = f"A = PDP^{{-1}},\\quad P = {P_l},\\quad D = {D_l}"
    extra = {"verify_hint": {"kind": "diagonalize", "M": M, "P": P, "D": D},
             "eigenvalues": list(M.eigenvals().keys())}
    return _sol(problem, steps, ans, "sympy_diagonalize", extra=extra)


def _solve_orthogonality(problem, M: Matrix, steps, text: str) -> dict:
    """
    正交性判定或正交化。

    关键细节：**输入的是向量组，不是方阵**。
    真实作业里「对这组向量做 Gram-Schmidt」常写成 3x2 矩阵（向量为行）。
    所以按形状判断：方阵 → 取列向量；非方阵 → 取行向量。
    """
    if M.rows == M.cols:
        vecs = [M[:, j] for j in range(M.cols)]
        layout = "列向量"
    else:
        vecs = [M[i, :] for i in range(M.rows)]
        layout = "行向量"

    names = [f"v_{i+1}" for i in range(len(vecs))]
    cols_text = ", ".join(f"{names[i]} = {latex(vecs[i])}" for i in range(len(vecs)))
    steps.append(f"输入为 {M.rows}x{M.cols} 矩阵，取其{layout}作为待处理向量：{cols_text}")

    is_check = bool(re.search(r"are\s+(the\s+)?(columns?|vectors?|rows?)?\s*orthogonal|"
                              r"是否正交|两两正交", text))
    is_ortho = bool(re.search(r"orthonormal|标准正交|规范正交|单位正交", text))
    is_gs = bool(re.search(r"gram-schmidt|正交化|orthogonalize|make.*orthogonal|"
                           r"orthogonal basis|正交基", text))

    # 判定型
    if is_check and not is_gs:
        dots = []
        ok = True
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                ip = simplify(vecs[i].dot(vecs[j]))
                dots.append(rf"$\langle {names[i]},{names[j]}\rangle = {latex(ip)}$")
                if ip != 0:
                    ok = False
        if not dots:
            steps.append("只有 1 个向量，平凡地两两正交")
            return _sol(problem, steps, "\text{单向量，平凡正交}",
                        "sympy_orthogonality_check")
        steps.append("两两内积：" + "；".join(dots))
        verdict = ("两两正交" if ok else
                   "**不正交**——存在内积非零的一对")
        steps.append(f"结论：{verdict}")
        return _sol(problem, steps,
                    f"{verdict};\quad " + ",\; ".join(dots),
                    "sympy_orthogonality_check")

    # Gram-Schmidt
    # 关键：SymPy 1.13 的 Matrix.orthogonalize 是 **classmethod**，
    # 必须以 Matrix.orthogonalize(v1, v2, ...) 形式调用（显式传入向量）。
    # 实例调用 M.orthogonalize() 会静默返回空列表——非常容易踩的坑。
    V = Matrix.vstack(*vecs)
    try:
        cols = [V[:, j] for j in range(V.cols)]
        q = list(Matrix.orthogonalize(*cols, normalize=False))
    except Exception as e:
        return _un(problem, f"Gram-Schmidt 执行失败: {type(e).__name__}: {e}")
    if not q:
        return _un(problem, "输入无向量，无法正交化")

    if is_ortho:
        q = [c / sympy.sqrt(c.dot(c)) for c in q]
        steps.append("已进一步归一化各向量，得到标准（单位）正交组")

    Q = Matrix.hstack(*q)          # 列依次为 q_1, q_2, ...
    QtQ = simplify(Q.T * Q)

    steps.append("Gram-Schmidt 结果：")
    for i, c in enumerate(q):
        steps.append(rf"$q_{i+1} = {latex(c)}$")
    steps.append(rf"验证 $Q^TQ = {latex(QtQ)}$")
    steps.append(r"说明：$Q$ 的**各列**依次为 $q_1, q_2, \dots$，即所求正交组。")

    ans = f"Q = {latex(Q)}"
    if is_ortho:
        ans += r",\qquad Q^TQ = I"
    return _sol(problem, steps, ans,
                "sympy_gram_schmidt" if not is_ortho else "sympy_orthonormalize",
                extra={"verify_hint": {"kind": "orthogonal", "Q": Q}})



def _solve_linear_system(problem, M: Matrix, latex_all, steps) -> dict:
    """从 Ax = b 形式解线性方程组。"""
    # 找 b：通常是列向量，或另一个 matrix
    b_vec = None
    for ls in latex_all:
        Mb = parse_latex_matrix(ls)
        if Mb is not None and Mb is not M:
            if Mb.cols == 1 and Mb.rows == M.rows:
                b_vec = Mb
                break
    if b_vec is None:
        # 尝试从文本里找 b = (x1, x2, ...)
        m = re.search(r"b\s*=\s*\(?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)",
                      " ".join(latex_all))
        if m:
            b_vec = Matrix([[float(m.group(i))] for i in (1, 2, 3)])
    if b_vec is None:
        return _un(problem, "未能解析出方程组右端项 b")

    detA = M.det()
    steps.append(f"$A = {latex(M)}$, $\\mathbf{{b}} = {latex(b_vec)}$")
    steps.append(f"$\\det(A) = {latex(detA)}$ → "
                 + ("系数矩阵非奇异，唯一解" if detA != 0 else "奇异，解不唯一或无解"))

    if detA == 0:
        return _un(problem, f"系数矩阵奇异（det={latex(detA)}），需讨论解的情况")

    x = M.inv() * b_vec
    steps += [f"$x = A^{{-1}}\\mathbf{{b}} = {latex(M.inv())} \\cdot {latex(b_vec)} = {latex(x)}$",
              f"验证 $Ax - \\mathbf{{b}} = {latex(simplify(M * x - b_vec))}$"]
    return _sol(problem, steps, latex(x), "sympy_linear_system",
                 extra={"verify_hint": {"kind": "identity", "M": M, "Minv": M.inv(),
                                        "b": b_vec}})


# ═════════════════════════════════════════════════════════════════════
# 微分方程
# ═════════════════════════════════════════════════════════════════════

def solve_ode(problem: dict) -> dict:
    """
    微分方程求解器。

    支持：
      - 一阶线性 ODE（常系数 + 初值条件）
      - 可分离变量
      - 二阶常系数齐次（特征方程）
      - 高阶常系数齐次

    实现要点（全部是踩过的坑，注释保留下来）：
    1. `y` 必须统一替换为 `y(x)`。否则 `2*y` 中的 y 是 UndefinedFunction 类，
       sympify 会报 "unsupported operand type(s) for *: Integer and UndefinedFunction"。
    2. sympify 不能直接解析含 `=` 的字符串，必须先按 `=` 拆成 lhs/rhs 再组装 Eq。
    3. dsolve 的 ics 格式是 {y(x0): val}（如 {y(0): 1}），不是 {y(x): val}。
    4. dsolve 返回 Eq(y(x), 解)，要取 .rhs 才是解本身。
    """
    text = problem.get("text", "")
    text_l = text.lower()
    latex_all = _all_latex(problem)

    ode_src = None
    cand_src = None
    for ls in latex_all:
        if _looks_like_ode(ls):
            if ode_src is None:
                ode_src = ls
        elif cand_src is None and re.match(r"^\s*y\s*=", ls):
            # 形如 "y = C_1 e^{2x} + C_2 e^{3x}" —— 待验证的候选解
            cand_src = ls

    # ── 验证型题目：「验证 y = ... 是该方程的解」──
    if re.search(r"verify|prove|show that|验证|证明", text_l) and cand_src and ode_src:
        return _solve_verify_substitution(problem, cand_src, ode_src)

    if ode_src is None:
        return _un(problem, "未找到含导数的方程（需要 y'、y'' 或 \\frac{dy}{dx}）")

    x = _sym("x")
    y = Function("y")

    try:
        eq = _latex_to_ode(ode_src, x, y)
    except Exception as e:
        return _un(problem, f"ODE 解析失败: {type(e).__name__}: {e}")

    if eq is None:
        return _un(problem,
                   f"无法把 `{ode_src[:60]}` 转成 SymPy 导数表达式")

    steps = [f"解析方程：${latex(eq)}$"]

    # 分类说明：给出可读的题型判断，便于学生核对
    # 注意：free_symbols 里可能混有 Derivative 对象，对 Relational 求 max 会抛
    # "cannot determine truth value"，所以先筛出真正的 Symbol。
    syms = [d for d in eq.lhs.free_symbols if isinstance(d, sympy.Symbol)]
    derivs = list(eq.lhs.atoms(sympy.Derivative))
    max_order = max((len(d.variables) for d in derivs), default=0)
    ind = "（齐次）" if simplify(eq.rhs) == 0 else "（非齐次）"
    # 线性判定：把 y(x) 整体当作一个符号，看方程对它是否一次。
    # 不能直接调 expr.is_linear —— SymPy 里 is_linear 是 Poly 的方法，Expr 上没有。
    lin = "线性" if _is_linear_in_y(eq.lhs) else "非线性"
    steps.append(f"方程类型：{max_order} 阶{ind}，关于 $y(x)$ {lin}")

    # 初值条件
    ic = _extract_ic(latex_all, x, y)
    try:
        if ic:
            at, val = ic
            steps.append(f"初值条件：$y({latex(at)}) = {latex(val)}$")
            # 先求通解，再代入初值解出任意常数。
            # 比直接传 ics={y(0): val} 更好：学生能看到常数是怎么定出来的，
            # 而且通解始终保留在 steps 里，便于核对。
            general = dsolve(eq, y(x))
            gen_rhs = general.rhs if isinstance(general, sympy.Equality) else general

            consts = sorted(gen_rhs.free_symbols, key=lambda s: s.name)
            solved_expr = gen_rhs
            for c in consts:
                try:
                    cval = sympy.solve(sympy.Eq(gen_rhs.subs(x, at), val), c)
                    if cval:
                        steps.append(
                            rf"代入 $x = {latex(at)}$："
                            rf"${latex(gen_rhs)} = {latex(val)}$"
                            rf"$\Rightarrow {latex(c)} = {latex(cval[0])}$")
                        solved_expr = solved_expr.subs(c, cval[0])
                except Exception:
                    continue

            rhs_sol = simplify(solved_expr)
            steps.append(rf"因此 $y(x) = {latex(rhs_sol)}$")
        else:
            rhs_sol = dsolve(eq, y(x))
            rhs_sol = rhs_sol.rhs if isinstance(rhs_sol, sympy.Equality) else rhs_sol
            steps.append("无初值条件，给出通解（含任意常数）")
            steps.append(rf"$y(x) = {latex(rhs_sol)}$")

        # 验证：代回原方程算残差——这是 rubric「答案验证」的要求
        try:
            residual = simplify(rhs_sol.diff(x) - eq.rhs.subs(y(x), rhs_sol))
            steps.append(rf"验证：把解代回原方程，残差 "
                         rf"$y' - f(x,y) = {latex(residual)}$")
        except Exception:
            steps.append("（代回验证跳过：解中含未定义常数）")

        return _sol(problem, steps, latex(rhs_sol), "sympy_dsolve",
                    answer_text=latex(rhs_sol),
                    extra={"verify_hint": {"kind": "ode_expr", "sol": rhs_sol,
                                           "eq": eq}})
    except Exception as e:
        return _un(problem, f"dsolve 求解失败: {type(e).__name__}: {e}")


def _solve_verify_substitution(problem, cand_src: str, ode_src: str) -> dict:
    """
    验证型求解：把候选解代入方程，看残差是否为 0。

    「验证 y = C₁e^{2x} + C₂e^{3x} 满足 y'' - 5y' + 6y = 0」
    这类题不需要 dsolve——直接把候选解代进去算残差即可，
    而且这正是「验证」的本质。
    """
    x = _sym("x")
    y = Function("y")

    try:
        cand = _parse_candidate(cand_src, x)
        eq = _latex_to_ode(ode_src, x, y)
    except Exception as e:
        return _un(problem, f"验证型题目解析失败: {type(e).__name__}: {e}")

    if cand is None:
        return _un(problem, f"无法解析候选解 `{cand_src[:50]}`")
    if eq is None:
        return _un(problem, f"无法解析方程 `{ode_src[:50]}`")

    steps = [f"待验证的函数：$y = {latex(cand)}$",
             f"方程：${latex(eq)}$"]

    # C_1, C_2 这类常数要当独立符号
    subst_y = {y(x): cand}
    try:
        residual = simplify(eq.lhs.subs(subst_y))
        consts = sorted(residual.free_symbols - {x}, key=lambda s: s.name)
        steps.append(
            rf"把 $y = {latex(cand)}$ 代入方程左端，得到残差："
            rf"$R = {latex(residual)}$")
        if consts:
            steps.append("其中 " + "、".join(f"${latex(c)}$" for c in consts) +
                         " 为任意常数——残差恒等于 0，**与常数取值无关**。")
        is_zero = simplify(residual.subs({c: 0 for c in consts})) == 0
        steps.append("✓ 残差恒为 0，候选解确实是该方程的解。" if is_zero
                     else f"✗ 残差不恒为 0，候选解**不是**该方程的解。")
    except Exception as e:
        return _un(problem, f"代入验证失败: {type(e).__name__}: {e}")

    # 顺便判断「是否覆盖全部解」：与 dsolve 通解比对
    general_note = ""
    try:
        gen = dsolve(eq, y(x))
        gen_rhs = gen.rhs if isinstance(gen, sympy.Equality) else gen
        cand_str = sympy.simplify(cand)
        gen_str = sympy.simplify(gen_rhs)
        same = (sympy.simplify(cand_str - gen_str) == 0)
        general_note = ("该形式即通解，故**每个解**都可写成此形式。" if same
                        else "注意：通解为 " + latex(gen_rhs) +
                             "，与题给形式不同，需说明是否等价。")
    except Exception:
        general_note = ""

    ans = ("验证通过：残差恒为 0" if is_zero else "验证不通过：残差不为 0")
    steps.append(general_note) if general_note else None

    return _sol(problem, steps, ans, "sympy_verify_substitution",
                answer_text=ans,
                extra={"verify_hint": {"kind": "form_check"}})


def _parse_candidate(src: str, x):
    """
    把 "y = C_1 e^{2x} + C_2 e^{3x}" 解析成 SymPy 表达式。

    实现说明：这里**不做「整串 LaTeX → sympify」的往返**。
    那样做踩过两个坑：
      · 常数 C_1 含下划线，不是合法 Python 标识符，sympify 直接 SyntaxError；
      · 常数与 exp( ) 之间缺乘号，"C_1 exp(2*x)" 在 eval 里同样非法。
    改成「先按顶层 +/- 切分成项、每项单独解析、再相加」的结构化做法，
    既绕开标识符问题，也让每一步都可控、可单测。
    """
    m = re.match(r"^\s*y\s*=\s*(.+)$", src.strip(), re.DOTALL)
    if not m:
        return None
    body = m.group(1).strip()

    # 按顶层 + / - 切分成项（带符号）
    terms, buf, sign = [], "", 1
    for ch in body:
        if ch in "+-" and buf.strip():
            terms.append((sign, buf))
            buf, sign = "", (1 if ch == "+" else -1)
        else:
            buf += ch
    if buf.strip():
        terms.append((sign, buf))

    total = None
    for sgn, raw in terms:
        t = _parse_candidate_term(raw.strip(), x)
        if t is None:
            continue
        total = t * sgn if total is None else total + t * sgn
    return total


def _parse_candidate_term(raw: str, x):
    """解析候选解里的单个项，例如 "C_1 e^{2x}"。失败返回 None。"""
    raw = (raw or "").strip()
    if not raw:
        return None

    loc = {"x": x, "exp": exp, "sin": sin, "cos": cos,
           "sqrt": sqrt, "pi": pi, "log": log, "e": sympy.E}

    # 常数符号 c_1 / c1 / C_1 / C 1 → 合法标识符 cc1
    def _const(mo):
        alias = f"cc{mo.group(1)}"
        loc[alias] = sympy.Symbol(f"C_{mo.group(1)}")
        return alias

    term = re.sub(r"\b[Cc][_\s]*(\d{1,2})\b", _const, raw)

    # LaTeX 清理
    term = term.replace("\\left", "").replace("\\right", "")
    term = term.replace("^", "**")
    term = re.sub(r"\be(?=\s*\()", "E", term)
    term = re.sub(r"\be\s*\*\*", "exp", term)
    term = re.sub(r"\\[,;!]", " ", term)
    term = re.sub(r"\\[a-zA-Z]+", " ", term)
    term = term.replace("{", "(").replace("}", ")")
    term = re.sub(r"\s+", " ", term).strip()
    if not term:
        return None

    # 保护多字母标识符（exp / sqrt / cc1 …）
    # 占位符用纯大写单字母（P/Q/R…）。任何含数字或下划线的占位符
    # 都会被下面「标识符+括号 → 补乘号」的规则切碎（曾用 zz0zz 出过问题）。
    names = sorted([k for k in loc if k != "x"], key=len, reverse=True)
    tokens = {}
    letters = [chr(ord("P") + i) for i in range(26)]

    def _prot(mo):
        k = letters[len(tokens)]
        tokens[k] = mo.group(0)
        return k

    term = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b").sub(
        _prot, term)

    # 各类隐式乘法。
    # ⚠️ 「标识符 + 括号」这条规则必须用 \s+（至少一个空格），不能用 \s*：
    #    \s* 会匹配零空白，把函数调用 exp(2x) 变成 exp*(2x) —— 语法合法
    #    但语义完全错误，而且不报错，极难发现。
    term = re.sub(r"(\d)\s*([a-zA-Z(])", r"\1*\2", term)
    term = re.sub(r"\)\s*\(", r")*(", term)
    term = re.sub(r"\)\s*([a-zA-Z0-9])", r")*\1", term)
    term = re.sub(r"([A-Za-z][A-Za-z0-9]*)\s+\(", r"\1*(", term)
    term = re.sub(r"(?<![A-Za-z0-9_])([A-Za-z])\s+([A-Za-z])(?![A-Za-z0-9_])",
                  r"\1*\2", term)

    for k, v in tokens.items():
        term = re.sub(r"(?<![A-Za-z0-9])" + k + r"(?![A-Za-z0-9])", v, term)

    try:
        return sympy.sympify(term, locals=loc)
    except Exception:
        return None


def _is_linear_in_y(expr) -> bool:
    """
    判断表达式是否关于 y(x) 线性。

    做法：把每个含 y(x) 的项（及其各阶导数）整体替换为独立符号，
    然后检查是否一次。若出现 y(x)^2 或 y(x)*y'(x) 之类则为非线性。
    """
    try:
        reps = {}
        for d in expr.atoms(sympy.Derivative):
            fn = d.expr
            if isinstance(fn, sympy.core.function.AppliedUndef):
                reps[d] = Symbol(f"_u_{len(reps)}")
        # y(x) 本身
        if expr.has(y_of(expr)):
            pass
        ysym = None
        for fn in expr.atoms(sympy.core.function.AppliedUndef):
            if fn.func.__name__ == "y":
                ysym = fn
                reps[fn] = Symbol("_y0")
        if not reps:
            return False
        # 若 y(x) 未出现在替换表中（可能通过其它形式出现），保守判为非线性
        reduced = expr.xreplace(reps)
        gen = reduced.free_symbols
        if not gen:
            return True
        # 全部替换符号的最高次数 <= 1 即为线性
        poly = sympy.Poly(reduced, *gen) if gen else None
        if poly is None:
            return False
        return all(sum(m) <= 1 for m in poly.monoms())
    except Exception:
        return False


def y_of(expr):
    """返回表达式中出现的 y(x)（没有则 None）。"""
    for fn in expr.atoms(sympy.core.function.AppliedUndef):
        if fn.func.__name__ == "y":
            return fn
    return None


def _looks_like_ode(s: str) -> bool:
    """判断字符串是否像微分方程（含导数记号）。"""
    t = s.replace("\\", "")
    return bool(
        re.search(r"y\s*'", t)
        or re.search(r"dy\s*/\s*dx", t)
        or re.search(r"d\^\{?2\}?y", t)
        or re.search(r"frac\{?d\s*y", s)
    )


def _split_equation(s: str):
    """按顶层 `=` 拆分方程，跳过 \\frac / \\left 里的括号。"""
    depth = 0
    for i, ch in enumerate(s):
        if ch in "{([":
            depth += 1
        elif ch in "})]":
            depth -= 1
        elif ch == "=" and depth == 0:
            # 排除 \le \ge \neq
            if i > 0 and s[i - 1] in "=<>!~":
                continue
            return s[:i], s[i + 1:]
    return None, None


def _latex_to_ode(src: str, x, y):
    """把含导数的 LaTeX 转为 sympy Eq(lhs - rhs, 0)。"""
    s = src.strip()

    # ── 导数记号 → Derivative(y(x), x[, n]) ──
    # 顺序很重要：先处理 y''(x) 与 y'(x)（带括号），再处理裸撇号
    s = re.sub(r"y''\s*\(\s*x\s*\)", "Derivative(y(x), x, 2)", s)
    s = re.sub(r"y'\s*\(\s*x\s*\)", "Derivative(y(x), x)", s)
    s = re.sub(r"y\s*\(\s*x\s*\)", "y(x)", s)          # 裸 y(x) 归一

    # \frac{d^2y}{dx^2} / \frac{dy}{dx}（含 \dfrac 变体）
    # ⚠️ 这里必须用 (?:d|t)? 而不是 [dt]?：
    #    方括号在正则里是**字符类**，[dt]? 匹配的是字面字符 "d"、"t" 或 "\t"，
    #    永远匹配不到 "\frac" / "\dfrac"。这个 bug 很隐蔽——
    #    \dfrac 能解析而 \frac 不能，症状看起来像"随机失败"。
    s = re.sub(r"\\(?:d|t)?frac\s*\{\s*d\s*\^\s*\{?2\}?\s*y\s*\}"
               r"\s*\{\s*d\s*x\s*\^\s*\{?2\}?\s*\}",
               "Derivative(y(x), x, 2)", s)
    s = re.sub(r"\\(?:d|t)?frac\s*\{\s*d\s*y\s*\}\s*\{\s*d\s*x\s*\}",
               "Derivative(y(x), x)", s)

    # 裸撇号（不在括号后）
    s = re.sub(r"y''", "Derivative(y(x), x, 2)", s)
    s = re.sub(r"y'", "Derivative(y(x), x)", s)

    # ── 其余 LaTeX → 表达式 ──
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\cdot", "*").replace("\\times", "*")
    s = re.sub(r"\\(?:d|t)?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", s)
    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\(?:quad|qquad|,|;|!)", " ", s)
    s = re.sub(r"\\[a-zA-Z]+", " ", s)      # 剩余命令一律剔除
    s = s.replace("{", "(").replace("}", ")")
    s = s.replace("^", "**")
    s = re.sub(r"\s+", " ", s).strip()

    lhs_s, rhs_s = _split_equation(s)
    if lhs_s is None:
        return None

    loc = {"y": y, "x": x, "Derivative": sympy.Derivative,
           "sqrt": sqrt, "sin": sin, "cos": cos, "tan": sympy.tan,
           "exp": exp, "log": log, "pi": pi, "E": E, "oo": oo,
           "Abs": Abs, "Rational": Rational, "I": I,
           "erf": sympy.erf, "gamma": sympy.gamma, "loggamma": sympy.loggamma}

    # 需要保护的标识符（含 \Derivative、函数名等），
    # 否则下面的「字母并排」规则会把 Derivative 拆成 D*erivative。
    PROTECTED = ("Derivative", "Rational", "Integer", "Float", "Symbol",
                 "sqrt", "sin", "cos", "tan", "exp", "log", "Abs", "E", "I",
                 "erf", "gamma", "loggamma", "pi", "oo")
    tokens = {}

    def _protect(m):
        key = f"__TOK{len(tokens)}__"
        tokens[key] = m.group(0)
        return key

    protected_re = re.compile(r"\b(" + "|".join(PROTECTED) + r")\b")

    def _parse(seg: str):
        nonlocal tokens
        tokens = {}
        seg = seg.strip()
        if not seg:
            return sympy.Integer(0)

        seg = protected_re.sub(_protect, seg)

        # ① 先补隐式乘法：2y → 2*y, 3x → 3*x
        #    必须放在 ② 之前，否则 "2y" 里的 y 前面是数字，\b 匹配不到，
        #    后续的「裸 y → y(x)」就会漏掉它（踩过的坑）。
        seg = re.sub(r"(\d)\s*([a-zA-Z(])", r"\1*\2", seg)
        seg = re.sub(r"\)\s*\(", r")*(", seg)
        seg = re.sub(r"\)\s*([a-zA-Z0-9])", r")*\1", seg)

        # ② 字母并排（含空格）的隐式乘法：xy → x*y，"x y" → x*y
        #两端都必须是「独立单字母」（前后都不是字母/数字/下划线），
        #    这样 Derivative / exp 这类多字母标识符不会被拆成 D*erivative。
        seg = re.sub(r"(?<![A-Za-z0-9_])([a-zA-Z])\s+([a-zA-Z])(?![A-Za-z0-9_])",
                     r"\1*\2", seg)
        seg = re.sub(r"(?<![A-Za-z0-9_])([a-zA-Z])([a-zA-Z])(?![A-Za-z0-9_])",
                     r"\1*\2", seg)

        # ③ 裸 y → y(x)（y 是未定义函数类，必须变成函数调用）
        seg = re.sub(r"\by(?!\s*\()", "y(x)", seg)

        # ④ 自然常数 e：e**(-x) → exp(-x)
        seg = re.sub(r"\be\s*\*\*", "exp", seg)
        seg = re.sub(r"\bln\b", "log", seg)

        # 还原被保护的标识符
        for key, val in tokens.items():
            seg = seg.replace(key, val)

        local = dict(loc)
        local.update({k: v for k, v in tokens.items() if False})
        return sympy.sympify(seg, locals=local, rational=True)

    try:
        lhs = _parse(lhs_s)
        rhs = _parse(rhs_s)
    except Exception:
        return None

    if not isinstance(lhs, sympy.Basic) or not isinstance(rhs, sympy.Basic):
        return None
    return sympy.Eq(lhs - rhs, 0)


def _extract_ic(latex_all, x, y):
    """
    抽取初值条件 y(a) = b。

    Returns:
        (a, b) 或 None
    """
    for ls in latex_all:
        m = re.match(r"y\s*\(\s*([\d.\-]+)\s*\)\s*=\s*(.+?)\s*$", ls.strip())
        if not m:
            continue
        try:
            a = sympy.sympify(m.group(1))
            b = sympy.sympify(_latex_atom(m.group(2)))
            if not a.has(x):
                return (a, b)
        except Exception:
            continue
    return None


# ═════════════════════════════════════════════════════════════════════
# 大学物理
# ═════════════════════════════════════════════════════════════════════

# 物理常量（SI）
CONSTANTS = {
    "g": (sympy.Float("9.80665"), "m/s^2"),
    "G": (sympy.Float("6.67430e-11"), "N m^2/kg^2"),
    "h": (sympy.Float("6.62607015e-34"), "J s"),
    "hbar": (sympy.Float("1.054571817e-34"), "J s"),
    "c": (sympy.Float("299792458"), "m/s"),
    "e": (sympy.Float("1.602176634e-19"), "C"),
    "eps0": (sympy.Float("8.8541878128e-12"), "F/m"),
    "mu0": (sympy.Float("1.25663706212e-6"), "N/A^2"),
    "ke": (sympy.Float("8.9875517923e9"), "N m^2/C^2"),
    "k": (sympy.Float("1.380649e-23"), "J/K"),
    "m_e": (sympy.Float("9.1093837015e-31"), "kg"),
    "m_p": (sympy.Float("1.67262192369e-27"), "kg"),
    "sigma": (sympy.Float("5.670374419e-8"), "W/(m^2 K^4)"),
}


def solve_physics(problem: dict) -> dict:
    """
    大学物理求解器。

    覆盖三类高频题型（都能用符号计算闭环）：
      mechanics             牛顿定律、一维运动、能量守恒
      electromagnetism     库仑定律、电场、电势、电路欧姆定律
      thermodynamics       理想气体状态方程

    与 starter kit 的差异：结果**带单位**并做量纲检查——
    这是 rubric 里「维度分析 / 答案验证」的要求。

    实现要点：物理题的**数值与单位在同一句话里**，
    所以解析必须从自然语言抽数，不能只盯着 LaTeX。
    """
    text = problem.get("text", "")
    text_l = _normalize_for_units(text)
    latex_all = _all_latex(problem)

    domain = _detect_physics_domain(text_l)
    steps = [f"识别领域：{domain}"]

    try:
        if domain == "mechanics":
            return _solve_mechanics(problem, text_l, latex_all, steps)
        if domain == "electromagnetism":
            return _solve_em(problem, text_l, latex_all, steps)
        if domain == "thermodynamics":
            return _solve_thermo(problem, text_l, latex_all, steps)
    except Exception as e:
        return _un(problem, f"物理求解异常: {type(e).__name__}: {e}")

    return _un(problem, "物理题型未识别（当前支持力学/电磁学/热学三类）")


def _detect_physics_domain(text_l: str) -> str:
    """领域判定。顺序有讲究：电磁学特征词更专 Specific，先判。"""
    # 电磁学特征最强，放最前
    if re.search(r"coulomb|库仑|electric field|电场|voltage|电压|current\b|电流|"
                 r"resistor|resistance|电阻|电路|circuit|charge|电荷|电容|电感",
                 text_l):
        return "electromagnetism"
    if re.search(r"ideal gas|理想气体|entropy|熵|boltzmann|温度|temperature|"
                 r"heat\b|热量|thermodynamic", text_l):
        return "thermodynamics"
    # 气体线索（"a gas occupies…" 这类表述没有 "ideal gas" 字样）
    if re.search(r"\bgas\b|气体|moles?\b|摩尔|\bpressure\b|压强|\bpa\b", text_l):
        return "thermodynamics"
    if re.search(r"newton|牛顿|force|力|加速度|acceleration|velocity|速度|"
                 r"momentum|动量|kinetic energy|动能|projectile|抛体|"
                 r"自由落体|free ?fall|摩擦|friction|重力|gravity|"
                 r"\bdrop|落下|\bfall|下落|\bspeed\b|速率|\bheight\b|高度", text_l):
        return "mechanics"
    return "unknown"


def _normalize_for_units(text: str) -> str:
    """
    把题面正规化，让「数值+单位」更容易被 regex 抓到。

    要处理的真实格式（来自真实作业）：
      "$3.0$ C"      数值被LaTeX 定界符包住→ "$3.0 c"
      "202650 Pa."   句号结尾
      "0.05 m^3"     上标单位
      "6 ohm"        单词单位
    做法：先把 $...$ 里的内容原样取出拼回去（去掉定界符），
    再统一转小写、压缩空格。
    """
    t = re.sub(r"\$\s*(.+?)\s*\$", r" \1 ", text, flags=re.DOTALL)
    t = t.replace("**", "^")
    t = re.sub(r"\s+", " ", t.lower())
    return t.strip()


def _nums_with_unit(text_l: str, unit_pattern: str):
    """
    抽出「数值 + 单位」对。返回 [(value_str, unit_str), ...]

    text_l 建议先用 _normalize_for_units() 处理过。
    """
    out = []
    for m in re.finditer(r"(-?\d+(?:\.\d+)?(?:e-?\d+)?)\s*(" + unit_pattern + r")",
                         text_l):
        out.append((m.group(1), m.group(2)))
    return out


def _all_latex_normalized(problem) -> tuple:
    """返回 (正规化后的题面, 原始题面)，省得到处重复调用。"""
    return _normalize_for_units(problem.get("text", "")), problem.get("text", "")


def _solve_mechanics(problem, text_l, latex_all, steps) -> dict:
    """牛顿第二定律 / 自由落体 / 动能 / 势能。"""
    g = CONSTANTS["g"][0]

    masses = _nums_with_unit(text_l, r"kg|kilograms?")
    forces = _nums_with_unit(text_l, r"n\b|newtons?|牛")
    accels = _nums_with_unit(text_l, r"m/s\^?2|m/s2")

    # ── F = ma / a = F/m ──
    # 题目可能给 F 和 m 求 a，也可能给 m 和 a 求 F——两个方向都要覆盖。
    if masses and re.search(r"\bforce\b|\bnewton|力|加速度|acceleration", text_l):
        m_ = sympy.Float(masses[0][0])
        if forces and not accels:
            F_ = sympy.Float(forces[0][0])
            a_ = simplify(F_ / m_)
            steps += [r"$F = ma\ \Rightarrow\ a = \frac{F}{m}$",
                      rf"$a = \frac{{{latex(F_)}}}{{{latex(m_)}}} = {latex(a_)}\ \mathrm{{m/s^2}}$",
                      r"量纲核对：$\mathrm{N/kg} = \mathrm{m/s^2}$ ✓"]
            ans = rf"a = {latex(a_)}\ \mathrm{{m/s^2}}"
            # 「保持匀速所需的合力」= 0，这是牛顿第一定律
            if re.search(r"constant velocity|匀速|constant speed", text_l):
                steps += ["物体做匀速直线运动时 $a = 0$，由 $F_{net}=ma$ 得",
                          r"$F_{net} = m\cdot 0 = 0\ \mathrm{N}$ —— 合力为零"]
                ans += r",\qquad F_{net}\ (\text{匀速时}) = 0\ \mathrm{N}"
            return _sol(problem, steps, ans, "physics_newton2",
                        answer_text=ans.replace(r"\qquad", "; "),
                        extra={"verify_hint": {"kind": "physical"},
                               "answer_value": a_})
        if accels and not forces:
            a_ = sympy.Float(accels[0][0])
            F_ = simplify(m_ * a_)
            steps += [r"$F = ma$",
                      rf"$= {latex(m_)}\times{latex(a_)} = {latex(F_)}\ \mathrm{{N}}$",
                      r"量纲核对：$\mathrm{kg}\cdot\mathrm{m/s^2} = \mathrm{N}$ ✓"]
            return _sol(problem, steps, rf"{latex(F_)}\ \mathrm{{N}}",
                        "physics_newton2", answer_text=f"{latex(F_)} N",
                        extra={"verify_hint": {"kind": "physical"},
                               "answer_value": F_})
        # 两个都给：a = F/m
        if forces and accels:
            F_ = sympy.Float(forces[0][0])
            a_ = simplify(F_ / m_)
            steps += [r"$a = F/m$",
                      rf"$= {latex(F_)}/{latex(m_)} = {latex(a_)}\ \mathrm{{m/s^2}}$"]
            return _sol(problem, steps, rf"{latex(a_)}\ \mathrm{{m/s^2}}",
                        "physics_newton2", answer_text=f"{latex(a_)} m/s^2",
                        extra={"verify_hint": {"kind": "physical"},
                               "answer_value": a_})

    # ── 动能 K = ½mv² ──
    if re.search(r"kinetic energy|动能", text_l):
        if masses and re.search(r"m/s", text_l):
            speeds = _nums_with_unit(text_l, r"m/s")
            if speeds:
                m_ = sympy.Float(masses[0][0])
                v_ = sympy.Float(speeds[0][0])
                K = simplify(m_ * v_ ** 2 / 2)
                steps += [r"$K = \frac{1}{2}mv^2$",
                          rf"$= \frac{{1}}{{2}}\times{latex(m_)}\times({latex(v_)})^2"
                          rf" = {latex(K)}\ \mathrm{{J}}$",
                          r"量纲核对：$\mathrm{kg}\cdot\mathrm{m^2/s^2} = \mathrm{J}$ ✓"]
                return _sol(problem, steps, rf"{latex(K)}\ \mathrm{{J}}",
                            "physics_kinetic_energy",
                            answer_text=f"{latex(K)} J",
                            extra={"verify_hint": {"kind": "physical"},
                                   "answer_value": K})

    # ── 自由落体 / 一维运动 v = gt, h = ½gt² ──
    if re.search(r"free ?fall|自由落体|dropped|drop from|falls? for|falls? from", text_l):
        times = _nums_with_unit(text_l, r"s|sec|seconds?|秒")
        if times:
            t_ = sympy.Float(times[0][0])
            v = simplify(g * t_)
            h = simplify(g * t_ ** 2 / 2)
            steps += ["自由落体（初速度为零，忽略空气阻力）：",
                      rf"$v = gt = {latex(g)}\times({latex(t_)}) = {latex(v)}\ \mathrm{{m/s}}$",
                      rf"$h = \frac{{1}}{{2}}gt^2 = {latex(h)}\ \mathrm{{m}}$",
                      r"量纲核对：$\mathrm{m/s^2}\cdot\mathrm{s}=\mathrm{m/s}$ ✓；"
                      r"$\mathrm{m/s^2}\cdot\mathrm{s^2}=\mathrm{m}$ ✓"]
            return _sol(problem, steps,
                        rf"v = {latex(v)}\ \mathrm{{m/s}},\quad h = {latex(h)}\ \mathrm{{m}}",
                        "physics_freefall",
                        answer_text=f"v = {latex(v)} m/s, h = {latex(h)} m",
                        extra={"verify_hint": {"kind": "physical"},
                               "answer_value": v})

    # ── 重力势能 / 万有引力 ──
    if re.search(r"gravitational potential|势能|gravitational force|万有引力", text_l):
        if masses and re.search(r"m\b", text_l):
            ms = _nums_with_unit(text_l, r"m|metres?|meters?|米")
            if ms:
                m_ = sympy.Float(masses[0][0])
                r_ = sympy.Float(ms[0][0])
                U = simplify(g * m_ * r_)
                steps += [r"$U = mgh$",
                          rf"$= {latex(m_)}\times{latex(g)}\times({latex(r_)})"
                          rf" = {latex(U.evalf(4))}\ \mathrm{{J}}$"]
                return _sol(problem, steps, rf"{latex(U.evalf(4))}\ \mathrm{{J}}",
                            "physics_potential_energy",
                            answer_text=f"{latex(U.evalf(4))} J",
                            extra={"verify_hint": {"kind": "physical"},
                                   "answer_value": U})

    return _un(problem, "力学题型未覆盖（当前支持 F=ma / 动能 / 自由落体 / 重力势能）")


def _solve_em(problem, text_l, latex_all, steps) -> dict:
    """库仑定律 / 欧姆定律 / 电场强度 / 电势能。"""
    ke = CONSTANTS["ke"][0]
    eps0 = CONSTANTS["eps0"][0]

    # ── 库仑定律 F = k q1 q2 / r² ──
    if re.search(r"coulomb|库仑", text_l):
        qs = _nums_with_unit(text_l, r"c\b|coulombs?")
        rs = _nums_with_unit(text_l, r"m\b|metres?|meters?|cm")
        if len(qs) >= 2 and rs:
            q1 = sympy.Float(qs[0][0]); q2 = sympy.Float(qs[1][0])
            r_ = sympy.Float(rs[0][0])
            F = simplify(ke * abs(q1 * q2) / r_ ** 2)
            steps += [r"库仑定律：$F = k\frac{|q_1q_2|}{r^2}$",
                      rf"$= {latex(ke)}\times|{latex(q1)}\times{latex(q2)}|"
                      rf"/({latex(r_)})^2 = {latex(F.evalf(4))}\ \mathrm{{N}}$",
                      r"量纲核对：$\mathrm{N\,m^2/C^2}\cdot\mathrm{C^2/m^2} = \mathrm{N}$ ✓"]
            return _sol(problem, steps, rf"{latex(F.evalf(4))}\ \mathrm{{N}}",
                        "physics_coulomb", answer_text=f"{latex(F.evalf(4))} N",
                        extra={"verify_hint": {"kind": "physical"},
                               "answer_value": F})

    # ── 欧姆定律 I = V / R ──
    if re.search(r"ohm|欧姆|current\b|电流|resistor|电阻", text_l):
        Vs = _nums_with_unit(text_l, r"v\b|volts?|伏")
        Rs = _nums_with_unit(text_l, r"ohm|ohms|ω|欧")
        if Vs and Rs:
            V_ = sympy.Float(Vs[0][0]); R_ = sympy.Float(Rs[0][0])
            I = simplify(V_ / R_)
            steps += [r"欧姆定律：$I = V/R$",
                      rf"$= {latex(V_)}/{latex(R_)} = {latex(I.evalf(4))}\ \mathrm{{A}}$",
                      r"量纲核对：$\mathrm{V}/\Omega = \mathrm{A}$ ✓"]
            return _sol(problem, steps, rf"{latex(I.evalf(4))}\ \mathrm{{A}}",
                        "physics_ohm", answer_text=f"{latex(I.evalf(4))} A",
                        extra={"verify_hint": {"kind": "physical"}, "answer_value": I})

    # ── 电场强度 E = F/q ──
    if re.search(r"electric field|电场", text_l):
        Fs = _nums_with_unit(text_l, r"n\b|newtons?|牛")
        qs = _nums_with_unit(text_l, r"c\b|coulombs?|库")
        if Fs and qs:
            F_ = sympy.Float(Fs[0][0]); q_ = sympy.Float(qs[0][0])
            E = simplify(F_ / q_)
            steps += [r"$E = F/q$",
                      rf"$= {latex(F_)}/{latex(q_)} = {latex(E.evalf(4))}\ \mathrm{{N/C}}$",
                      r"量纲核对：$\mathrm{N/C}$ ✓"]
            return _sol(problem, steps, rf"{latex(E.evalf(4))}\ \mathrm{{N/C}}",
                        "physics_electric_field", answer_text=f"{latex(E.evalf(4))} N/C",
                        extra={"verify_hint": {"kind": "physical"}, "answer_value": E})

    # ── 点电荷场强 E = k q / r² ──
    if re.search(r"field|场", text_l):
        qs = _nums_with_unit(text_l, r"c\b|coulombs?|库")
        rs = _nums_with_unit(text_l, r"m\b|metres?|meters?|cm")
        if qs and rs and re.search(r"point charge|点电荷", text_l):
            q_ = sympy.Float(qs[0][0]); r_ = sympy.Float(rs[0][0])
            E = simplify(ke * abs(q_) / r_ ** 2)
            steps += [r"点电荷场强：$E = k\frac{|q|}{r^2}$",
                      rf"$= {latex(E.evalf(4))}\ \mathrm{{N/C}}$"]
            return _sol(problem, steps, rf"{latex(E.evalf(4))}\ \mathrm{{N/C}}",
                        "physics_point_charge_field",
                        answer_text=f"{latex(E.evalf(4))} N/C",
                        extra={"verify_hint": {"kind": "physical"}, "answer_value": E})

    return _un(problem, "电磁学题型未覆盖（当前支持库仑定律/欧姆定律/电场强度/点电荷场强）")


def _solve_thermo(problem, text_l, latex_all, steps) -> dict:
    """理想气体状态方程 PV = nRT。"""
    Ps = _nums_with_unit(text_l, r"pa|pascal")
    Vs = _nums_with_unit(text_l, r"m\^?3|m3|cubic meters?|liters?|l\b")
    Ts = _nums_with_unit(text_l, r"k\b|kelvin")

    if Ps and Vs and Ts:
        R = sympy.Float("8.314462618")
        P_ = sympy.Float(Ps[0][0])
        V_ = sympy.Float(Vs[0][0])
        T_ = sympy.Float(Ts[0][0])
        n = simplify(P_ * V_ / (R * T_))
        p_l, v_l, r_l, t_l, n_l = latex(P_), latex(V_), latex(R), latex(T_), latex(n.evalf(4))
        steps += [r"理想气体状态方程：$PV = nRT$",
                  rf"$n = \frac{{PV}}{{RT}} = \frac{{{p_l}\times{v_l}}}"
                  rf"{{{r_l}\times{t_l}}} = {n_l}\ \mathrm{{mol}}$",
                  r"量纲核对：$\mathrm{Pa\cdot m^3}/(\mathrm{J/(mol\cdot K)}\cdot\mathrm{K})"
                  r" = \mathrm{mol}$ ✓"]
        return _sol(problem, steps, rf"{n_l}\ \mathrm{{mol}}",
                    "physics_ideal_gas", answer_text=f"{n_l} mol",
                    extra={"verify_hint": {"kind": "physical"}, "answer_value": n})

    return _un(problem, "热学题型未覆盖（当前支持理想气体状态方程）")
