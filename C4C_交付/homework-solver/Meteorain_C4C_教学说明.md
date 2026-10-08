# Meteorain_C4C_教学说明.md

> 安装、使用、扩展指南
> 作者：Meteorain｜日期：2026-10-06

---

## 一、三分钟快速上手

### 1.1 环境要求

| 项目 | 要求 | 说明 |
|------|------|------|
| Python | ≥ 3.9 | 开发环境 3.13 |
| 操作系统 | Windows / macOS / Linux | 跨平台 |
| LaTeX | **无需安装** | 项目自带 `tools/tectonic.exe` |

### 1.2 安装

```bash
git clone https://github.com/07Meteorain/AI.git
cd AI/C4C_交付/Meteorain_C4C_作业自动求解与排版

# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 1.3 运行

```bash
# 最简：跑示例作业（不需要 API Key）
python scripts/pipeline.py examples/homework_linear_algebra.md output/

# 完整：真实作业 + 编译 PDF
python scripts/pipeline.py my_homework.pdf out/ \
    --compile \
    --course "MATH 221 Linear Algebra" \
    --student "你的名字" \
    --title "Homework 6 — Solutions"
```

**没有 API Key 也能跑通全流程**——流水线会自动降级到
SymPy + 概念模板，覆盖本项目示例作业的 100%。

---

## 二、命令参考

### 2.1 全部参数

```
python scripts/pipeline.py <输入文件> <输出目录> [选项]

输入格式：
  .md .txt          Markdown / 纯文本
  .tex              LaTeX（反向转Markdown）
  .pdf              PDF（文本型：pdfplumber / pypdf）
  .docx             Word（含OMML 公式提取）
  .png .jpg .jpeg   图片（OCR：国产VL / Tesseract）

输出：
  1_ingested.json   Stage 1 摄入结果
  2_parsed.json     Stage 2 结构化题目
  3_solutions.json  Stage 3 解答+ 验证标签
  homework.tex      Stage 4 LaTeX 源文件
  homework.pdf      Stage 5 编译产物（需 --compile）
  figures/*.pdf     matplotlib 自动生成的函数图

选项：
  --compile         编译 PDF
  --course NAME     课程名称（默认 Mathematics）
  --student NAME    学生姓名（默认 Student）
  --title TITLE     文档标题（默认 Homework Solutions）
  --provider NAME   国产模型：qwen | kimi | deepseek | claude
  --model NAME      指定模型名（默认用provider 推荐值）
  --offline         离线模式，不调用 LLM API
  --no-llm          完全禁用 LLM（纯 SymPy）
  --no-verify关闭答案验证
  --verbose         详细输出（含每题路由理由）
```

### 2.2 常用场景

```bash
# 场景1：中文作业，自动切 xelatex +中文字体
python scripts/pipeline.py 中文作业.md out/ \
    --compile --course "高等数学" --student "张三"

# 场景 2：Word 作业
python scripts/pipeline.py 作业.docx out/ --compile

# 场景 3：拍照作业（需配 DASHSCOPE_API_KEY 走国产VL）
export DASHSCOPE_API_KEY=sk-xxx
python scripts/pipeline.py 作业.jpg out/ --compile

# 场景 4：完全离线（无网/无 Key 的机器）
python scripts/pipeline.py homework.pdf out/ --offline

# 场景 5：只看解法，不要 PDF（快速调试）
python scripts/pipeline.py homework.md out/ --no-llm --verbose
```

---

## 三、配置国产模型

### 3.1 支持的模型

| provider | 环境变量 | 获取地址 |
|----------|---------|---------|
| `qwen`（默认） | `DASHSCOPE_API_KEY` | https://dashscope.aliyun.com/ |
| `kimi` | `MOONSHOT_API_KEY` | https://platform.moonshot.cn/ |
| `deepseek` | `DEEPSEEK_API_KEY` | https://platform.deepseek.com/ |
| `claude`（对照组） | `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |

### 3.2 配置方式

**方式 A：环境变量（推荐，适合 CI）**
```bash
export DASHSCOPE_API_KEY=sk-xxxxxxxx
```

**方式 B：配置文件**
编辑 `config/config.yaml`：
```yaml
solver:
  provider: "kimi"
  model: "moonshot-v1-32k"
  temperature: 0.1
```

**方式 C：命令行覆盖**
```bash
python scripts/pipeline.py hw.md out/ --provider kimi --model kimi-k2-0905-preview
```

### 3.3 优先级

```
默认值 < config.yaml < config.json < 环境变量 < 命令行参数
```

### 3.4 检查配置是否生效

```bash
python scripts/llm_engine.py
```

输出示例：
```json
{
  "provider": "qwen",
  "display": "通义千问Qwen3.6（阿里云百炼）",
  "api_key_present": true,
  "ready": true,
  "fallback": null
}
```

---

## 四、支持的学科

### 4.1 已实现域

#### 线性代数（`domain_skills/linear_algebra.yaml`）

| 操作 | 说明 |
|------|------|
| 行列式 | `det(A)` |
| 逆矩阵 | 自动验证 $AA^{-1}=I$；$\det=0$ 时明确报「奇异」 |
| 特征值 | 含重数标注；检查重数和是否等于阶数 |
| 特征向量 | 每个特征值对应的特征空间基 |
| 对角化 | $A=PDP^{-1}$；验证重构；说明不可对角化的条件 |
| SVD | 奇异值 + 对角阵 Σ |
| 秩 / 迹 / 转置 | — |
| RREF | 行最简形 + 主元列 |
| 零空间 / 列空间 | 给基向量 |
| 正交性判定 | 两两内积 + 结论 |
| Gram-Schmidt | 正交化 / 归一化（标准正交） |
| 线性方程组 | $Ax=b$；验证残差 |

#### 微分方程

| 类型 | 说明 |
|------|------|
| 一阶线性（常系数） | 含初值条件，自动解任意常数 |
| 一阶齐次 | — |
| 可分离变量 | — |
| 二阶 / 高阶常系数 | 特征方程法 |
| **验证型** | 「验证 $y=\dots$ 是方程的解」——代入算残差 |

支持 LaTeX 记号：`y'`、`y''`、`\frac{dy}{dx}`、`\dfrac{dy}{dx}`、`\frac{d^2y}{dx^2}`

#### 大学物理

| 类别 | 题型 | 输出 |
|------|------|------|
| 力学 | 牛顿第二定律（$F=ma$ / $a=F/m$） | 带单位 + 量纲核对 |
| 力学 | 自由落体（$v=gt$、$h=\frac12gt^2$） | 带单位 |
| 力学 | 动能 $K=\frac12mv^2$ | 带单位 |
| 力学 | 重力势能 $U=mgh$ | 带单位 |
| 电磁 | 库仑定律 $F=kq_1q_2/r^2$ | 带单位 |
| 电磁 | 欧姆定律 $I=V/R$ | 带单位 |
| 电磁 | 电场强度 $E=F/q$ | 带单位 |
| 电磁 | 点电荷场强 $E=kq/r^2$ | 带单位 |
| 热学 | 理想气体 $PV=nRT$ | 带单位 |

**内置常量**：$g$、$G$、$h$、$\hbar$、$c$、$e$、$\varepsilon_0$、$\mu_0$、
$k_e$（库仑常量）、$k_B$、$m_e$、$m_p$、$\sigma$

#### 微积分（继承 starter kit）

极限、ε-δ 记号、ε-δ 计算（构造 $\delta=\min\{1,\varepsilon/C\}$）、
切线方程、水平切线、夹逼定理、连续性、L'Hôpital、IVT等概念题。

### 4.2 未实现域

概率统计、数值方法、信号与系统、电路分析、复变函数。
这些题会明确报告「未求解」并转交 LLM，不会给出错误答案。

---

## 五、扩展：加一个新学科

以「复变函数」为例，三步：

### 步骤 1：定义领域本体

新建 `domain_skills/complex_analysis.yaml`：

```yaml
domain: complex_analysis
version: "1.0"

concepts:
  - id: analytic_function
    type: concept
    name: "解析函数"
    formal: "在开区域内可导且导数连续"
    keywords: [analytic, holomorphic, 解析]

solution_methods:
  - id: residue_theorem
    type: solution_method
    concept: analytic_function
    name: "留数定理"
    applies_when: "计算闭合曲线积分"
    tool: sympy
    solver_template: complex_solvers.solve_residue

classification_rules:
  - priority: 100
    pattern:
      text_contains: ["residue", "留数"]
    maps_to: analytic_function
    solver: residue_theorem
```

### 步骤 2：实现求解器

在 `scripts/domain_solvers.py` 里加函数：

```python
def solve_residue(problem: dict) -> dict:
    """复变函数：留数定理。"""
    # ... 解析题目、计算、构造 steps
    return _sol(problem, steps, latex(result), "sympy_residue")
```

### 步骤 3：注册路由

在 `scripts/solve.py::solve_sympy()` 里加分支：

```python
if re.search(r"留数|residue", text_l):
    return solve_residue(problem)
```

在 `scripts/solve.py::decide_route()` 里加判定（**放在抽象函数检测之前**）：

```python
if re.search(r"留数|residue", text_l):
    return "sympy", "复变函数题，符号计算可解"
```

### 步骤 4：写测试

在 `tests/test_domain_solvers.py` 加用例，跑：

```bash
python tests/test_domain_solvers.py
python tests/benchmark.py --no-llm
```

---

## 六、答案验证怎么读

生成的 PDF 里，每题答案下方有验证徽章：

| 徽章 | 含义 |
|------|------|
| 🟢 `✓ 已验证 3/3 项检验通过` | 形式检查 + 恒等式 + 形状，全部通过 |
| 🟠 `⚠ 验证存疑` | 有检验未通过，**建议人工复核** |
| 🟡 `未求解` | 求解器不会，明确报告而非编答案 |

**看到 ⚠ 请务必复核**——它意味着机器自己没把握。
比如「特征值验证未通过」可能是特征值算错了，也可能是
$\det(A-\lambda I)$ 的数值阈值太严，可以按题目具体判断。

查看详细验证记录：

```bash
python -c "
import json
for s in json.load(open('out/3_solutions.json', encoding='utf-8')):
    v = s.get('verification', {})
    print(s['problem_id'], v.get('overall'))
    for c in v.get('checks', []):
        print('   ', c['method'], c.get('passed'), c.get('issue') or c.get('note', ''))
"
```

---

## 七、常见问题

### Q1: 提示「未找到 LaTeX 编译器」

项目自带 `tools/tectonic.exe`，正常情况下会自动发现。
如果仍失败，检查：

```bash
# 确认文件在位
ls tools/tectonic.exe

# 手动指定 PATH（Windows Git Bash）
export PATH="$PWD/tools:$PATH"

# 或装系统级 LaTeX
#   MiKTeX: https://miktex.org/download
#   TeX Live: https://tug.org/texlive/
```

### Q2: 中文显示成方框

说明系统缺中文字体。`render_latex.py` 会自动探测，
若都缺失会给出提示。手动安装任一即可：

- **Noto Sans CJK SC**（开源，跨平台）：https://fonts.google.com/noto-cjk
- Windows 自带：微软雅黑 / 宋体 / 黑体
- macOS 自带：苹方 / 宋体

### Q3: OCR 识别公式效果差

数学公式的 OCR 准确率天然有限。建议：
1. 优先用国产 VL（`DASHSCOPE_API_KEY`）而非 Tesseract
2. 拍清楚、拍正、光线均匀
3. 复杂公式建议手动输入 Markdown

### Q4: 求解率上不去 / 某些题一直「未求解」

这是**设计如此**。流水线宁可说不会，也不编答案。

如果确定要处理这类题，两条路：
1. **加概念模板**（适合有固定答案的题目）
2. **配置 LLM API Key**（适合需要推理的题目）

### Q5: 想关掉验证

```bash
python scripts/pipeline.py hw.md out/ --no-verify
```

但不建议——验证是发现 bug 的主要手段
（本项目的两个严重错误都是验证模块抓出来的）。

---

## 八、开发者接口

### 8.1 作为库调用

```python
import sys
sys.path.insert(0, 'scripts')

from ingest import ingest
from parse_problems import parse_problems
from solve import solve_all
from render_latex import render_document, compile_pdf

# 摄入 + 解析
problems = parse_problems(ingest('homework.md'))

# 求解（可传自定义 LLM 引擎）
from llm_engine import LLMSolver
llm = LLMSolver(provider='qwen')
solutions = solve_all(problems, llm=llm, verify=True, verbose=False)

# 渲染
tex, cjk = render_document(solutions, course='Math', student='Me')
ok, info = compile_pdf('out/homework.tex', 'out', cjk=cjk)
```

### 8.2 关键数据��构

```python
# Problem（Stage 2 输出）
{
    "id": "P3",
    "text": "Find the eigenvalues of $A = ...$",
    "math_expressions": [{"type": "display", "latex": "..."}],
    "type": "matrix",              # 题型分类
    "sub_problems": [{"id": "a", "text": "...", "math_expressions": [...]}],
}

# Solution（Stage 3 输出）
{
    "problem_id": "P3",
    "solved": True,
    "steps": ["解析方程：...", "验证：..."],
    "answer_latex": "3, 1",
    "solver": "sympy_eigenvalues",
    "verification": {
        "overall": "pass",         # pass | fail | skipped
        "n_checks": 2, "n_passed": 2, "n_failed": 0,
        "checks": [{"method": "cross_check_eigen", "passed": True, ...}],
    },
}
```

### 8.3 自定义求解器

```python
# scripts/domain_solvers.py
def solve_my_topic(problem: dict) -> dict:
    steps = ["第一步：..."]
    return {
        "problem_id": problem["id"],
        "problem_text": problem.get("text", ""),
        "solved": True,
        "steps": steps,
        "answer_latex": r"\frac{1}{2}",
        "solver": "my_topic",
        "sub_solutions": [],
    }
```

---

## 九、项目结构

```
Meteorain_C4C_作业自动求解与排版/
├── SKILL.md                    技能主指令（Agent 触发用）
├── README.md                   快速上手
├── requirements.txt            依赖清单（分三级）
│
├── scripts/
│   ├── pipeline.py             ★ 一键编排（入口）
│   ├── ingest.py               Stage 1 摄入（5 种格式）
│   ├── parse_problems.py       Stage 2 解析 + 分类
│   ├── solve.py                Stage 3 路由 + 求解
│   ├── domain_solvers.py       线代/ODE/物理求解器
│   ├── verify.py               四层答案验证
│   ├── render_latex.py         Stage 4/5 排版 + 编译
│   ├── llm_engine.py           国产模型引擎
│   └── config_loader.py        配置加载
│
├── domain_skills/              领域本体（T-box）
│   ├── linear_algebra.yaml
│   └── calculus_limits.yaml
│
├── tests/
│   ├── test_domain_solvers.py  27 项单元测试
│   └── benchmark.py            基准测试 + 基线对比
│
├── examples/                   示例作业
│   ├── homework_linear_algebra.md
│   └── homework_physics_ode.md
│
├── config/config.yaml          默认配置
├── tools/tectonic.exe          内置 LaTeX 引擎
└── output/                     运行产物
```

---

## 十、许可与致谢

- **starter kit**：`c4c-homework-solver-starter`（Claude Code 上验证的微积分极限求解器）
- **外部库**：SymPy、pdfplumber、python-docx、matplotlib、PyYAML
- **LaTeX 引擎**：[Tectonic](https://tectonic-typesetting.github.io/)，MIT License
- **领域本体蒸馏来源**：Strang《Linear Algebra》、Stewart《Calculus》、Berkeley Math 1A 课程材料