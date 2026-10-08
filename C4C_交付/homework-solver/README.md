# C4C 作业自动求解与排版

> 从作业文件到可提交 PDF，一条命令搞定。
> **跑在国产大模型上**（Qwen 3.6 / Kimi 2.5 / DeepSeek），答案自带验证标签。

```
输入（md / pdf / docx / tex / 图片）
  →摄入 → 解析 → 求解（SymPy + 国产 LLM 混合路由）→ 验证 → LaTeX → PDF
```

---

## 效果

| 测试集 | 本项目 | Claude 基线 |
|--------|--------|------------|
| Berkeley Math 1A WS3（切线 & ε-δ） | **8/8** = 100% | 8/8 = 100% |
| Berkeley Math 1A WS4（极限） | **10/10** = 100% | 9/10 = 90% |
| **核心域合计** | **18/18 = 100%** | 17/18 = 94.4% |
| 线性代数（新增） | **12/12** = 100% | 域外 |
| 物理 + ODE（新增） | **14/14** = 100% | 域外（40%） |
| **总计** | **44/44** | — |

**每个答案都经过四层验证**，PDF 里直接标`✓ 已验证` / `⚠ 验证存疑`。

---

## 快速上手

```bash
pip install -r requirements.txt

# 跑示例（不需要 API Key）
python scripts/pipeline.py examples/homework_linear_algebra.md output/

# 真实作业 + 编译 PDF
python scripts/pipeline.py my_homework.pdf out/ \
    --compile --course "MATH 221" --student "你的名字"
```

**无需安装 LaTeX**——项目自带 `tools/tectonic.exe`。

---

## 五个 Stage

| Stage | 输入 → 输出 | 能力 |
|-------|-----------|------|
| **1 摄入** | 文件 → 结构化文本 | md / tex / pdf / docx / 图片 OCR |
| **2 解析** | 文本 → 题目列表 | 题号、子题、公式、题型分类 |
| **3 求解** | 题目 → 解答 + 验证 | 混合路由：SymPy 优先，国产 LLM 兜底 |
| **4 排版** | 解答 → `.tex` | 中英文自适应、作图、验证徽章 |
| **5 编译** | `.tex` → `.pdf` | pdflatex / xelatex / tectonic 自动降级 |

---

## 路由策略：SymPy 还是 LLM？

这是本项目的核心设计。

```
① 结构性信号（最可靠）
   矩阵 / ODE / 物理常量 →专用求解器
② 概念模板库命中→ 模板求解器（确定性，零幻觉）
③ ε-δ 计算题            → ε-δ 构造器
④ 才考虑 LLM
   抽象函数 / 证明 / 纯文字 → 国产 LLM
⑤ 兜底：SymPy 失败 → LLM 二次机会 → 规则兜底
```

**为什么这样排优先级？** 三个真实的坑：
1. 「prove/verify」等动词会抢走本质是计算题的题目
2. 抽象函数检测会误伤「给了具体 f(x)定义」的题
3. 题干的信息量可能远小于子题（AP1 全部内容在子题里）

**一条硬规则**：领域求解器一旦命中，
**要么给答案，要么明确报未解，绝不退回通用求解器**。

> 早期版本没定义这条，导致「求库仑力」的题
> 从题面抓到数字 3.0 当答案输出——
> 看起来完全正常，实际完全错误。

---

## 支持的学科

**线性代数** — 行列式、逆矩阵、特征值/向量、对角化、SVD、秩、迹、转置、
RREF、零空间、列空间、正交判定、Gram-Schmidt、线性方程组

**微分方程** — 一阶线性（含初值）、一阶齐次、可分离变量、
二阶/高阶常系数、验证型（代入求残差）

**大学物理** — 牛顿第二定律、自由落体、动能、重力势能、
库仑定律、欧姆定律、电场强度、点电荷场强、理想气体
（全部输出带单位 + 量纲核对）

**微积分** — 极限、ε-δ 记号、ε-δ 计算（δ=min{1, ε/C}）、
切线、夹逼定理、L'Hôpital、IVT 等概念题

---

## 答案验证

```
L1 形式检查    空答案 / NaN / zoo / 量级合理性
L2 数值代入    答案代回原方程，残差 < 1e-9
L3 交叉检验    符号算法 vs 数值逼近，两条独立路径互验
L4 量纲/形状   物理量量纲、矩阵阶数
```

**验证只打标签，不改答案。**

> 这个设计不是装饰——它抓到了两个「求解率 100% 但答案全错」的 bug：
> 1. `\frac{a}{b}` 被解析成 `a*b`（AP1 答案 -11520，正确 -20）
> 2. SymPy 带 `integer=True` 时 `limit(n·sin(2π/n)/2, n, oo)` 返回 0
>    （正确是 π，**且不报错**）

---

## 配置国产模型

```bash
export DASHSCOPE_API_KEY=sk-xxx    # 通义千问（默认）
export MOONSHOT_API_KEY=sk-xxx     # Kimi
export DEEPSEEK_API_KEY=sk-xxx     # DeepSeek
```

或编辑 `config/config.yaml`，或用 `--provider kimi`。

**没有Key 也能跑**——自动降级到 SymPy + 概念模板，
示例作业的 44/44 全靠它。

---

## 测试

```bash
python tests/test_domain_solvers.py    # 27 项单元测试
python tests/benchmark.py --no-llm     # 基准测试 + 基线对比
```

---

## 项目结构

```
├── scripts/
│   ├── pipeline.py           ★ 一键编排入口
│   ├── ingest.py             Stage 1 摄入（5 种格式）
│   ├── parse_problems.py     Stage 2 解析 + 分类
│   ├── solve.py              Stage 3 路由 + 求解
│   ├── domain_solvers.py     线代 / ODE / 物理求解器
│   ├── verify.py             四层答案验证
│   ├── render_latex.py       Stage 4/5 排版 + 编译
│   ├── llm_engine.py         国产模型引擎
│   └── config_loader.py      配置加载
├── domain_skills/            领域本体（T-box）
├── tests/                    单元测试 + 基准测试
├── examples/                 示例作业
├── tools/tectonic.exe        内置 LaTeX 引擎
└── config/config.yaml        默认配置
```

---

## 文档

| 文档 | 内容 |
|------|------|
| `Meteorain_C4C_方案设计.md` | 架构、模型选型、路由决策 |
| `Meteorain_C4C_验证报告.md` | 逐题答案核对 + 与 Claude 基线对比 |
| `Meteorain_C4C_教学说明.md` | 安装、使用、扩展新学科 |
| `Meteorain_C4C_拿来说明.md` | 拿了什么、改了什么、库选型理由 |
| `Meteorain_C4C_AI日志.md` | 开发全过程 AI 使用记录 |
| `Meteorain_C4C_AAR复盘.md` | 复盘：做成了什么、没做成什么 |

---

## 致谢与来源

- **starter kit**：`c4c-homework-solver-starter`（Claude Code 上验证的极限域求解器）
- **外部库**：SymPy、pdfplumber、python-docx、matplotlib、PyYAML
- **LaTeX 引擎**：[Tectonic](https://tectonic-typesetting.github.io/)，MIT License
- **领域本体蒸馏来源**：Strang《Linear Algebra》、Stewart《Calculus》、
  Berkeley Math 1A 课程材料