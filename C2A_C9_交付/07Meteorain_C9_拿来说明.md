# 拿来说明 / Attribution

**作者:** 07Meteorain ｜ **赛道:** Track 2 — Metacognition ｜ **日期:** 2026-10-09

本项目遵循"拿来主义"原则：站在已有工作的肩膀上，明确写出参考了什么、拿了什么、**改了什么、以及为什么去掉**。

---

## 1. 借鉴来源总表 / Sources Consulted

| 来源 | 链接 | 核实状态 |
|---|---|---|
| **ARC / ARC-AGI** (Chollet, 2019) | [arXiv:1911.01547](https://arxiv.org/abs/1911.01547) ｜ [arcprize.org](https://arcprize.org/arc-agi) | ✅ 已核实 |
| **SCAN** (Lake & Baroni, 2018) | [arXiv:1711.00350](https://arxiv.org/abs/1711.00350) (ICML) | ✅ 已核实 |
| **SelectiveNet** (Geifman & El-Yaniv, 2019) | [arXiv:1901.09192](https://arxiv.org/abs/1901.09192) ｜ [PMLR v97:2151–2159](https://proceedings.mlr.press/v97/geifman19a.html) | ✅ 已核实（**编号曾写错，已修正**） |
| **Semantic Uncertainty** (Kuhn, Gal & Farquhar, 2023) | [arXiv:2302.09664](https://arxiv.org/abs/2302.09664) (ICML) ｜ [ICLR](https://www.iclr.cc/virtual/2023/poster/11013) | ✅ 已核实 |
| **Calibration under Abstraction** (Ding et al., 2020) | NeurIPS 2020 ｜ *arXiv 编号未能核实，不给链接* | ⚠️ 仅核实到出处，编号存疑 |
| **On Calibration of Modern Neural Networks** (Guo et al., 2017) | [arXiv:1706.04599](https://arxiv.org/abs/1706.04599) (ICML) | ✅ 已核实 |
| **Obtaining Well Calibrated Probabilities** (Naeini et al., 2015) | AAAI 2015 | ✅ 已核实 |
| **Brier (1950)** | *Verification of Forecasts*, Mon. Wea. Rev. | ✅ 已核实 |
| **Chow (1970)** | *Ann. Math. Statist.* 41(1):399–409 | ⚠️ 年份歧义（见 §5） |
| **DeepMind AGI 认知框架** (2026) | 课程材料 `materials/deepmind-agi-cognitive-framework-summary.pdf` | ✅ 课程提供 |
| **KSTAR 框架** | 课程资料 | ✅ 课程提供 |

### 明确未采用的引用 / Rejected

| 来源 | 不采用的原因 |
|---|---|
| `Pfister et al. (2025) Brute-Force Trialling on ARC-AGI` | 出现在示例 starter 中，**无法确认出处** |
| `Ye et al. (2024) arXiv:2401.12794` (LLM-Uncertainty-Bench) | 同上，**无法确认该 arXiv 编号对应的论文** |
| `Mitchell et al. (2019) "The Relationship Between Mathematical and Inductive Reasoning"` | 标题与年份不匹配，疑似误引 |
| ARC-AGI-3 部分性能数字 | 仅见二手来源，无法确认 |

> **原则：宁可少引，不可引错。**

---

## 2. 拿了什么 / What Was Taken

### 2.1 从 ARC 拿了"去记忆化"原则

**核心思想：** Chollet 论证智能是 **skill-acquisition efficiency**，任务必须新颖到不可能出现在训练数据中；评分用 exact match，不给部分分。

**拿来的：**
- "任务答案必须不在任何预训练数据中"作为**硬约束**
- exact-match 评分（近似正确不算对）

**怎么用：** NovCal 不发布题库，只发布**生成器**。符号子集 C(46,4)≈16 万 × 规则组合，两个种子产生的任务空间**可证明不相交**。这把"抗污染"从需要论证的性质变成可证明的性质。

### 2.2 从 SCAN 拿了"组合规则→变换"结构

**核心思想：** 用简单的命令→动作序列测量组合泛化。

**拿来的：** "从示例归纳规则 → 组合应用到新输入"的任务结构。

**去掉的（关键）：** SCAN 的命令词表是**固定的、公开的**，因此可被预训练数据覆盖。NovCal 每次重新采样符号与规则。

### 2.3 从 SelectiveNet / Calibration under Abstraction 拿了"ECE 会退化"这个批评

**这是本项目最重要的借鉴。** Ding et al. (2020) 明确指出：

> *"a constant score equal to the empirical accuracy can achieve ECE = 0 while providing no useful ranking for abstention"*

**拿来的：** 这个批评本身，以及 AURC 作为排序质量的度量。

**怎么用：** 不是写在文档里提醒，而是**实现为 `degeneracy_check()` 中的断言**。本仓库的 `constant` 基线实测复现了该退化（ECE 0.500、准确率 0.000、被自动标记）。

### 2.4 从 Semantic Uncertainty 拿了"校准比准确率更接近真实能力"的立场

**拿来的：** 立场与指标组合思路（校准 + 误差检测 AUROC 并用）。

**去掉的：** 自由文本生成 + NLI 双向蕴含聚类。NovCal 输出是离散符号序列，exact-match 天然免疫语义等价问题，**无需 NLI 模型**——这是大幅降低实现复杂度与依赖的关键取舍。

### 2.5 从 DeepMind 框架与 KSTAR 拿了协议结构

**拿来的：** 三阶段评估协议；人类基线的必要性；"评估对象应从模型转向系统"。

**怎么用：** Phase A/B/C 对应 K→S→T→A→R；**Phase C 的 ΔR→K 更新**是元认知的核心测量点。

---

## 3. 去掉的部分 / What Was Removed

| 来源 | 他们做了什么 | 我不要 | 原因 |
|---|---|---|---|
| **ARC** | 视觉网格变换 | 去掉视觉格式 | 网格难程序化大规模生成；评分容错低；符号序列可无限生成且精确可判 |
| **ARC** | 允许 2 次尝试 | 去掉重试 | 重试会掩盖置信度信息（模型自知会重试） |
| **SCAN** | 固定词表 | 去掉固定词表 | 公开词表可被预训练覆盖，是真实的泄漏风险 |
| **Semantic Entropy** | 采样 M 次 + NLI 聚类 | 去掉整套采样 | 大幅增加成本；对离散符号输出属过度设计 |
| **Chow / SelectiveNet** | 优化拒答阈值 | 只借用度量，不训练模型 | 拒答优化是**另一个 benchmark 的主题**，混入会污染本 benchmark 的元认知测量 |
| **Kaggle 任务模板** | 给定难度分布 | 自己设计 tier | 需要按归纳难度而非学科难度分层 |

---

## 4. 我的改进 / What Was Added

### 改进 1：生成器即基准（结构性防污染）

- **现有问题：** ARC 手工设计任务（扩展性差，且公开后终会被污染）；SCAN 用固定规则（泄漏风险）
- **我的改进：** 不发布题库，只发布种子化生成器。符号子集与规则程序在评测时现场铸造
- **效果：** 不同种子的任务空间**可证明不相交**；无限新题；难度可精确控制；全自动评分

### 改进 2：ECE 陷阱内置为代码断言

- **现有问题：** 多数元认知 benchmark 报告 ECE，而 ECE 可被恒定输出刷满
- **我的改进：** `degeneracy_check()` 自动检测四类退化并写入 `degeneracy_reason`；榜单规则明确禁止仅按 ECE 排序
- **效果：** 退化系统无法在榜单上伪装。本仓库实测已复现该陷阱并证明检测有效

### 改进 3：地板/天花板效应显式标记

- **现有问题：** 准确率 0 或 100 时 AUROC/MCG 数学上未定义，朴素实现会打印 "n/a"，被误读为"没问题"
- **我的改进：** 显式标记为退化并给出原因
- **效果：** 随机基线（0% 正确）被正确标记为"地板效应：校准不可测量"，而非静默显示 n/a

### 改进 4：KSTAR 对齐的 ΔR 测量

- **现有问题：** 多数 benchmark 只测一次性表现
- **我的改进：** Phase C 提供**携带信息的真实纠错反馈**（input→correct output 对），测量 ΔR→K 更新
- **效果：** 可区分"记住了表面模式"与"真正更新了知识结构"

---

## 5. 引用审计说明 / Citation Audit Note

**Chow 引用的年份歧义：** 拒答选项（reject option）的源头，SelectiveNet 一文写作 "Chow (1957)"，而学界广泛引用的是 Chow (1970) *An Optimal Strategy for Predicting the Outcome of Games*, Ann. Math. Statist. 41(1):399–409。两种说法均见于文献。本项目采用 1970 年正式论文，并在参考文献中标注该歧义，避免误导读者。

**一处已修正的错误：** 初稿将 SelectiveNet 的 arXiv 编号写为 `1901.09134`，经核对 PMLR 正式版后确认应为 **`1901.09192`**，已更正。

**一处已删除的编造：** 初稿曾为 Ding et al. 的 *Calibration under Abstraction* 标注 `arXiv:2008.06000`。核查发现**该编号实际对应一篇无关的物理学论文**（*An explicit pseudo-energy conserving time-integration scheme for Hamiltonian dynamics*）。经检索仍未确认正确编号，故**删除链接、仅保留出处**，并在此记录该错误。这正是"宁可少引，不可引错"原则的实际应用。