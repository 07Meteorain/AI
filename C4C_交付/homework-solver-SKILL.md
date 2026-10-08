# Homework Auto-Solver & Formatter（作业自动求解与排版）

> Ontology-grounded, retrieval-augmented homework solving.
> 运行在**国产大模型**上：Qwen 3.6 / Kimi 2.5 / DeepSeek。

---

## Skill Invocation

**Triggers:**
「求解作业」「自动解题」「做这份 worksheet」「auto-solve homework」，
或用户提供数学/物理作业文件（.md / .pdf / .docx / .tex / 图片）并要求解答。

**Usage:**

```bash
SKILL_DIR="<本技能目录>"

# 基本用法
python "$SKILL_DIR/scripts/pipeline.py" <输入文件> <输出目录> [选项]

# 真实作业 + 编译 PDF
python "$SKILL_DIR/scripts/pipeline.py" homework.pdf out/ \
    --compile --course "MATH 221 Linear Algebra" --student "Meteorain"

# 中文作业（自动切 xelatex + 中文字体）
python "$SKILL_DIR/scripts/pipeline.py" 作业.docx out/ --compile --student "张三"

# 离线（无 API Key）
python "$SKILL_DIR/scripts/pipeline.py" homework.md out/ --offline
```

**Parameters:**

| 参数 | 默认 | 说明 |
|------|------|------|
| `input` | 必填 | 作业文件（.md/.pdf/.docx/.tex/图片） |
| `output_dir` | 必填 | 输出目录 |
| `--compile` | off | 编译 PDF |
| `--course` | "Mathematics" | 课程名称 |
| `--student` | "Student" | 学生姓名 |
| `--title` | "Homework Solutions" | 文档标题 |
| `--provider` | `qwen` | 国产模型：qwen / kimi / deepseek |
| `--model` | provider 默认 | 模型名 |
| `--offline` | off | 离线模式，不调 API |
| `--no-llm` | off | 禁用 LLM（纯 SymPy） |
| `--no-verify` | off | 关闭答案验证 |
| `--verbose` | off | 输出每题的路由理由 |

**Dependencies:**
`pip install -r requirements.txt`（SymPy + pdfplumber + python-docx + matplotlib）
PDF 编译**无需安装 LaTeX**——项目自带 `tools/tectonic.exe`。

---

## Output Files

| 文件 | 内容 |
|------|------|
| `1_ingested.json` | Stage 1 摄入结果（含分段边界） |
| `2_parsed.json` | Stage 2 结构化题目（含题型分类） |
| `3_solutions.json` | Stage 3 解答 + **验证标签** |
| `homework.tex` | Stage 4 LaTeX 源文件 |
| `homework.pdf` | Stage 5 编译产物（需 `--compile`） |
| `figures/*.pdf` | matplotlib 自动生成的函数图 |
| `llm_trace.jsonl` | LLM 调用审计轨迹 |

---

## Architecture

```
Input → Ingest → Parse + Classify → Solve（SymPy + LLM 混合路由）
      → Verify（四层）→ Render LaTeX → Compile PDF
```

### Solve 的路由逻辑

```
① 结构性信号（最可靠）
   \begin{pmatrix} → 矩阵求解器
   y' / dy/dx→ ODE 求解器
   物理常量关键词     → 物理求解器
② 概念模板库命中      → 模板求解器（确定性，零幻觉）
③ ε-δ 计算题         → ε-δ 构造器
④ 才考虑 LLM
   抽象函数 / 证明 / 纯文字 → 国产 LLM
⑤ 兜底：SymPy 失败 → LLM 二次机会 → RuleBasedFallback
```

**硬规则**：领域求解器一旦命中，**要么给答案，要么明确报未解**，
绝不退回通用求解器。（否则会从题面抓到数字当答案，静默给出错误结果。）

### 验证模块

| 层 | 方法 | 抓什么错 |
|----|------|---------|
| L1 | 形式检查 | 空答案、NaN、量级异常 |
| L2 | 数值代入 | 答案代回原方程对不上 |
| L3 | 交叉检验 | 符号算法 vs 数值逼近不一致 |
| L4 | 量纲/形状 | 物理量量纲、矩阵阶数 |

**验证只打标签，不改答案。**

---

## Domain Coverage

| 域 | 覆盖内容 |
|----|---------|
| **线性代数** | det / inv / 特征值 / 特征向量 / 对角化 / SVD / rank / trace / transpose / RREF / nullspace / colspace / 正交判定 / Gram-Schmidt / 线性方程组 |
| **微分方程** | 一阶线性（含初值）/ 一阶齐次 / 可分离变量 / 二阶高阶常系数 / 验证型（代入求残差） |
| **大学物理** | 牛顿定律 / 自由落体 / 动能 / 势能 / 库仑定律 / 欧姆定律 / 电场强度 / 理想气体（均带单位 + 量纲核对） |
| **微积分** | 极限 / ε-δ 记号 / ε-δ 计算 / 切线 / 水平切线 / 夹逼 / L'Hôpital / IVT 等概念题 |

LaTeX 记号支持：`y'`、`y''`、`\frac{dy}{dx}`、`\dfrac{dy}{dx}`、
`\frac{d^2y}{dx^2}`、`\begin{pmatrix}`、`\begin{cases}`。

---

## Test Results

```
单元测试   27/27 通过
基准测试   44/44 求解，0 验证告警

核心域（Berkeley Math 1A WS3-4）
  WS3   8/8  = 100%   （基线 100%）
  WS4  10/10 = 100%   （基线90%）
  合计 18/18 = 100%   （基线 94.4%）✅ 超过

扩展学科（starter kit 基线 40%）
  线性代数        12/12 = 100%
  物理 + ODE     14/14 = 100%
```

复现：
```bash
python tests/test_domain_solvers.py
python tests/benchmark.py --no-llm
```

---

## Extending: 加一个新学科

1. **`domain_skills/<domain>.yaml`** — 定义概念、求解方法、分类规则
   （参考 `linear_algebra.yaml` 的 `oracle_insight` 字段，
   把踩过的坑记进去）

2. **`scripts/domain_solvers.py`** — 实现求解器函数，返回
   `{solved, steps[], answer_latex, solver, sub_solutions[]}`

3. **`scripts/solve.py::solve_sympy()`** — 加路由分支
   ```python
   if re.search(r"留数|residue", text_l):
       return solve_residue(problem)
   ```

4. **`scripts/solve.py::decide_route()`** — 加判定
   **必须放在抽象函数检测之前**，否则会被 f(x) 抢走
   ```python
   if re.search(r"留数|residue", text_all):
       return "sympy", "复变函数题，符号计算可解"
   ```
   注意用 `text_all`（含子题文本），不是 `text_l`——
   很多题的信息只在子题里。

5. **`tests/test_domain_solvers.py`** — 加用例，跑测试 + benchmark

---

## Known Limitations

| 局限 | 现状 |
|------|------|
| LLM 未经真实 API 实测 | 本机无 Key，代码路径完整但未实测 |
| 量纲分析是启发式 | SymPy 无内置量纲系统；严格版需引入 pint |
| 数值方法未覆盖 | 无插值/数值积分/迭代法 |
| 概率统计未覆盖 | — |
| 中文题目解析 | 支持但未专门测试 |
| OCR 公式识别 | 准确率天然有限，建议优先用国产 VL |

**未覆盖的领域会明确报告「未求解」，不会给出错误答案。**

---

## Example Agent Interaction

```
User: 「这是我的线代作业，帮我做一下」
Agent: [运行 pipeline --compile]
       → "已解出 12/12 题，全部通过自动验证（7 页 PDF）。
          其中第 8 题 Gram-Schmidt 得到正交组，Q^TQ 为对角阵
          （非标准正交，如需单位长度请再归一化）。
          答案 PDF: [链接]"
```