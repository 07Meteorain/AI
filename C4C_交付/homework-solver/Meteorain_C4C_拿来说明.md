# Meteorain_C4C_拿来说明.md

> 从 starter kit 拿了什么、用了哪些库、Claude 版与国产模型版的差异
> 作者：Meteorain｜日期：2026-10-06

---

## 一、拿了什么（一句话）

**拿了 starter kit 的骨架（5 阶段流水线 + T-box 本体思想 + LaTeX 模板骨架），
换了里面的脑子（求解器全重写）、加了国产模型引擎、加了答案验证、
并把「域外40%」扩展到「100%」。**

---

## 二、逐项对照：哪些直接拿了，哪些改了，哪些全新

### 2.1 直接拿来（未改动或仅微调）

| 文件 | 拿的方式 | 说明 |
|------|---------|------|
| `scripts/parse_problems.py` | **整文件复制 + 局部修改** | 题号/子题/公式提取逻辑原样保留；只改了 `classify_problem()` 加结构信号优先判定 |
| `domain_skills/calculus_limits.yaml` | 完整继承 | 极限域本体（T-box）原样保留，本项目新增第二个域与之共存 |
| `test_cases/test1_*.md`、`test2_*.md` | 直接作为回归测试集 | Berkeley Math 1A 真实试卷，用作与 Claude 基线对比的标尺 |
| `examples/sample_homework.md` | 作为示例保留 | starter kit 的示例作业 |
| `oracles/`（5 份知识蒸馏文档） | **作为概念模板的知识来源** | 见 2.3 |

**为什么保留 `parse_problems.py` 的解析逻辑**：
它的题号识别（`Problem N` / `题 N` / `N.` / `N)` / `Q.N` / `Exercise N`）
和子题切分已经过 Berkeley 真实试卷验证，重写没有意义。
我只改了**题型分类**那一段——原因见 3.1。

### 2.2 改了（理解后重写）

| 模块 | starter kit 现状 | 我的改动 | 为什么 |
|------|-----------------|---------|-------|
| `ingest.py` | 4 个函数直接 `raise NotImplementedError` | **全部实现**：pdfplumber + pypdf 双路、python-docx（含 OMML 公式提取）、OCR（国产 VL + Tesseract），**新增 `.tex` 反向摄入** | CHALLENGE.md Level 2 硬性要求；`.tex` 是我加的，起因是我需要自己写的作业文件能被流水线读 |
| `solve.py` | 微积分极限求解 | **完全重写**：新增路由决策层、`decide_route()`、概念模板库、ε-δ 计算、几何极限；原有限极限逻辑保留并增强 | 极限域只是起点，Level 2/3 要求扩展学科 |
| `render_latex.py` | 基础模板 + `compile_pdf` 脚手架 | **重写**：中英文自动切引擎、CJK 字体动态探测、验证徽章内嵌、matplotlib 作图、多引擎探测降级 | starter kit 的 PDF 编译是「需要本机装 LaTeX」的脚手架；challenge 要求「必须生成可提交的 PDF」 |
| `pipeline.py` | 编排器 | 增强：LLM 引擎自检、题型分布统计、路由理由输出、编译结果回传 | 增加可观测性 |

### 2.3 全新写的（starter kit 完全没有）

| 模块 | 行数量级 | 作用 |
|------|---------|------|
| `scripts/llm_engine.py` | ~400 | **国产模型引擎**（迁移任务的核心） |
| `scripts/verify.py` | ~300 | **四层答案验证** |
| `scripts/domain_solvers.py` | ~1100 | 线代/ODE/物理求解器 |
| `scripts/config_loader.py` | ~130 | 配置系统（Level 4 要求） |
| `domain_skills/linear_algebra.yaml` | ~400 | 线性代数领域本体 |
| `tests/test_domain_solvers.py` | ~200 | 27 项单元测试 |
| `tests/benchmark.py` | ~200 | 基准测试 + 基线对比 |
| `tools/tectonic.exe` | 50MB | 内置 LaTeX 引擎 |

---

## 三、拿 starter kit 的 oracles 做了什么

starter kit 的 `oracles/` 目录有 5 份知识蒸馏文档（教材、学习指南、
教授指南、教学法指南、习题集）。**这是 starter kit 最有价值的部分**——
它把「一个函数怎么解」抽象成了「领域知识 + 求解方法」的分离结构。

我的用法：

### 3.1 极限域：直接继承 + 补充

`oracles/02_study_guide.md` 里的知识蒸馏成了代码里的概念模板：

| oracle 里的知识 | 落地为|
|-----------------|--------|
| Four Keywords 证明法（Given/Choose/Suppose/Check） | ε-δ 求解步骤模板 |
| ∞ 不是数 | `_match_conceptual_template()` 的 infinity 分支 |
| Squeeze Theorem | squeeze 分支 |
| L'Hôpital 前提条件 | lhopital 分支 |
| δ 不能依赖 x | δ 构造器的设计约束 |
| min-notation (δ = min{1, ε/C}) | `_find_delta()` 的实现 |

### 3.2 新增域：用同样的方法论蒸馏

线性代数的 `domain_skills/linear_algebra.yaml` 里的
`oracle_insight` 字段，记录的是我从 Strang 教材 + MIT 18.06 提炼的：
- det 是乘法同态而非加法同态
- 可逆 ⟺ det≠0 ⟺ 零空间仅含零向量
- 可对角化 ⟺ 每个特征值几何重数 = 代数重数
- Gram-Schmidt 输入可能是行向量组（m×n，m≠n）

**这些知识直接影响了代码结构**，见 4.2。

---

## 四、用了哪些外部库

### 4.1 必需依赖

| 库 | 版本 | 用途 | 与starter kit 的关系 |
|----|------|------|-------------------|
| **SymPy** | ≥1.12 | 符号计算内核 | 沿用。starter kit 就用它；但我用到的 API 远超它（`dsolve`、`orthogonalize`、`singular_values`、矩阵全套） |
| **PyYAML** | ≥6.0 | T-box 配置解析 | 沿用 |
| **tcolorbox**（LaTeX） | — | 解答步骤的彩色框 | **新增**，starter kit 用纯文本段落 |

### 4.2 新增依赖（starter kit 未用）

| 库 | 用途 | 为什么需要 |
|----|------|-----------|
| **pdfplumber** | PDF 文本提取 | Level 2 硬性要求 |
| **pypdf** | PDF 兜底提取 | pdfplumber 对某些 PDF 会提取为空，需要兜底 |
| **python-docx** | Word 摄入 | Level 2 硬性要求 |
| **Pillow** | 图像预处理 | OCR 前处理 |
| **pytesseract** | OCR 封装 | Level 2/3 要求 |
| **matplotlib** | 函数图生成 | Level 4「图形自动生成」 |
| **Tectonic** | LaTeX 编译 | 见 4.3 |

### 4.3 为什么选Tectonic（而不是要求用户装 TeX Live）

starter kit 的 `compile_pdf()` 只探测 `pdflatex` / `xelatex`，
两者都需要用户**预先安装 TeX Live 或 MiKTeX**（几百MB 到几GB）。

对评审场景这是致命的：对方机器上大概率没装，产物就只有 `.tex`。

Tectonic 的优势：
- **单文件、零依赖**——一个 50MB 的 exe，不装 TeX 发行版
- 自动下载所需宏包（首次约 200MB，之后走缓存）
- 内置 XeTeX 引擎，中文直接支持
- MIT License，可随项目分发

我把它放进 `tools/`，`detect_engines()` 会优先发现项目内置版本。

### 4.4 明确**没有**引入的库

| 库 | 为什么没引|
|----|---------|
| `pint` | 量纲分析本可以用它做成严格的量纲代数，但它依赖链较重（带来 numpy/pandas）。当前用启发式检查 + 显式量纲核对步骤，够用且轻量。**这是取舍，不是遗漏**。 |
| `scipy` | 数值方法（插值/积分/迭代）不在 Level 1-3 要求内，Level 4 再引入。 |
| `numpy` | matplotlib 会间接带入；暂不直接依赖。 |
| 任何 LLM SDK | 全部用 `urllib` 手写 HTTP 调用。理由：三家国产模型都是 OpenAI兼容协议，手写只需 30 行，且**不引入供应链风险**，也让读者看清请求/响应结构。 |

---

## 五、Claude 版 vs 国产模型版：逐项差异

这是 challenge 的核心问题。以下是**实测差异**（基于同一批题目）。

### 5.1 架构差异

| 维度 | starter kit（Claude Code） | 本项目（国产模型） |
|------|-------------------------|-----------------|
| **运行宿主** | Claude Code 主循环 | 独立 Python 进程，任何环境 |
| **推理调用方式** | 在对话里"问" Claude | `urllib` 直接 POST 到 `/chat/completions` |
| **模型切换** | 换 Claude 模型 | `--provider qwen/kimi/deepseek` |
| **结构化输出** | 人工在对话里整理成 JSON | `response_format: json_object` + 三层 JSON 抽取降级 |
| **失败处理** | 人工重试 | 异常捕获 → 缓存 → 规则兜底 |
| **调用审计** | 靠翻对话记录 | `llm_trace.jsonl`（时间戳 + prompt SHA + 响应摘要） |
| **成本控制** | 不可观测 | token 统计 + prompt 哈希缓存 |
| **无网/无 Key** | 不可用 | 自动降级，流水线仍能端到端跑完 |

### 5.2 能力差异（实测）

| 测试集 | Claude 版（starter kit 官方数据） | 本项目（SymPy+模板，无 LLM） |
|--------|------------------------------|-------------------------------|
| Berkeley WS3 | 8/8 = 100% | **8/8 = 100%** |
| Berkeley WS4 | 9/10 = 90% | **10/10 = 100%** |
| 核心域合计 | 17/18 = **94.4%** | 18/18 = **100%** |
| 线性代数（12 题） | 域外 | **12/12 = 100%** |
| 物理+ODE（14 题） | 域外 | **14/14 = 100%** |
| **合计** | — | **44/44 = 100%** |

**注意这个对比的不对称性**：
本项目的 100% 是在**无 LLM** 的情况下达到的（纯 SymPy + 概念模板）。
LLM 在这里是**兜底而非主力**。

这恰恰说明了一件事：
> **能确定性计算的问题，不要交给 LLM。**
> starter kit 的 40% 域外表现，不是因为「Claude 不行」，
> 而是因为 starter kit 里那些域的求解器**根本没实现**
> （`solve_matrix` / `solve_ode` 是直接 `raise` 的空壳）。

### 5.3 迁移带来的真实收获

如果不迁移到国产模型、只是继续用 Claude，会漏掉什么？

**会漏掉「模型不可用时的可复现性」。**
本项目的 44/44 全部来自 SymPy，不依赖任何 API。
这意味着：换模型不改变结果，API 挂了也不影响，
评审者clone 下来就能验证每一个数字。

**会漏掉「确定性 vs 概率性」的显式区分。**
starter kit 里「Claude 算出答案」是一个黑盒；
本项目里每个答案都标了来源：
- `sympy_eigenvalues` → 确定性，可复现
- `conceptual_template` → 确定性，来自 oracle 蒸馏
- `qwen:qwen3-max` → 概率性，需要人复核

这个区分对学生和评审者都很重要。

---

## 六、迁移中发现的 Claude 版设计的三个问题

我在理解 starter kit 的过程中发现了三个问题（已在我的版本中修正），
它们不一定全是 starter kit 的bug，有些是**设计取舍在扩展后暴露的局限**。

### 6.1 问题1：领域求解器是空壳，且失败后行为未定义

```python
# starter kit 的 solve.py
def solve_matrix(problem):
    return _unsolved(problem, "矩阵解析需要扩展（学生扩展点）。")
```

三个问题：
1. 空壳——但**扩了之后呢？** 没定义
2. 我的第一版写成 `if r["solved"]: return r`，失败就 fall through
3. fall through 到通用求解器 → **静默给出错误答案**

**修正**：领域求解器一旦命中，要么给答案，要么明确报未解，
绝不退回通用求解器。这条原则写进了代码注释，因为它反直觉。

### 6.2 问题 2：验证模块完全缺失

starter kit 算完就输出，从不回头检查。
challenge 的 rubric 里「输出可核验」占重要权重——
**没有验证模块，「正确率」就是个无法核验的数字**。

我加了四层验证，结果**第一版就有两个严重 bug 被它抓出来**
（SymPy 静默误算、分数被解析成乘法）。详见验证报告第四节。

### 6.3 问题 3：PDF 编译是不可用的脚手架

```python
# starter kit 的 render_latex.py
print("  ⚠️ 未找到 LaTeX 编译器（pdflatex/xelatex）。")
print("  安装提示: macOS: brew install --cask mactex-no-gui ...")
```

challenge 要求「生成可提交的 PDF」。
如果对方没装 TeX，交付物就退化成一堆 `.tex`。

**修正**：内置 tectonic，零安装依赖。

---

## 七、独立判断与取舍

除了「拿」和「改」，有几处是我**自己的判断**，值得说明。

### 7.1 判断：优先确定性，而非优先 LLM 能力

直觉上「用更强的模型」是进步方向，但我的实测结论相反：
**44/44 的题目，SymPy 全都能确定性求解。**

所以我把路由设计成「先用 SymPy，LLM 兜底」，
而不是「LLM 为主，SymPy 辅助」。

代价：需要为每个域写求解器，前期投入大。
收益：结果可复现、零幻觉、成本为零、离线可用。

### 7.2 判断：宁可说不会，不编答案

starter kit 未解的题会写「需要扩展（学生扩展点）」——这是诚实的。
但我第一版的 fall through 逻辑破坏了这一点。

所以我给自己定了条硬规则：
> **不确定就说不确定。宁可 solved=false，也不要编造答案。**

这条规则让「未求解」从失败变成了**负责任的行为**。

### 7.3 判断：验证只打标签，不改答案

一个诱人的设计是「验证失败就自动修正答案」。
我**没有这么做**，因为：
- 自动修正会掩盖求解器本身的缺陷
- 「自动修对了」和「本来就算对了」在报告里无法区分
- 打标签能把问题暴露在报告里，这对评审者更有价值

### 7.4 判断：CJK 字体动态探测而非硬编码

硬编码 Noto CJK 在只装了雅黑的 Windows 上直接编译失败。
加上 `\IfFontExistsTF` 逐个探测后，换机器也能编译。
**代价是导言区多了几行代码，收益是跨机器可用。**

---

## 八、总结：一张表看清边界

|类别 | 内容 | 占比 |
|------|------|------|
| **直接拿来** | parse_problems 的解析逻辑、calculus_limits.yaml、oracles 知识、Berkeley 测试集 | ~15% |
| **理解后重写** | solve.py、render_latex.py、pipeline.py、ingest.py 的空壳 | ~30% |
| **全新实现** | llm_engine、verify、domain_solvers、config_loader、线性代数本体、测试、tectonic | ~55% |
| **外部库** | SymPy（沿用）+ pdfplumber/pypdf/python-docx/matplotlib/Pillow/pytesseract（新增）+ Tectonic | — |

**一句话**：
> 拿了 starter kit 的**架构思想**（领域知识与求解器分离、5阶段流水线、T-box 本体），
> 重写了它的**求解能力**（3 个新学科域），
> 补上了它**缺的两块**（国产模型引擎、答案验证），
> 并修掉了它**未定义的行为**（失败后怎么办）。