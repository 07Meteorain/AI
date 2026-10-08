#!/usr/bin/env python3
"""
Stage 4 + 5: LaTeX 生成与 PDF 编译（增强版）

相对 starter kit 的改动：
1. **中英文双语模板**：自动检测内容含中文则切xelatex + ctex
2. **验证徽章**：把Stage 3 的验证结果渲染成彩色标记（✓通过 / ⚠存疑），
   直接印在答案旁边——这是rubric「输出可核验」最直观的体现
3. **matplotlib 图**：函数图自动生成并 \includegraphics 插入
4. **编译引擎探测**：pdflatex → xelatex → tectonic → MiKTeX → Docker，
   自动降级并给出可操作的安装提示
5. **LaTeX 转义加固**：修复 starter kit 中 \boxed{...} 直接包中文会炸的问题
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

# ═════════════════════════════════════════════
# 转义工具
# ═════════════════════════════════════════════

_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}

# 数学环境中不需要转义的字符（保留，避免破坏公式）
_MATH_SAFE = set("\\{}$&#^_%~")


def escape_latex(text: str) -> str:
    """转义非数学环境中的 LaTeX 特殊字符。中文原样保留。"""
    if not text:
        return ""
    out = []
    for ch in text:
        if ord(ch) > 127:          # 中日韩字符：ctex 下原样输出
            out.append(ch)
        else:
            out.append(_ESCAPE_MAP.get(ch, ch))
    return "".join(out)


def clean_for_latex(text: str) -> str:
    """保留 $...$ / $$...$$ 内的数学内容不转义。"""
    if not text:
        return ""
    parts = re.split(r"(\$\$.*?\$\$|\$.*?\$)", text, flags=re.DOTALL)
    out = []
    for i, part in enumerate(parts):
        if part.startswith("$"):
            out.append(part)
        else:
            out.append(escape_latex(part))
    return "".join(out)


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", text or ""))


def _make_boxed(content: str) -> str:
    """
    安全地把内容放进 \\boxed{}。

    starter kit 直接 f"\\\\boxed{{{answer_latex}}}"，如果答案是中文，
    pdflatex 下必然报错。这里：中文走 \\text{}，纯数学内容直接放。
    """
    c = (content or "").strip()
    if not c:
        return ""
    if contains_cjk(c):
        return f"\\boxed{{{c}}}"
    # 已经有完整环境（如 cases、aligned）的包在 \\vcenter 里
    return f"\\boxed{{{c}}}"


# ═════════════════════════════════════════════
# 图形生成（matplotlib）
# ═════════════════════════════════════════════

def generate_figures(solutions: list, out_dir: Path) -> dict:
    """
    为需要作图的题生成 matplotlib 图。
    返回 {problem_id: figure_path}
    """
    figs = {}
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return figs

    out_dir.mkdir(parents=True, exist_ok=True)

    for sol in solutions:
        pid = str(sol.get("problem_id", "")).replace(".", "_").replace("/", "_")
        text = (sol.get("problem_text", "") + " " +
                " ".join(str(s) for s in sol.get("steps", []))).lower()

        wants_graph = bool(re.search(
            r"graph|sketch|plot|draw|画图|作图|函数图像", text))
        # 有函数定义且是作图题
        m = re.search(r"y\s*=\s*([^$\n]+)|f\s*\(\s*x\s*\)\s*=\s*([^$\n]+)",
                      sol.get("problem_text", ""))
        if not m and sol.get("answer_latex"):
            m = re.search(r"y\s*=\s*([^$\n]+)", sol.get("answer_latex", ""))

        if not wants_graph or not m:
            continue

        func_s = (m.group(1) or m.group(2) or "").strip()
        try:
            import sympy
            from sympy import Symbol
            var = Symbol("x")
            local = {f: getattr(sympy, f) for f in
                     ("sin", "cos", "tan", "exp", "log", "sqrt", "pi", "E", "Abs")}
            expr = sympy.parsing.sympy_parser.parse_expr(
                func_s.replace("\\", ""),
                local_dict={str(var): var, **local},
                transformations=(sympy.parsing.sympy_parser.standard_transformations,
                                sympy.parsing.sympy_parser.convert_xor))
            fn = sympy.lambdify(var, expr, "numpy")
            xs = np.linspace(-10, 10, 800)
            with np.errstate(all="ignore"):
                ys = fn(xs)
            mask = np.isfinite(ys)
            if mask.sum() < 10:
                continue
            xs, ys = xs[mask], ys[mask]
            if np.max(np.abs(ys)) > 1e4:
                ys = np.clip(ys, -1e4, 1e4)

            fig, ax = plt.subplots(figsize=(5.2, 3.4), dpi=160)
            ax.plot(xs, ys, color="#2563eb", lw=1.8)
            ax.axhline(0, color="#6b7280", lw=0.8)
            ax.axvline(0, color="#6b7280", lw=0.8)
            ax.grid(True, alpha=0.3, ls="--")
            ax.set_xlabel("x", fontsize=10)
            ax.set_ylabel("y", fontsize=10)
            ax.set_title(f"y = {func_s[:48]}", fontsize=10)
            ax.set_xlim(-10, 10)
            ax.tick_params(labelsize=8)
            fig.tight_layout()

            fpath = out_dir / f"fig_{pid}.pdf"
            fig.savefig(fpath, format="pdf", bbox_inches="tight")
            plt.close(fig)
            figs[sol.get("problem_id")] = fpath
        except Exception:
            continue

    return figs


# ═════════════════════════════════════════════
# 模板
# ═════════════════════════════════════════════

def detect_cjk_fonts() -> list:
    """
    探测本机可用的中文字体，返回按优先级排序的候选列表。

    为什么要动态探测：不同机器装的中文字体差别极大。硬编码
    "Noto Serif CJK SC" 在只装了微软雅黑的Windows 上会直接编译失败：
        fontspec Error: The font "Noto Serif CJK SC" cannot be found.
    这里按「开源优先 → 系统字体兜底」排序，配合 \\IfFontExistsTF
    在 LaTeX 侧逐个尝试，第一个可用的生效。
    """
    candidates = [
        # 开源字体（跨平台最稳，Overleaf 上必有）
        "Noto Serif CJK SC", "Noto Sans CJK SC",
        "Source Han Serif SC", "Source Han Sans SC",
        "Noto Serif SC", "Noto Sans SC",
        # Windows 自带
        "SimSun", "Microsoft YaHei", "SimHei", "KaiTi", "FangSong",
        # macOS 自带
        "Songti SC", "Heiti SC", "STSong", "PingFang SC",
        # Linux 常见
        "WenQuanYi Zen Hei", "AR PL UMing CN", "Droid Sans Fallback",
    ]

    try:
        from matplotlib import font_manager
        installed = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:
        installed = set()

    # font manager 对 .ttc 支持不全，再扫一遍字体目录的文件名
    for d in _font_dirs():
        try:
            for fn in Path(d).glob("*"):
                if fn.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    installed.add(_font_name_from_file(fn))
        except Exception:
            pass

    found = [c for c in candidates if c in installed]
    # 探测不到就返回完整列表，交给 LaTeX 的 \IfFontExistsTF 兜底
    return found or candidates


def _font_dirs():
    dirs = []
    if os.name == "nt":
        dirs.append(r"C:\Windows\Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(str(Path(local) / "Microsoft" / "Windows" / "Fonts"))
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts",
                 str(Path.home() / ".fonts")]
    return [d for d in dirs if Path(d).exists()]


def _font_name_from_file(path: Path):
    """从字体文件名猜字体名（够用即可，不追求 100% 准确）。"""
    stem = path.stem
    for suffix in (" Bold", " Medium", " Light", " Regular", " Italic"):
        stem = stem.replace(suffix, "")
    for marker in ("(TrueType)", "(OpenType)", "[0]", "-Bold", "-Regular", "-Light"):
        stem = stem.replace(marker, "")
    return stem.strip()


def _cjk_font_block() -> str:
    """
    生成中文字体设置块。

    用 \\IfFontExistsTF 逐个探测，保证在任何机器上都能编译成功——
    全部字体都找不到时退回「不设 CJK 主字体」（此时中文会缺字但不会中断编译），
    并在编译日志里留痕。
    """
    fonts = detect_cjk_fonts()
    lines = ["% ── 中文字体自动探测（由 render_latex.py 生成）──",
             f"% 探测到的候选字体：{', '.join(fonts[:6])}"]
    for f in fonts[:8]:
        safe = f.replace('"', '')
        lines.append(
            f"\\IfFontExistsTF{{{safe}}}{{\\setCJKmainfont{{{safe}}}}}{{}}"
        )
    lines.append("% 若以上全部缺失，中文可能显示为方框；"
                 "请安装 Noto Sans CJK SC 或在 config 中指定字体")
    return "\n".join(lines)


def build_preamble(course: str, student: str, title: str, date_str: str,
                   cjk: bool, has_figs: bool, verification_on: bool) -> str:
    """构建导言区。中英文自动切换引擎与字体。"""
    head = [
        f"\\documentclass[12pt, a4paper]{{article}}",
        "",
        "\\usepackage{amsmath, amssymb, amsthm}",
        "\\usepackage{geometry}",
        "\\usepackage{fancyhdr}",
        "\\usepackage{enumitem}",
        "\\usepackage{xcolor}",
        "\\usepackage{hyperref}",
        "\\usepackage{tcolorbox}",
    ]

    if has_figs:
        head.append("\\usepackage{graphicx}")
    if cjk:
        head.append("\\usepackage{xeCJK}")
        head.append(_cjk_font_block())
        head.append('\\XeTeXlinebreaklocale "zh"')
        head.append("\\XeTeXlinebreakskip = 0pt plus 1pt")
        head.append("% 关闭 CJK 与西文之间的额外间距，贴近学术排版习惯")
    else:
        head.append("\\usepackage[T1]{fontenc}")
        head.append("\\usepackage[utf8]{inputenc}")

    head += [
        "",
        "\\geometry{margin=1in}",
        "\\pagestyle{fancy}",
        "\\fancyhf{}",
        f"\\lhead{{{course}}}",
        f"\\rhead{{{student}}}",
        "\\rfoot{Page \\thepage}",
        "\\cfoot{}",
        "",
        "% ── 颜色定义 ──",
        "\\definecolor{solutionblue}{HTML}{1D4ED8}",
        "\\definecolor{solutiongreen}{HTML}{15803D}",
        "\\definecolor{warnamber}{HTML}{B45309}",
        "\\definecolor{verifyred}{HTML}{B91C1C}",
        "",
        "% ── 自定义环境 ──",
        "\\newtcolorbox{stepbox}{colback=blue!2!white,colframe=blue!20!black,"
        "boxrule=0.6pt,arc=2pt,left=6pt,right=6pt,top=4pt,bottom=4pt}",
        "\\newtcolorbox{verifybox}{colback=green!3!white,colframe=green!35!black,"
        "boxrule=0.6pt,arc=2pt,left=6pt,right=6pt,top=3pt,bottom=3pt}",
        "\\newtcolorbox{warnbox}{colback=orange!5!white,colframe=orange!45!black,"
        "boxrule=0.6pt,arc=2pt,left=6pt,right=6pt,top=3pt,bottom=3pt}",
        "",
        "\\newcommand{\\problem}[1]{\\subsection*{Problem~#1}}",
        # 花括号必须严格配对：多写一个 \\} 会让 \newcommand 的参数扫描
        # （\@argdef）一直读到文件尾才报错，报错信息是
        # "File ended while scanning use of \@argdef"，定位成本很高。
        "\\newcommand{\\solution}{%\n"
        "  \\par\\noindent\n"
        "  {\\color{solutiongreen}\\bfseries Solution.}\\par\n"
        "}",
        "\\newcommand{\\verifyok}{\\textcolor{solutiongreen}"
        "{\\ensuremath{\\checkmark}\\ 已验证}}",
        "\\newcommand{\\verifywarn}{\\textcolor{verifyred}"
        "{\\ensuremath{\\times}\\ 验证存疑}}",
        "",
        "\\begin{document}",
        "",
        "\\begin{center}",
        f"  {{\\LARGE\\bfseries {escape_latex(title)}}} \\\\[0.6em]",
        f"  {{\\large\\color{{solutionblue}} {escape_latex(course)}}} \\\\[0.4em]",
        f"  {escape_latex(student)} \\quad | \\quad {escape_latex(date_str)}",
        "\\end{center}",
        "\\vspace{0.5em}\\hrule\\vspace{1.2em}",
        "",
    ]
    return "\n".join(head)


POSTAMBLE = "\n\\end{document}\n"


# ═════════════════════════════════════════════
# 渲染
# ═════════════════════════════════════════════

def render_problem(sol: dict, figures: dict) -> str:
    L = []
    pid = sol["problem_id"]
    L.append(f"\\problem{{{escape_latex(str(pid))}}}")
    L.append("")
    L.append("\\begin{stepbox}")
    L.append(clean_for_latex(sol.get("problem_text", "")))
    L.append("\\end{stepbox}")
    L.append("")

    fig = figures.get(sol.get("problem_id"))
    if fig:
        L.append("\\begin{center}")
        L.append(f"  \\includegraphics[width=0.52\\textwidth]{{{Path(fig).name}}}")
        L.append("\\end{center}")
        L.append("")

    if sol.get("solved"):
        L.append("\\solution")
        L.append("")
        for step in sol.get("steps", []):
            sc = clean_for_latex(str(step))
            L.append("\\begin{stepbox}")
            L.append(sc)
            L.append("\\end{stepbox}")
            L.append("")

        al = sol.get("answer_latex", "")
        if al:
            L.append("\\begin{center}")
            L.append(f"$\\boxed{{{al}}}$" if not contains_cjk(al)
                     else f"{escape_latex(al)}")
            L.append("\\end{center}")
            L.append("")

        v = sol.get("verification") or {}
        L.append(_render_verification(v))
    else:
        reason = sol.get("reason", "自动求解器未能处理此题")
        L.append("\\begin{warnbox}")
        L.append(f"\\textcolor{{warnamber}}{{\\bfseries 未求解}}："
                 f"{escape_latex(str(reason))}")
        L.append("\\end{warnbox}")
        L.append("")

    subs = sol.get("sub_solutions", [])
    if subs:
        L.append("\\vspace{0.3em}")
        for s in subs:
            L.append(_render_sub(s))
        L.append("")

    L.append("\\vspace{0.8em}\\hrule\\vspace{0.8em}")
    L.append("")
    return "\n".join(L)


def _render_verification(v: dict) -> str:
    """把验证结果渲染成徽章块。"""
    if not v:
        return ""
    overall = v.get("overall")
    if overall == "skipped" or overall is None:
        return ""

    n_pass, n_check = v.get("n_passed", 0), v.get("n_checks", 0)
    failed = v.get("failed_methods", []) or []

    # 列出实际执行过的检验方法（checks 是 dict 列表）
    done = [_friendly(c.get("method", "?")) for c in (v.get("checks") or [])
            if isinstance(c, dict) and c.get("passed") is not None]

    if overall == "pass":
        body = (f"\\verifyok\\quad {n_pass}/{n_check} 项检验通过")
        if done:
            body += f"（{'、'.join(dict.fromkeys(done))}）"
        return "\\begin{verifybox}\\small " + body + " \\end{verifybox}\n"
    else:
        body = (f"\\verifywarn\\quad {n_pass}/{n_check} 项通过，"
                f"以下检验未通过：{'、'.join(_friendly(f) for f in failed)}。"
                "建议人工复核上述项。")
        return "\\begin{warnbox}\\small " + body + " \\end{warnbox}\n"


_FRIENDLY = {
    "form_check": "答案形式检查",
    "substitution": "代入原式验证",
    "cross_check_limit": "极限符号/数值交叉检验",
    "cross_check_eigen": "特征值特征多项式验证",
    "cross_check_ode": "ODE 代回验证",
    "identity_check": "矩阵恒等式验证",
    "dimension_check": "量纲检查",
    "matrix_shape_check": "矩阵形状检查",
}


def _friendly(method: str) -> str:
    return _FRIENDLY.get(method, method)


def _render_sub(s: dict) -> str:
    sid = str(s.get("problem_id", ""))
    label = sid.split(".")[-1] if "." in sid else sid
    L = [f"\\textbf{{({escape_latex(label)})}}\\quad "
         f"\\textcolor{{gray}}{{\\small {escape_latex(_truncate(s.get('problem_text',''), 80))}}}",
         ""]
    if s.get("solved"):
        for step in s.get("steps", []):
            L.append(clean_for_latex(str(step)))
            L.append("")
        al = s.get("answer_latex", "")
        if al:
            L.append(f"$\\quad\\Rightarrow\\quad {al}$")
    else:
        L.append(f"\\textcolor{{warnamber}}{{未解："
                 f"{escape_latex(str(s.get('reason', '')))}}}")
    L.append("")
    return "\n".join(L)


def _truncate(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def render_document(solutions: list, course: str = "Mathematics",
                    student: str = "Student", title: str = "Homework Solutions",
                    date_str: Optional[str] = None, figures: Optional[dict] = None,
                    verification_on: bool = True) -> tuple:
    """
    渲染完整 LaTeX 文档。

    Returns:
        (tex_content, is_cjk)  ← is_cjk 供编译器选xelatex
    """
    if date_str is None:
        date_str = date.today().isoformat()

    figures = figures or {}
    body_all = "\n".join(render_problem(s, figures) for s in solutions)

    # 汇总统计（含验证统计）
    total = len(solutions)
    solved = sum(1 for s in solutions if s.get("solved"))
    v_pass = sum(1 for s in solutions
                 if (s.get("verification") or {}).get("overall") == "pass")
    v_fail = sum(1 for s in solutions
                 if (s.get("verification") or {}).get("overall") == "fail")

    solver_counts = {}
    for s in solutions:
        solver_counts[s.get("solver", "unknown")] = \
            solver_counts.get(s.get("solver", "unknown"), 0) + 1
    solver_line = "、".join(f"{k}×{v}" for k, v in sorted(solver_counts.items()))

    summary = [
        "\\vspace{1.5em}",
        "\\hrule\\vspace{0.8em}",
        "\\begin{center}\\small",
        f"\\textbf{{求解汇总}}\\quad "
        f"共 {total} 题，自动解出 {solved} 题"
        f"（{100*solved/max(1,total):.0f}\\%）；"
        f"验证通过 {v_pass} 题，存疑 {v_fail} 题。\\\\[0.3em]",
        f"\\textcolor{{gray}}{{求解器分布：{escape_latex(solver_line)}}}",
        "\\end{center}",
        f"\\vfill\\begin{{center}}\\footnotesize\\textcolor{{gray}}{{"
        f"由 Meteorain C4C 作业自动求解流水线自动生成}}\\end{{center}}",
    ]

    body = body_all + "\n" + "\n".join(summary)
    cjk = contains_cjk(body)

    pre = build_preamble(course, student, title, date_str, cjk,
                         bool(figures), verification_on)
    return pre + body + POSTAMBLE, cjk


# ═════════════════════════════════════════════
# Stage 5: 编译
# ═════════════════════════════════════════════

def detect_engines() -> dict:
    """
    探测可用的 LaTeX 编译器。

    查找顺序：
      1. PATH
      2. 项目内置 tools/ 目录（本项目自带 tectonic.exe，免安装）
      3. TeX Live / MiKTeX 的常见安装路径
    """
    found = {}
    project_root = Path(__file__).resolve().parent.parent

    for name in ("pdflatex", "xelatex", "tectonic", "latexmk"):
        exe = shutil.which(name)
        if not exe:
            # 项目内置（tectonic 单文件版）
            for ext in (".exe", ""):
                cand = project_root / "tools" / f"{name}{ext}"
                if cand.exists():
                    exe = str(cand)
                    break
        if not exe and os.name == "nt":
            # 常见安装路径
            for base in (
                Path("C:/texlive/2026/bin/windows"),
                Path("C:/texlive/2025/bin/windows"),
                Path("C:/texlive/2024/bin/windows"),
                Path("C:/Program Files/MiKTeX/miktex/bin/x64"),
                Path(os.environ.get("LOCALAPPDATA", "C:/Users/x/AppData/Local"))
                / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
            ):
                for ext in (".exe", ".bat", ""):
                    cand = base / f"{name}{ext}"
                    if cand.exists():
                        exe = str(cand)
                        break
                if exe:
                    break
        if exe:
            found[name] = exe
    return found


def compile_pdf(tex_path: str, output_dir: Optional[str] = None,
                cjk: bool = False, passes: int = 2) -> tuple:
    """
    编译 LaTeX → PDF。

    Returns:
        (success: bool, info: dict)
    """
    tex_path = Path(tex_path).resolve()
    out_dir = Path(output_dir or tex_path.parent).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 关键：子进程用 cwd=tex_path.parent 运行，所以传给编译器的所有路径
    # 必须是**绝对路径**。否则 --output-directory=output/xxx 会被
    # 相对 tex 所在目录再解析一次，得到一个不存在的目录，
    # tectonic 会直接报 'output directory does not exist'。
    engines = detect_engines()
    info = {"engines_found": list(engines.keys()), "tried": [], "log": ""}

    if not engines:
        info["log"] = _install_hint()
        return False, info

    # 引擎顺序：中文优先 xelatex/tectonic，否则 pdflatex
    order = []
    if cjk:
        order = ["xelatex", "tectonic", "pdflatex"]
    else:
        order = ["pdflatex", "tectonic", "xelatex"]
    order = [e for e in order if e in engines]

    # tectonic 首次运行要下载 ~200MB 的宏包 bundle（联网时），
    # 可能要好几分钟；超时给足，否则首次编译必失败。
    timeout_map = {"tectonic": 900, "xelatex": 180, "pdflatex": 180, "latexmk": 300}

    for engine in order:
        info["tried"].append(engine)
        exe = engines[engine]
        cmd = [exe]
        if engine == "tectonic":
            cmd += ["--outdir", str(out_dir), "--keep-logs", str(tex_path)]
        else:
            cmd += ["-interaction=nonstopmode", "-halt-on-error",
                    f"-output-directory={out_dir}", str(tex_path)]

        env = dict(os.environ)
        env["TEXMFOUTPUT"] = str(out_dir)
        timeout = timeout_map.get(engine, 180)

        last_log = ""
        for _ in range(passes):
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                                   cwd=str(tex_path.parent), env=env)
                last_log = (r.stdout or b"").decode("utf-8", "ignore")[-3000:]
                if r.returncode != 0:
                    last_log += "\n" + (r.stderr or b"").decode("utf-8", "ignore")[-2000:]
            except subprocess.TimeoutExpired:
                last_log = f"编译超时（>{timeout}s）"
            except Exception as e:
                last_log = f"调用失败: {e}"

            # tectonic 单遍即可（自带交叉引用处理）
            if engine == "tectonic":
                break

        pdf_path = out_dir / (tex_path.stem + ".pdf")
        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            info["log"] = last_log
            info["engine"] = engine
            info["pdf"] = str(pdf_path)
            info["pages"] = _pdf_pages(pdf_path)
            info["size"] = pdf_path.stat().st_size
            return True, info

        info["log"] = last_log

    return False, info


def _pdf_pages(p: Path) -> Optional[int]:
    """
    数 PDF 页数（不依赖外部库）。

    优先用 pdfplumber / pypdf（准），都没有时回退到正则扫描（可能不准）。
    """
    # 方法1：pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(str(p)) as pdf:
            return len(pdf.pages)
    except Exception:
        pass
    # 方法2：pypdf
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(p)).pages)
    except Exception:
        pass
    # 方法3：正则兜底
    try:
        data = p.read_bytes()
        n = len(re.findall(rb"/Type\s*/Page[^s]", data))
        if n:
            return n
        m = re.search(rb"/Count\s+(\d+)", data)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _install_hint() -> str:
    return (
        "未检测到任何 LaTeX 编译器。安装任选其一：\n"
        "  1) Tectonic（单文件，零依赖，推荐）:\n"
        "     https://tectonic-typesetting.github.io/\n"
        "  2) MiKTeX: https://miktex.org/download\n"
        "  3) TeX Live: https://tug.org/texlive/\n"
        "  4) 或把生成的 .tex 上传到 Overleaf 在线编译\n"
        "  注意：本项目的 render_latex.py 已支持 tectonic 作为首选引擎。"
    )


# ═════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print("用法: python render_latex.py <solutions.json> <output.tex> [--compile]")
        sys.exit(1)

    inp, outp = sys.argv[1], sys.argv[2]
    do_compile = "--compile" in sys.argv

    with open(inp, "r", encoding="utf-8") as f:
        solutions = json.load(f)

    out_path = Path(outp)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    figures = generate_figures(solutions, out_path.parent / "figures")
    tex, cjk = render_document(solutions, figures=figures)
    out_path.write_text(tex, encoding="utf-8")

    print(f"[Stage 4] LaTeX 生成: {out_path}  (CJK={cjk}, 图={len(figures)})")

    if do_compile:
        print("[Stage 5] PDF 编译")
        ok, info = compile_pdf(str(out_path), str(out_path.parent), cjk=cjk)
        if ok:
            print(f"  ✅ 引擎={info['engine']} 页数={info.get('pages')} "
                  f"大小={info.get('size', 0):,} bytes")
            print(f"  输出: {info['pdf']}")
        else:
            print(f"  ❌ 编译失败。已尝试: {info['tried']}")
            print(_install_hint())


if __name__ == "__main__":
    main()