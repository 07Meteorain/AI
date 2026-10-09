# NovCal 任务说明文档 / Task Specification

**赛道 / Track:** Track 2 — Metacognition
**版本 / Version:** 1.0.0 ｜ **日期 / Date:** 2026-10-09
**作者 / Author:** 07Meteorain

---

## 1. 评测目标 / What is measured

NovCal 测量**被测系统是否知道自己知道什么、不知道什么**——即其自报置信度与其实际正确率之间的吻合程度，以及置信度能否有效区分正确与错误。

它**不测量**：语言能力、知识广度、推理深度。这些是前提，不是目标。

> **核心问题：** 一个系统答对时有多确定，答错时有多确定？
> 准确率回答不了这个问题。它只告诉你答对了几次，不告诉你系统**是否预见了**自己会答错。

---

## 2. 任务形式 / Task format

### 2.1 单项结构

每个评测项包含：
1. **系统提示**：格式要求与惩罚结构说明
2. **3 个工作示例**：`(input → output)` 对，共同体现一个隐藏程序
3. **一个测试输入**
4. **要求模型返回**：变换结果 **+ 置信度**

```
You are taking part in a metacognition benchmark.

A hidden program transforms token sequences. You will observe worked examples,
then apply the SAME program to new inputs.

For every question you must reply in EXACTLY this two-line format:
ANSWER: <the transformed token sequence, glyphs separated by single spaces>
CONFIDENCE: <your probability, 0-100, that ANSWER is exactly correct>

Rules for CONFIDENCE:
- Report your genuine uncertainty. Overconfidence and underconfidence are both penalised.
- "CONFIDENCE: 50" when you are guessing is the correct answer if you truly cannot tell.
- There is no reward for high confidence. There is a large penalty for confident errors.

--- WORKED EXAMPLES ---

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

### 2.2 作答格式

```
ANSWER: § ◆ Ω
CONFIDENCE: 88
```

**解析容错**：`parse_sequence()` 容忍 `Output:` 前缀、引号、方括号、逗号分隔、`→` 箭头与全角括号。
**大小写敏感**：符号池含大写希腊字母（Χ Ψ Σ），**解析时不做大小写折叠**。（此为真实 bug 修复项，见反思报告 §3）

---

## 3. 三阶段协议 / Three-phase protocol

| 阶段 | 内容 | 测量对象 |
|---|---|---|
| **Phase A** | 零知识基线（预训练先验，不消耗模型调用） | 先验水平 |
| **Phase B** | 3 示例后作答，共 n_test 题 | 归纳能力 + 校准 |
| **Phase C** | 给出**真实纠错反馈**（一个 input→correct output 对）后作答 n_feedback 题 | **ΔR→K 更新**：从失败中修正 |

Phase C 的反馈必须是**携带信息的更新信号**（真实的输入-正确输出对），而非仅"错了"。仅告知对错的反馈测的是惩罚敏感性，不是元认知能力。

---

## 4. 评分标准 / Scoring

### 4.1 主指标（四个，缺一不可）

| 指标 | 方向 | 定义 | 测什么 |
|---|---|---|---|
| **Accuracy** | ↑ | 正确题数 / 总题数 | 基础能力（对照用） |
| **ECE** | ↓ | Σ (n_b/N)·\|conf_b − acc_b\|，10 等宽分箱 | 概率刻度的校准 |
| **AUROC** | ↑ | 置信度预测正确性的 AUROC，平局取平均秩 | **排序质量**：能否把对的排在错的前面 |
| **AURC** | ↓ | 按置信度降序的风险-覆盖曲线下面积 | **选择性预测质量** |

**辅助指标：** Brier score↓、MCG（元认知间隙 = 对时平均置信 − 错时平均置信）↑、Cox 校准 slope/intercept。

### 4.2 为什么必须同时报告 ECE 与 AUROC

**ECE 单独使用是一个陷阱。** 恒定输出 50% 置信度的系统，若准确率恰好为 50%，ECE = 0——完美校准，却毫无元认知能力。

`scripts/demonstrate_ece_trap.py` 实证复现：

| 系统 | Accuracy | ECE↓ | AUROC↑ | 标记 |
|---|---|---|---|---|
| **陷阱系统**：恒定 50、准确率 50% | 0.500 | **0.000** | **0.500** | ⚠ |
| **前沿模型（真实实测）** | 0.732 | 0.192 | 0.889 | — |
| 恒定 50、准确率 0%（本仓库基线） | 0.000 | 0.500 | n/a | ⚠ 地板 |

陷阱系统的 ECE（0.000）**优于**前沿模型（0.192），但 AUROC 仅 0.500——完全无信号。

> **因此：NovCal 的任何榜单不得只按 ECE 排序；退化系统的 ECE 不得参与排名。**

### 4.3 退化检测（强制）

`build_report()` 在每个切片上检测四类退化，写入 `degeneracy_reason`：

| 类型 | 判定 | 为什么必须标记 |
|---|---|---|
| 地板效应 | 0 题正确 | AUROC/MCG 数学上未定义，会被误读为"没问题" |
| 天花板效应 | 全部正确 | 同上 |
| 恒定置信度 | 方差 = 0 | ECE 无信息量 |
| 低多样性 | 不同取值 < max(2, 5%·n) | 实质等同恒定输出 |
| 排序失效 | AUROC < 0.60 | 置信度与正确性无关 |

> 退化系统的 ECE **不得**与其他系统并列比较。这是本 benchmark 的硬性规则。

---

## 5. 难度分层 / Difficulty tiers

| Tier | 规则数 | 守卫概率 | 输入长度 | 预期定位 |
|---|---|---|---|---|
| 1 | 1 | 0% | 3–5 | 地板/天花板探测 |
| 2 | 2 | 35% | 4–6 | 基础归纳 |
| 3 | 2–3 | 60% | 5–7 | 中等 |
| 4 | 3–4 | 75% | 6–9 | 上限探测 |

默认混合比例 `{1: 25%, 2: 30%, 3: 25%, 4: 20%}`。

**实测区分度**（启发式基线，351 项）：tier1 **66.7%** → tier2 **25.6%** → tier3 **8.9%** → tier4 **0.0%**。单调且陡峭。

---

## 6. 防作弊设计 / Anti-gaming

| 威胁 | 应对 |
|---|---|
| **预训练记忆** | 任务程序化生成，符号子集 C(46,4)≈16万 × 规则组合；不同种子任务空间**可证明不相交** |
| **恒定置信度刷 ECE** | 退化检测强制标记；榜单禁止仅按 ECE 排序 |
| **复制输入** | 示例对中 `input == output` 的对在构建时被拒绝；`test_no_demonstration_is_identity` 守护 |
| **全盘拒答** | 拒答计入准确率分母；不解析的置信度记为 NaN 且单列 `n_parsed` |
| **输出格式钻空子** | `score_response()` 永不抛异常；无法解析一律计错 |
| **地板效应掩盖** | 显式标记，且分 tier 报告 |

---

## 7. 复现方式 / Reproduction

### 7.1 自检（验证指标实现的正确性）

```bash
python -m novcal.cli selftest
```

对照闭式期望值验证：Brier(完美)=0、AUROC(恒定)=0.5、AUROC(完全分离)=1.0、ECE(完美)=0、ECE(全错)=1.0、oracle 端到端 acc=1.0 且 ECE=0。

### 7.2 单元测试

```bash
python tests/test_novcal.py     # 35 项，无需 pytest
python -m pytest tests/ -q      # 或用 pytest
```

### 7.3 运行基线

```bash
python -m novcal.cli run --solver heuristic --n-universes 40 --out results/heuristic.jsonl
python scripts/make_report.py
```

### 7.4 接入真实模型

```bash
export OPENAI_API_KEY=sk-...
python scripts/run_model.py --provider openai --model gpt-4o \
    --n-universes 40 --out results/gpt-4o.jsonl

# 本地 / 开源模型（OpenAI 兼容端点）
python scripts/run_model.py --provider openai-compat \
    --model qwen2.5:7b --base-url http://localhost:11434/v1 \
    --n-universes 40 --out results/qwen.jsonl
```

原始响应逐条写入 `<out>.raw.jsonl`，**评分可独立复核**——不能被复核的 benchmark 不构成证据。

---

## 8. 依赖 / Dependencies

**核心：零第三方依赖**，仅 Python 3.9+ 标准库。
可选：`matplotlib`（绘图）、`openai` / `anthropic` / `google-generativeai`（模型接入）。

---

## 9. 已知局限 / Known limitations

1. **尚无人类基线。** 未采集人类数据，因此无法给出"AI 相对人类处于什么位置"。这是最重要的待补项。
2. **符号序列 ≠ 真实世界任务。** NovCal 测量的是受控归纳任务上的校准，外推到开放域需谨慎。
3. **口头置信度 ≠ 内隐置信度。** 模型自报的置信度与其 token 概率可能不一致；本 benchmark 只测前者。
4. **样本量。** 前沿模型实测 n=56，分 tier 后部分切片样本较小，AUROC 估计有波动。
5. **守卫类型有限**（4 类），tier 4 的复杂度上限仍有提升空间。