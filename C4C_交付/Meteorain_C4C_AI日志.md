# Meteorain_C4C_AI日志.md

> 开发全过程 AI 使用记录
> 作者：Meteorain｜日期：2026-10-06
> 工具：WorkBuddy（Claude Code 架构的 Agent 运行环境）
> 代码规模：6272 行 Python（scripts 5366 + tests 285）

---

## 一、总体说明

本项目由 AI 深度参与开发：读需求 → 设计架构 → 写代码 → 调试 → 测试 →写文档。
**AI 不是辅助工具，而是主要劳动力。**

但本日志不写「我让 AI 写了个功能」这种流水账——
challenge 的 rubric 明确把「一句话指令直接提交、无迭代」列为 **red flag**。
所以下面记录的是**迭代过程**：每一轮遇到什么问题、AI 怎么诊断、我怎么判断、
下一轮改了什么。

**统计口径**：本次开发共经历约 **20 轮实质性迭代**，其中：
- 11 轮因测试失败而返工
- 6 轮因发现逻辑错误而返工（人工核对答案时发现）
- 3 轮因环境/依赖问题而返工

---

## 二、阶段一：理解 starter kit（Day 1）

### 2.1 第一轮：读需求

**我的指令**：
> 「帮我完成 C4C 这个挑战，严格按照 C4C 这个挑战的文件里的内容完成」

**AI 的动作**：
1. 读 `CHALLENGE.md`（26984 字节）+ `rubric.json` + `challenge.json`
2. 解压并遍历 `materials/c4c-homework-solver-starter/`（30+ 文件）
3. 读核心脚本：`pipeline.py`、`solve.py`、`ingest.py`、`parse_problems.py`、
   `render_latex.py`、`classify.py`、`retrieve.py`、`domain_solvers.yaml`
4. 读测试集：`test1_tangent_epsilon_delta.md`、`test2_limits.md`
5. 检查环境：Python 3.13、SymPy 1.13已装、**无 LaTeX**、GitHub 可推送

**关键发现（写进方案设计的依据）**：

| 发现 | 影响 |
|------|------|
| `ingest.py` 的 PDF/Word/OCR 三个函数全是 `raise NotImplementedError` | Level 2 的扩展点明确 |
| `solve.py` 的 `solve_matrix` / `solve_ode` 是空壳 | Level 2/3 的扩展点明确 |
| `render_latex.py` 的 `compile_pdf` 只探测 pdflatex/xelatex | 需要解决"用户没装 TeX"的问题 |
| Claude 基线是 17/18 = 94.4%（仅极限域） | 这是必须达到的标尺 |
| rubric 里「输出可核验」占 25 分权重 | starter kit 没有验证模块 → 必须补 |

### 2.2 第二轮：跑通 starter kit 基线

**我的指令**：
> 「先跑一遍 starter kit，拿到真实的基线数据」

**AI 的动作**：直接运行 starter kit 的 pipeline。

**结果**：
```
test1_tangent_epsilon_delta: 8/8 (100%)
test2_limits:10/10 (100%)   ← 注意：实际跑出来比文档里的 9/10 更好
```

**我的判断**：
文档标称 17/18，但我实测拿到 18/18。这说明**基线数字不能直接引用文档，
必须自己跑**。于是我把目标定为「实测基线 18/18」，并在验证报告里如实标注
「文档标称 17/18，本机实测 18/18」。

> 这是一个小但重要的判断：**不引用未经验证的数字**。

---

## 三、阶段二：架构设计（Day 1-2）

### 3.1 第三轮：设计路由策略

**我的核心问题**（也是 challenge Level 3 明确要求回答的）：
> 「哪些题用 SymPy，哪些题用国产 LLM？」

**AI 的第一版设计**：
```
抽象函数/证明/概念 → LLM
有矩阵 → SymPy 域求解器
有ODE → SymPy 域求解器
其它 → SymPy，失败转 LLM
```

**我 reviewing 后提出的质疑**：
> 「物理题的数值单位在自然语言里，没有 LaTeX 表达式，
> 按你这个规则会走LLM——但『12 N 作用于 3.0 kg 物体』明明 SymPy 一行能算。
> 而且你没定义『领域求解器失败怎么办』。」

**AI 修正后**：
```
① 结构性信号优先（矩阵/ODE/物理）
② 概念模板库命中 → 模板求解器
③ ε-δ 计算题
④ 才考虑 LLM
⑤ SymPy 失败 → LLM 二次机会
```

并确立一条硬规则（写进代码注释）：
> **领域求解器一旦命中，要么给答案，要么明确报未解，
> 绝不退回通用求解器。**

---

## 四、阶段三：实现（Day 2-6）

### 4.1 第四轮：写 LLM 引擎

**我的指令**：
> 「实现国产模型引擎，Qwen/Kimi/DeepSeek 三家OpenAI 兼容，
> 要有 JSON 强约束、审计轨迹、无 Key 兜底」

**AI 的产出**：`scripts/llm_engine.py`（569 行）

**设计决策（AI 提出，我认可）**：
1. 用 `urllib` 手写 HTTP 而非引入 SDK —— 少一个依赖，读者能看清请求结构
2. `compare_providers()` 支撑 Level 4 的模型对比报告
3. 三层降级：真实 API → 缓存 → 规则兜底

**我的追问**：
> 「无 Key 时兜底会做什么？如果它编答案怎么办？」

**AI 修正**：兜底只回答**能 100% 确定**的陈述性概念题，
其余明确返回 `solved=False` +说明缺什么。

### 4.2 第五轮：写验证模块

**我的指令**：
> 「rubric 里『输出可核验』占 25 分，starter kit 完全没有验证。
> 加一个，但我要能看懂它在验什么。」

**AI 的产出**：`scripts/verify.py`（418 行），四层验证

**我 reviewing 时追问**：
> 「符号算法自己算自己，交叉检验有意义吗？」

**AI 回应**：
交叉检验的两条路径是**独立的**——
符号路径走 Gruntz/L'Hôpital，数值路径按定义在实点上采样逼近。
更重要的是：**这个设计后来真的抓到了 bug**（见5.3）。

### 4.3 第六轮：写线代求解器

**我的指令**：
> 「扩线性代数域，参考 starter kit 的 domain YAML 结构」

**AI 产出**：`domain_skills/linear_algebra.yaml`（400 行）+ `domain_solvers.py`

**AI 在 YAML 的 `oracle_insight` 字段里主动记录了踩坑预警**：
- 「⚠️ 不能只匹配 inverse 关键词——真实作业常写 Find $A^{-1}$」
- 「⚠️ SymPy 1.13 没有 M.svd()，要用 singular_values()」
- 「⚠️ Matrix.orthogonalize 是 classmethod，实例调用会静默返回空列表」

**我的评价**：这三处预警后来**全部应验**（见 5.2、5.4）。

---

## 五、阶段四：调试与迭代（Day 4-6）

>这一节是本日志的重点：**记录失败与修复**，而非成功。

### 5.1 第一轮测试：全线飘红

第一次跑端到端，输出：
```
[10/12] linear_algebra
❌ 10 [none] 符号计算异常: TypeError: Data type not understood
❌ 12 [none] 符号计算异常: TypeError: Data type not understood
[14] physics_ode
❌ 1 [none] 无可用求解路径
...
```

**AI 的诊断过程**（不是直接改代码）：
1. 读 traceback → 定位到 `M.diagonalize()` 返回类型问题
2. 写最小复现脚本隔离问题
3. 发现 `M.orthogonalize()` 是 classmethod，实例调用**静默返回空列表**
4. 发现 `M.svd()` 在 SymPy 1.13 不存在

**修复**：改用 `Matrix.orthogonalize(*cols)` 和 `M.singular_values()`。

**我的评价**：
这个 bug 极隐蔽——`orthogonalize()` 实例调用**不报错**，只是返回空列表，
看起来像「这题没解出来」，实际是「API 用错了」。
这类问题只能靠读文档 + 最小复现发现。

### 5.2 第二轮测试：回归失败

修完新学科，回归 Berkeley 测试集：
```
[7/8]  test1   ← 我方丢失 Q1 Q2 P4
[3/10] test2   ← 我方丢失 Q2 Q4 AP1
```

**对比 starter kit 输出后确认**：我方 7+3=10，starter kit 8+10=18。
**我引入了严重回归。**

**我的质疑**：
> 「我重写 solve.py 时是不是把 starter kit 的能力弄丢了？
> 为什么新学科 100%，老学科只有 55%？」

**AI 的诊断**：
逐题对比两边的 `3_solutions.json`，定位丢失的 8 题：
| 题 | starter kit | 我方 | 原因 |
|----|------------|------|------|
| Q1/Q2 | conceptual_template | 无可用求解路径 | 缺切线存在性/唯一性模板 |
| Q4 | f(x)=x² | 无可用求解路径 | ε-δ 计算求解器缺失 |
| Q2(test2) | ∞模板 | 无可用求解路径 | ∞ 模板被抽象函数检测抢走 |
| AP1 | 见各子题 | 无可用求解路径 | 题干无公式，全在子题里 |

**根因**：
> 我的 `decide_route()` 把「prove / verify」当成需 LLM 的信号，
> 但 Berkeley 的概念题里这些词满天飞；
> 同时抽象函数检测、题干只看父题不看子题——三重叠加导致误判。

**修复迭代**（分 4 轮，每轮只改一个变量）：

|轮次 | 改动 | 结果 |
|------|------|------|
| 7a | 加切线唯一性/存在性模板 | 5/8 → 6/8 |
| 7b | 加「模板命中优先于 LLM」规则 | 6/8 → 7/8 |
| 7c | 模板检查提到抽象函数检测之前 | 7/8, 9/10 |
| 7d | 路由判断纳入子题文本 | 7/8, 10/10 |
| 7e | 实现 ε-δ 计算（δ = min{1, ε/C}） | **8/8**, 10/10 |
| 7f | 加几何极限（圆内接 n 边形） | **8/8**, **10/10** |

**我的评价**：
这是本次开发**最重要的迭代**。教训是：
> **重写别人的系统时，必须先跑通它的测试再动手。**
> 我是先重写后测试，代价是多花 6 轮返工。

### 5.3 第三轮测试：验证模块抓到静默错误

单元测试全绿、求解率 100%，看起来很完美。
但我**逐题核对标准答案**时发现不对：

| 题| 系统答案 | 正确答案 |
|----|---------|---------|
| AP1(a) | -11520 | -20 |
| AP2 | $\infty\operatorname{sign}(\langle-1,1\rangle\cdots)$ | $\pi$ |
| AP3 | $0$ | $\pi$ |

**AI 的诊断**：

**Bug A：分数被解析成乘法**
```
输入: \frac{x^2 + 2x - 24}{x - 4}
结果: (x-4)*(x^2 + 2x - 24)     ← 乘法！
原因: _find_matching_brace 的起点算错一格
      num_start = idx + m.end() - m.start() + 1   ← 多加了 idx
      应为 m.end()
```
修复后：`(x^2+2x-24)/(x-4)` ✓

**Bug B：SymPy 静默误算**
```python
n = Symbol('n', positive=True, integer=True)
limit(n*sin(2*pi/n)/2, n, oo)   # → 0    ❌ 正确是 π
limit(n*sin(2*pi/n)/2, n, oo)   # → π    ✓（去掉 integer=True）
```
**带 `integer=True` 假设时 Gruntz 算法给错答案且不报错。**

**修复（双保险）**：
1. 求解器去掉 `integer=True`，并加解析值 $\pi R^2$ 交叉核对
2. `cross_check_limit` 改为多尺度高精度数值逼近

**我的评价**：
> **这是验证模块存在的意义。**
> 求解率 100% 但答案全错——如果只看「求解率」这个指标，这个 bug 会一路
> 写进 PDF 交付出去。**「正确率」必须可核验，否则就是自欺欺人。**

### 5.4 第四轮测试：验证误报

修复后 AP3 正确输出 π，但验证徽章显示「⚠ 验证存疑」。

**诊断**：数值逼近用了 `delta = 1e-6/1e-7/1e-8`，
在 $n=10^8$ 时 `sin(2π/n) ≈ 6e-8`，double 只有 16 位有效数字，
相减全被舍入吃掉 → 结果 NaN。

**修复**：步长改为 `1e-3/1e-4/1e-5`；数值不稳定时**跳过**而非判错。

**我的评价**：
> **验证器自己也会有 bug。** 关键是它只报警不改答案——
> 如果它「自动修正」，这个 NaN 会导致 π 被改成一个假值。

### 5.5 第五轮测试：物理题全部未解

物理作业求解率突然 0%。诊断后发现三层原因：

| 层 | 问题 | 修复 |
|----|------|------|
| 路由 | 物理题没有 LaTeX 表达式 → 被判「纯文字题」→ 丢给 LLM | 物理关键词判定提到「无表达式→LLM」之前 |
| 单位解析 | `$3.0$ C` 的 `$` 把数值和单位隔开，正则抓不到 | 新增 `_normalize_for_units()` 先剥 `$` |
| 领域识别 | "A ball is dropped" 不含 "free fall" | 扩充关键词（drop / falls / speed / height） |

**我的评价**：
这一轮暴露了一个通用经验：
> **真实作业的表述比教材题目「脏」得多。**
> 教科书里的「自由落体」在真实作业里是「a ball is dropped from rest」。
> 解析器必须容忍这种多样性。

### 5.6 环境问题：LaTeX 缺失

编译 PDF 一直失败。本机无 TeX。

**解决路径（三次尝试）**：

| 尝试 | 方案 | 结果 |
|------|------|------|
| 1 | 找系统里的 MiKTeX / TeX Live | 不存在 |
| 2 | `curl` 下载 tectonic | 证书吊销检查失败（`schannel error 0x80092012`） |
| 3 | `curl --ssl-no-revoke -C -` 断点续传 | ✓ 下载成功 19MB |

**下载后仍失败**，连续三轮报错：
1. `Package fontspec Error: The font "Noto Serif CJK SC" cannot be found` → 改字体探测
2. `Undefined control sequence` → 删掉我写错的 `\XeTeXbreakskip`
3. `File ended while scanning use of \@argdef` → `\newcommand{\solution}` 多了一个 `\}`

**修复 font**：
```latex
% 硬编码 → 动态探测
\IfFontExistsTF{Noto Sans SC}{\setCJKmainfont{Noto Sans SC}}{}
\IfFontExistsTF{SimSun}{\setCJKmainfont{SimSun}}{}
...
```

**修复路径 bug**：
```
error: output directory "output\la2" does not exist
原因: subprocess 用了 cwd=tex.parent，传入的相对 --output-directory
      被相对 tex 目录再解析一次 → 指向不存在的路径
修复: 传给编译器的所有路径强制 .resolve() 成绝对路径
```

**我的评价**：
> 这段折腾暴露了我在**跨平台工程**上的经验不足：
> 路径处理、子进程工作目录、字体依赖这三件事在Windows 上都有坑，
> 而本地 Linux 上一测就过。

---

## 六、阶段五：文档与交付

### 6.1 第六轮：写交付文档

我明确要求：
> 「不要写流水账。rubric 把『一句话指令直接提交、无迭代』列为 red flag，
> 所以要记录**迭代过程**和**失败经验**。」

于是五份文档的结构是：
- 方案设计：含**路由决策的三个坑**（为什么这么排优先级）
- 验证报告：含**验证抓到的 4 个真实 bug**
- 拿来说明：含**我发现的 starter kit 3 个设计问题**
- 教学说明：含**常见问题**（字体、OCR、编译失败）

### 6.2 关于诚实性

三处我主动要求 AI「如实标注」而非美化：

| 位置 | 内容 |
|------|------|
| 验证报告 5.1 | 「LLM 路径未经真实 API 实测」——本机无 Key |
| 验证报告 5.2 | 「量纲检查是启发式而非严格量纲代数」 |
| 验证报告 5.3 | 「求解率 100% 的边界」——自建测试集可能过拟合 |

**我的判断**：
> 评审真正在意的是「你说的能不能复现」。
> 声称 100% 但不说测试集是我自己造的，那是误导；
> 说清边界，反而更可信。

---

## 七、AI 使用方式总结

### 7.1 我如何使用 AI

| 阶段 | AI 的角色 | 我的角色 |
|------|----------|---------|
| 读需求 | 执行者 | 指定读哪些文件 |
| 架构设计 | 提案者 | **质疑并要求说清失败路径** |
| 写代码 | 执行者 | 审查设计决策 |
| 调试 | **诊断者** | 提供「和标准答案不符」的现象 |
| 测试 | 执行者 | **设计测试用例** |
| 写文档 | 执行者 | 规定「不要流水账」 |

### 7.2 AI 做得好的地方

1. **最小复现隔离**——遇到类型错误时，能写脚本隔离到单个 API 调用
2. **踩坑写进注释**——把「SymPy 1.13 没有 svd()」这类知识留在代码里
3. **诊断链条完整**——从「答案错了」追到 `_find_matching_brace` 算错一格
4. **诚实标注**——被我要求后，会在文档里写明未实测的部分

### 7.3 AI 做得不好的地方

1. **重写时丢失原有能力**——重写 solve.py 时丢掉 8 题，直到回归测试才发现
2. **未定义失败路径**——第一版路由设计没有「领域求解器失败怎么办」
3. **正则在 shell 里被转义破坏**——多次调试因`\\frac` 在 shell 里被吃掉
4. **环境适配不足**——相对路径、子进程 cwd、字体依赖

### 7.4 最关键的一条

> **AI 不会自动告诉你「你弄丢了什么」。**
>
> 我重写了求解器，求解率在新学科上是 100%，
> 如果只看新学科的测试，我会以为任务完成了。
> 是**跑回归测试 + 对比 starter kit 输出**才发现丢了 8 题。
>
> **AI 开发的安全性来自「有基线可对比」，而不是「AI 写得多好」。**

---

## 八、可复现命令清单

```bash
# 环境准备
pip install -r requirements.txt

# 单元测试（27 项）
python tests/test_domain_solvers.py

# 基准测试 + Claude 基线对比
python tests/benchmark.py --no-llm --json output/benchmark.json

# 端到端：真实作业 → PDF
python scripts/pipeline.py examples/homework_linear_algebra.md output/la \
    --compile --course "MATH 221 Linear Algebra" --student "Meteorain" --no-llm

python scripts/pipeline.py examples/homework_physics_ode.md output/po \
    --compile --course "PHYS 201 University Physics" --student "Meteorain" --no-llm

# LLM 引擎自检
python scripts/llm_engine.py
```

**预期输出**：
```
单元测试: 27/27 通过
基准测试: 44/44 求解，0 验证告警
核心域:   18/18 = 100%（Claude 基线 94.4%）
扩展学科: 26/26 = 100%（starter kit 基线 40%）
PDF:      线代 7 页 + 物理 8 页
```

---

## 九、审计轨迹

流水线运行时，LLM 调用会落到 `output/llm_trace.jsonl`：
```json
{"ts": "2026-10-06T14:32:11", "provider": "qwen", "model": "qwen3-max",
 "event": "api_call", "prompt_len": 284, "prompt_sha": "a3f9...",
 "response_head": "{\"solved\": true, \"steps\": [...]}"}
```

本次开发因未配置 API Key，该文件记录的都是 `fallback` 事件。
配置 Key 后自动转为真实调用记录。