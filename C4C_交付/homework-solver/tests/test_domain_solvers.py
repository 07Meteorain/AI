#!/usr/bin/env python3
"""域求解器单元测试：直接测 LaTeX 矩阵/ODE/物理解析，不走完整流水线。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import sympy
from sympy import Matrix, latex
import domain_solvers as DS

BS = chr(92)  # backslash，避免 shell 转义问题

def mk(mtype="pmatrix", body=None):
    body = body if body is not None else "1 & 2 " + BS+BS+ " 3 & 4"
    return BS+"begin{" + mtype + "}" + body + BS+"end{" + mtype + "}"

def prob(pid, text, latex_list):
    return {
        "id": pid, "text": text,
        "math_expressions": [{"type": "display", "latex": L} for L in latex_list],
        "sub_problems": [], "type": "matrix",
    }

print("=" * 60)
print("1. 矩阵 LaTeX 解析")
M = DS.parse_latex_matrix(mk())
print("   2x2 =", M.tolist(), "-> 期望 [[1,2],[3,4]]")

print("\n2. 3x2 矩阵（向量为行）")
M2 = DS.parse_latex_matrix(mk(body="1 & 1 " + BS+BS+ " 1 & 0 " + BS+BS+ " 0 & 1"))
print("   shape =", M2.shape, "-> 期望 (3, 2)")
print("   rows =", [M2[i, :].tolist() for i in range(M2.rows)])

print("\n3. 3x3 带分数")
M3 = DS.parse_latex_matrix(mk(body="1/2 & 0 " + BS+BS+ " 0 & 3"))
M3b = DS.parse_latex_matrix(mk(body=BS+"frac{1}{2} & 0 " + BS+BS+ " 0 & 3"))
print("   frac 解析 =", M3b.tolist(), "-> 期望 [[1/2, 0],[0, 3]]")

print("\n4. 各类矩阵意图")
cases = [
    ("行列式", "Compute the determinant of $A$", [mk()], "det"),
    ("逆矩阵(LaTeX上标)", "Find $A^{-1}$ for the matrix", [mk()], "inv"),
    ("逆矩阵(英文)", "Find the inverse of $A$", [mk()], "inv"),
    ("特征值", "Find the eigenvalues of $A$", [mk()], "eig"),
    ("特征向量", "Find the eigenvectors of $A$", [mk()], "eigv"),
    ("秩", "Compute the rank of $A$", [mk(body="1 & 2 " + BS+BS+" 2 & 4")], "rank"),
    ("转置", "Find the transpose of $A$", [mk()], "T"),
    ("迹", "Compute the trace of $A$", [mk()], "trace"),
    ("正交判定", "Determine whether the columns of $A$ are orthogonal",
     [mk(body="1 & 1 " + BS+BS + " 0 & 1")], "orth-check"),
    ("Gram-Schmidt(方阵)", "Apply Gram-Schmidt to $A$", [mk()], "gs"),
    ("Gram-Schmidt(3x2)", "Apply Gram-Schmidt orthogonalization to $A$",
     [mk(body="1 & 1 " + BS+BS + " 1 & 0 " + BS+BS + " 0 & 1")], "gs"),
    ("标准正交", "Orthonormalize the vectors of $A$",
     [mk(body="1 & 1 " + BS+BS + " 0 & 1")], "ortho"),
    ("RREF", "Find the rref of $A$", [mk(body="1 & 2 " + BS+BS + " 2 & 4")], "rref"),
    ("零空间", "Find the null space of $A$",
     [mk(body="0 & 0 " + BS+BS + " 0 & 0")], "null"),
    ("SVD", "Find the singular values of $A$", [mk()], "svd"),
    ("对角化", "Diagonalize $A$", [mk(body="4 & 1 " + BS+BS + " 2 & 3")], "diag"),
]
for name, text, lats, expect in cases:
    r = DS.solve_matrix(prob("T", text, lats))
    got = "?" if not r.get("solved") else r.get("solver", "?")
    ok = r.get("solved")
    ans = (r.get("answer_latex") or r.get("reason", ""))[:52]
    print(f"   {'OK ' if ok else 'FAIL'} [{expect:11}] {name:22} -> {got:26} {ans}")

print("\n5. 微分方程")
ode_cases = [
    ("一阶线性+IVP", "Solve $y' + 2y = e^{-x}$ with $y(0) = 1$",
     ["y' + 2y = e^{-x}", "y(0) = 1"]),
    ("齐次一阶", "Solve the ODE $y' - 3y = 0$", ["y' - 3y = 0"]),
    ("二阶常系数", "Solve $y'' - 5y' + 6y = 0$", ["y'' - 5y' + 6y = 0"]),
    ("可分离变量", "Solve $\\frac{dy}{dx} = x y$", [BS+"frac{dy}{dx} = xy"]),
]
for name, text, lats in ode_cases:
    p = {"id": name, "text": text,
         "math_expressions": [{"type": "display", "latex": L} for L in lats],
         "sub_problems": [], "type": "ode"}
    r = DS.solve_ode(p)
    ok = r.get("solved")
    ans = (r.get("answer_latex") or r.get("reason", ""))[:70]
    print(f"   {'OK ' if ok else 'FAIL'} {name:16} -> {ans}")

print("\n6. 大学物理")
phys_cases = [
    ("牛顿第二定律", "A force acts on a 2.0 kg mass producing an "
     "acceleration of 3.0 m/s^2. Find the force.", []),
    ("自由落体", "A ball is dropped from rest and falls for 2 s. "
     "Find its speed and the height fallen.", []),
    ("动能", "Find the kinetic energy of a 3.0 kg object moving at 4.0 m/s.", []),
    ("库仑定律", "Two charges of 2.0 C and 3.0 C are separated by a "
     "distance of 1 m. Find the Coulomb force.", []),
    ("欧姆定律", "A 12 V potential is applied across a 4 ohm resistor. "
     "Find the current.", []),
    ("电场强度", "Find the electric field if a force of 6.0 N acts on "
     "a charge of 3.0 C.", []),
    ("理想气体", "A gas occupies 0.02 m^3 at 300 K and 101325 Pa. "
     "Find the number of moles.", []),
]
for name, text, lats in phys_cases:
    p = {"id": name, "text": text,
         "math_expressions": [{"type": "display", "latex": L} for L in lats],
         "sub_problems": [], "type": "physics"}
    r = DS.solve_physics(p)
    ok = r.get("solved")
    ans = (r.get("answer_latex") or r.get("reason", ""))[:60]
    print(f"   {'OK ' if ok else 'FAIL'} {name:14} [{r.get('solver','?')}] {ans}")

print("\n" + "=" * 60)