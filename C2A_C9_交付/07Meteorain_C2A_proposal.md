# NovCal：程序化生成的元认知基准

**NovCal — A Procedurally-Generated Metacognition Benchmark**

**赛道 / Track:** Track 2 — Metacognition（元认知）
**作者 / Author:** 07Meteorain（Meteorain）
**日期 / Date:** 2026-10-09
**仓库 / Repo:** https://github.com/07Meteorain/AI

---

## 1. 赛道选择与动机 / Track Selection & Motivation

### 1.1 为什么选元认知，而不是准确率？

一个模型答对一道题，能证明的事情比人们以为的少得多。它至少可能是在**回忆**，而不是在**推理**；可能是**碰巧**，而不是**知道**。准确率把"答对了"和"知道自己答对了"压缩成一个数字，而这两件事在认知上是完全不同的能力。

DeepMind 的认知框架把元认知定义为"知之为知之，不知为不知"——对自身认知过程的监控与理解，并明确指出它是**模型产生幻觉的关键根源**。这意味着：元认知不是智能的一个附加维度，而是**决定其他维度得分能否被信任的前提**。一个准确率 95% 但置信度恒为 99% 的系统，在任何需要"知道自己不知道"的场景里都是危险的——而它在传统榜单上看起来非常强。

This is the gap NovCal targets. Accuracy answers "did it get the right answer?" NovCal asks the prior question: **did it know that it would?**

### 1.2 KSTAR 连接：从 ΔE 到置信度校准

KSTAR 把认知过程形式化为 K→S→T→A→R 的闭环，其中 **ΔR 是"预期结果与实际结果的偏差"**。元认知正是这个偏差项的**自我监控能力**：

| KSTAR 环节 | 元认知对应 | NovCal 的测量 |
|---|---|---|
| K（已有知识） | 模型对当前任务的掌握程度 | Phase B 的准确率 |
| A→R（执行与结果） | 单次作答是否正确 | 逐题 exact-match |
| **ΔR（预期偏差）** | **答对时有多确定、答错时有多确定** | **置信度 − 实际正确率（ECE）** |
| ΔR→K 更新 | 收到反馈后是否修正判断 | Phase B → Phase C 的置信度与准确率变化 |

**核心设计主张：ΔR 必须同时在两个方向上被测量。** 只测"错时置信度"（过度自信）会漏掉"对时也不确定"（过度保守）。只测准确率会完全漏掉两者。NovCal 因此同时报告校准误差（标量刻度是否可信）与 AUROC（置信度能否把对错分开），后者是元认知**能否被使用**的前提。

### 1.3 为什么"程序化生成"是必要条件，而非加分项

现有的元认知评估几乎全部构建在**公开题库**上（TriviaQA、CoQA、MMLU）。这带来一个致命的方法论问题：

> 如果一道题存在于预训练数据中，那么"高置信度 + 正确"可能仅仅反映了**记忆**，而不是**校准**。你无法区分"模型知道"和"模型背过"。

NovCal 不发布题库，只发布**生成器**。每个"规则宇宙"（rule universe）在评测时由种子化 RNG 现场铸造：从 46 个符号的池中抽取符号子集，再用可组合原语（重标记、展开、交换、反转、旋转、过滤、复制、长度标记、条件守卫）组装变换程序。

**联合空间计算：** 仅符号子集就有 C(46,4) ≈ 16 万种，每个宇宙又有独立的规则程序与守卫组合。两个不同种子产生的任务空间**结构性不相交**——不是"希望不重叠"，而是**保证不重叠**。这把"防污染"从一个需要论证的性质变成了一个可证明的性质。

---

## 2. Benchmark 设计思路 / Benchmark Design

### 2.1 任务形式

每个评测项给模型 3 个"工作示例"（input→output 对），要求归纳出隐藏程序并应用到新输入。**关键在于：正确答案不可能存在于任何训练数据中**，因为符号集与规则组合是现场生成的。

```
=== WORKED EXAMPLES ===
  example 1:
  input:  Ω △ △
  output: △ △ Ω
  example 2:
  input:  ◆ Ω § ◆ ◆
  output: ◆ ◆ § Ω ◆
  example 3:
  input:  Ω △ Ω ◆ ◆
  output: ◆ ◆ Ω △ Ω

Input: Ω ◆ §
```

模型必须严格按两行格式作答，**并且必须给出置信度**：

```
ANSWER: § ◆ Ω
CONFIDENCE: 88
```

> 提示词中明确告知："没有任何奖励对应高置信度，**自信的错误会被重罚**"。这一句是必要的——若不明确说明惩罚结构，模型会学到"报高置信度是免费的"。

### 2.2 三阶段协议（KSTAR 对齐）

| 阶段 | 内容 | 对应 KSTAR | 测什么 |
|---|---|---|---|
| **Phase A** | 零知识基线（仅内部基线，不消耗模型调用） | K₀ | 先验水平 |
| **Phase B** | 3 个示例后作答 | K→S→T→A→R | 从示例归纳 + 校准 |
| **Phase C** | **给出真实纠错反馈后**继续作答 | **ΔR→K 更新** | **能否从失败中修正** |

Phase C 的反馈是**真实的 (input → correct output) 对**，不是光秃秃的"错了"两个���。因为携带信息的更新信号才构成真正的 ΔR；只告知"对/错"测的是惩罚敏感性，不是元认知。

### 2.3 核心创新：ECE 陷阱与退化检测

这是 NovCal 最重要的设计贡献，也是与其他元认知 benchmark 的根本分野。

**问题：ECE 单独使用是一个陷阱。** 一个恒定输出 50% 置信度的系统，如果准确率恰好是 50%，它的 ECE = 0——**完美的校准**，却完全不具备任何元认知能力。这个退化模式在选择性预测文献中有明确记载（Geifman & El-Yaniv, 2019；Ding et al., 2020）。

`scripts/demonstrate_ece_trap.py` 对此做了实证复现：

| 系统 | Accuracy | ECE↓ | AUROC↑ | 退化标记 |
|---|---|---|---|---|
| **陷阱系统**：恒定 50、准确率 50% | 0.500 | **0.000** | **0.500** | ⚠ |
| 随机猜测 | 0.250 | 0.250 | 0.500 | ⚠ |
| **前沿模型（真实实测）** | **0.732** | 0.192 | **0.889** | — |
| 恒定 50、准确率 0%（本仓库基线） | 0.000 | 0.500 | n/a | ⚠ 地板 |

**陷阱系统的 ECE = 0.000，比前沿模型的 0.192 "更好"，但它的 AUROC = 0.500——零信号。**

> 只按 ECE 排序的排行榜，会把一个"什么都不会"的系统排在真实前沿模型**之上**。

这正是 NovCal 强制并列报告 AUROC/AURC、并禁止退化系统参与 ECE 排名的原因。

**NovCal 的解决方案：多指标面板 + 显式退化标记。**

| 指标 | 测什么 | 会被什么欺骗 | NovCal 状态 |
|---|---|---|---|
| **ECE** | 概率刻度的校准 | 恒定输出 | 主指标 |
| **AUROC** | 置信度能否区分对错 | 无（只认排序） | 主指标 |
| **AURC** | 选择性预测质量 | 排序差的系统 | 主指标 |
| **Brier** | 严格评分规则 | 两者都罚 | 主指标 |
| **MCG** | 对/错时的置信度差 | — | 辅助 |
| **slope/intercept** | Cox 校准探针 | 过度自信 vs 无信号 | 辅助 |
| **退化检测** | 地板/天花板效应、恒定输出、置信度多样性不足、AUROC<0.60 | — | **强制标记** |

`build_report()` 会在任何切片上检测四种退化并写入 `degeneracy_reason`：
- **地板效应**：0 题正确 → 校准不可测量
- **天花板效应**：全对 → 同上
- **恒定置信度**：方差为 0 → ECE 无信息量
- **置信度多样性不足**：不同取值 < max(2, 5%·n)

**这个设计把"指标设计陷阱"从文档里的一句话变成了代码里的一条断言。**

### 2.4 难度分层

| Tier | 规则数 | 守卫概率 | 输入长度 | 角色 |
|---|---|---|---|---|
| 1 | 1 | 0% | 3–5 | 地板校准点 |
| 2 | 2 | 35% | 4–6 | 基础归纳 |
| 3 | 2–3 | 60% | 5–7 | 中等 |
| 4 | 3–4 | 75% | 6–9 | 天花板探测 |

实测区分度（启发式基线）：tier1 66.7% → tier2 25.6% → tier3 8.9% → tier4 0.0%。梯度单调且陡峭。

---

## 3. 人类基线考量 / Human Baseline

### 3.1 为什么本提案对人类基线保持谨慎

DeepMind 框架的第二阶段明确要求"采集具有人口统计学代表性的人类基线"。我认同其必要性，但**必须诚实说明本提案的边界**：

> **我尚未采集人类数据。** 任何在此之前给出的"人类准确率"都是无根据的猜测，而这类猜测正是评估研究中最常见的不严谨来源。因此我**拒绝**在提案中填写一张凭印象的"人类表现分布表"，并将其作为下一步的首要工作（见 §5）。

我给出的是**人类基线的设计规范**，而非数据：

**采样要求**
- n ≥ 60 每难度层，覆盖非 AI 从业者（AI 从业者不构成有效对照）
- 同时收集**信度**（retest 间隔 ≥2 周）与**元认知偏差**（实际准确率 vs 自评准确率）
- 每名参与者需签署知情同意，说明任务"无法提前练习"

**需要检验的假设**
- H1：人类在 tier 1–2 显著高于当前 AI（AI 已在 tier 1 达 100%）
- H2：人类置信度整体**过度自信**（Kahneman & Tversky 的校准研究范式）
- H3：人类在 tier 4 的置信度曲线出现**拐点**——开始承认不会（这是 AI 当前完全缺失的行为）

**若 H3 成立，NovCal 的核心价值即被证实**：它测量的正是人类有、AI 还没有的能力。

### 3.2 区分度设计

- **过易风险**：tier 1 对前沿模型已达天花板 → 通过 tier 4（多守卫组合）探测上限
- **过难风险**：地板基线（random/constant）全部被自动标记为退化 → 不会把"全员不及格"误读为"题目太难"
- **双向陷阱**：退化检测同时捕获地板与天花板，不预设"分数高=好"

---

## 4. 预期创新点与可行性 / Innovation & Feasibility

### 4.1 拿来了什么，改了什么

| 来源 | 拿了 | 去掉 | 原因 |
|---|---|---|---|
| **ARC** (Chollet, 2019) | "任务必须新颖、抗记忆" 的设计哲学；exact-match 评分 | 视觉网格 | 网格难程序化生成、评分容错低；符号序列可无限生成且精确可判 |
| **SCAN** (Lake & Baroni, 2018) | 组合规则 → 序列变换的任务结构 | **固定词表** | SCAN 规则公开，可被预训练数据覆盖；本方案每次重新采样 |
| **Geifman & El-Yaniv (2019)** | AURC / 选择性预测；**ECE 的退化性质** | — | 直接采纳其批评并内置为检测器 |
| **Ling et al. (2023)** 语义熵 | "校准比准确率更接近真实能力"的立场 | 自由文本+NLI 聚类 | 本方案输出为离散符号，exact-match 消除了语义等价问题，无需 NLI |
| **DeepMind 认知框架** | 三阶段协议；人类基线的必要性 | — | 直接采用 |

### 4.2 三项创新

1. **生成器即基准（结构性防污染）**：不是"我们没被污染"，而是"任务空间可证明不相交"。
2. **ECE 陷阱内置为断言**：把文献中的批评变成 `degeneracy_reason` 字段，恒定置信度系统无法在榜单上伪装成优秀。
3. **退化检测强制化**：地板/天花板/恒定输出/低多样性四类自动标记，防止"n/a"被读成"没问题"。

### 4.3 可行性

| 项目 | 状态 |
|---|---|
| 核心代码 | ✅ 已完成（`novcal/`，5 模块，纯标准库） |
| 单元测试 | ✅ 35/35 通过，含 4 条回归测试 |
| 自检 | ✅ `selftest` 通过（针对解析器的闭式期望值验证） |
| 基线跑通 | ✅ 5 个基线 × 351 项 |
| 前沿模型实测 | ✅ 56 项（真实作答，非模拟） |
| 模型适配层 | ✅ OpenAI / Anthropic / Gemini / OpenAI-compatible |
| Kaggle 提交 | ⏳ 待提交（本仓库含提交所需全部材料） |

**零第三方依赖**：核心 benchmark 与评分仅用 Python 标准库，`pip install` 都不是必需。matplotlib 仅用于可选绘图。

---

## 5. 后续工作

1. **人类基线采集**（最高优先级）——n ≥ 60/tier，含信度重测
2. **跨模型对比**——用 `scripts/run_model.py` 接入 GPT / Claude / Gemini / 开源模型各 ≥2 个
3. **Kaggle Community Benchmarks 上架**——生成器可直接暴露为 notebook
4. **守卫类型扩展**——当前 4 类守卫，可加入嵌套守卫以拉高 tier 4 上限
5. **置信度 elicitation 方式对比**——口头置信度 vs token 概率 vs 多次采样一致性

---

## 参考文献 / References

1. Burnell, R., Yamamori, Y., Firat, O., et al. (2026). *Measuring Progress Toward AGI: A Cognitive Framework.* Google DeepMind.
2. Chollet, F. (2019). *On the Measure of Intelligence.* arXiv:1911.01547.
3. Lake, B. M., & Baroni, M. M. (2018). *Generalization without Systematicity.* ICML. arXiv:1711.00350.
4. Geifman, Y., & El-Yaniv, R. (2019). *SelectiveNet: A Deep Neural Network with an Integrated Reject Option.* ICML 2019, PMLR 97:2151–2159. arXiv:1901.09192.
5. Ding, X., Kumar, S., Jordan, M. I., & Radivojac, A. (2020). *Calibration under Abstraction.* NeurIPS.（该文具体 arXiv 编号未核实，故不给出链接）
6. Naeini, M. P., Cooper, G., & Hauskrecht, M. (2015). *Obtaining Well Calibrated Probabilities Using Bayesian Binning.* AAAI.
7. Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. (2017). *On Calibration of Modern Neural Networks.* ICML.
8. Kuhn, L., Gal, Y., & Farquhar, S. (2023). *Semantic Uncertainty.* ICLR. arXiv:2302.09664.
9. Brier, G. W. (1950). *Verification of Forecasts.* Mon. Wea. Rev.
10. Chow, R. (1970). *An Optimal Strategy for Predicting the Outcome of Games.* Ann. Math. Statist. 41(1):399–409.（SelectiveNet 一文将拒答选项追溯至 Chow 1957；此处引用 1970 年的正式论文）
11. Mitchell, T. M., et al. (2022). *The Surprising Difficulty of Learning Compositional Functions.* (SCAN 的后续批评)