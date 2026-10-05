# Meteorain_C2G_方案设计.md

> **作者**：07Meteorain（Meteorain）
> **日期**：2026-10-05
> **上游文档**：`Meteorain_C2G_方案草案.md`（回答算力申请门槛问题）
> **本文档作用**：在草案基础上展开——技术选型细节、实验矩阵、否决清单、风险与复现方案

---

## 1. 目标与定位

| 项目 | 内容 |
|------|------|
| 目标等级 | Level 2（BPB < 1.18）起步，条件允许时冲击 Level 3 |
| 主线方向 | **评估策略 + 量化保真度**，架构改动作为二级增益 |
| 验证条件 | 单卡 RTX 3050 4GB（**非**赛事 8×H100 口径） |
| 验证方式 | 等算力固定步数对照实验，3 seed 稳定性检验 |
| 核心产出 | 一份**每个数字都能追溯到实测条件**的消融报告 |

**必须先说清楚的边界**：本机没有 8×H100。因此本方案验证的是**方法论与各改动的相对贡献**，不是最终榜单成绩。所有本地 BPB 数字都标注了测量条件，**不与官方 8×H100 榜单数字直接比较**。榜单分数只填实测值。

---

## 2. 技术选型：五项改动与证据链

### 总览

| 改动 | 开关变量 | 类型 | 上游证据 | 本地是否采纳 |
|------|---------|------|---------|------------|
| A. 滑窗评估 | `SLIDING_WINDOW_EVAL` | 评估 | record 2026-03-19，实测 -0.0319 | ✅ 采纳为主线 |
| B. fp16 嵌入直传 | `FP16_EMBED_PASSTHROUGH` | 量化 | record 2026-03-18，退化 0.007→0.0005 | ✅ 采纳 |
| C. 并行残差 | `PARALLEL_RESIDUAL` | 架构 | PR #1204/#1412 | ⚠️ 待实测决定 |
| D. QK-gain 调优 | `QK_GAIN_INIT` | 架构 | record 2026-04-06 | ⚠️ 待实测决定 |
| E. LR/warmdown 调优 | `TUNED_LR` | 训练 | record 2026-03-18 | ⚠️ 待实测决定 |

### A. 滑窗评估（主线）

**问题**：官方 baseline 把验证集切成互不重叠的 1024-token 块。块内第一个 token 的上文长度是 0，平均每个 token 只有约 512 个上文 token。这是**评估方式造成的信息浪费**，不是模型能力不足。

**机制**：窗口长度仍为 `train_seq_len`，但每次只前进 `stride` 个 token，且只对最右边 `stride` 个 token 计分（它们已累积 `seq_len - stride` 个上文）。

```
stride=64, seq_len=1024:
窗口0: [0........1023]        计分全部 1024个（没有前一个窗口可承接）
窗口1: [64.......1087]         只计分 [1024..1087]，前 960 个已计过
窗口2: [128.....1151]         只计分 [1088..1151]
...
每个 token 恰好计分一次 ✓
每个 token 的上文长度 >= seq_len - stride = 960 ✓
```

**为什么合法**：窗口严格因果（只用前缀），每个 token 只被计分一次（不重不漏），标准 softmax over full vocab（无 n-gram 缓存、无 logit bias）。这满足官方 Issue #1017  Track B 的全部条件。

**代价**：窗口数 = total_tokens / stride，是 chunked 的 `seq_len / stride` = 16 倍计算量。这就是为什么它必须走「评估限时 600s（独立于训练 600s）」这个预算。

### B. fp16 嵌入直传

**问题**：官方量化把 `tok_emb.weight` 也做 int8。但 tied embeddings 意味着同一份权重**同时**承担两个角色：
- input embedding：决定每个 token 的初始表示
- output head：直接产生 logits

量化误差经 output head **直接放大到 logits**，没有中间层可以吸收。这是量化误差的最大来源。

**机制**：`quantize_state_dict_int8` 增加一个白名单 `FP16_PASSTHROUGH_PATTERNS`（默认 `tok_emb`），命中的张量以 fp16 原样保留，不走 int8 路径。

**代价与决策**：fp16 是 int8 的两倍字节。`1024 × 256`（本地配置）= 262,144 参数 → 多约 262KB。官方配置 `1024 × 512` = 524,288 参数 → 多约 512KB。**必须验证 artifact 是否仍 ≤ 16,000,000**，这是本项的硬约束。

**与上游的差异**：上游 `FP16Embed_WD3600` 把 MLP hidden 从 1024 降到 992 来腾空间。我把它做成**决策点而非硬编码**——先测 artifact 余量，再决定是否缩 MLP。理由是缩 MLP 会损失模型能力，必须实测权衡，不能拍脑袋定一个数。

### C. 并行残差

**串行**（baseline）：`x = x + attn(x); x = x + mlp(x)`
**并行**（本改动）：`h = x; x = x + attn(h); x = x + mlp(h)`

让 attention 和 MLP 读**同一份**输入，梯度路径更直接，深层信号传播更顺（GPT-J 提出）。

**关键设计**：`PARALLEL_RESIDUAL_START` 默认 7，即只在深层启用。浅层并行可能有害——浅层需要串行的逐层精炼。这需要在本地实测确认起始层是否合理。

**风险提示**：上游是在 11 层 + SP8192 上验证的，本地是 6 层 + SP1024。**架构改动的收益高度依赖规模**，不能假设直接移植有效。所以我把它列为「待实测决定」，若有害则剔除并如实记录。

### D. QK-gain 调优

`q_gain` 是 per-head 可学习缩放，直接控制 attention logit 的尺度 → softmax 锐度。baseline 用 1.5，上游 SOTA 用 5.25 并报告「从 4.0 到 5.25 单调改进」。

**风险**：5.25 是在 11 层 + 大vocab 上调出来的。本地 6 层模型的最优值可能不同。所以我要做**扫描**而不是直接照搬 5.25。

### E. LR / warmdown 调优

**问题诊断**：baseline 默认 `ITERATIONS=20000`，`WARMDOWN_ITERS=1200`。但 10 分钟预算下实际只能跑约 13,780 步。`lr_mul` 用「时间」估算剩余时间，所以 warmdown 在 wallclock 上确实生效了——问题在于 **1200 步的 warmdown 窗口相对 13,780 步的总训练太短**，LR 在最后 8.7% 的时间里才归零，模型没时间在低 LR 下收敛。

**改动**：`WARMDOWN_ITERS` 1200 → 3600，`MATRIX_LR` 0.04 → 0.06（上游 `FP16Embed_WD3600` 的组合）。

**逻辑**：更大的 warmdown 窗口 + 更高的峰值 LR = 在有限预算下更充分地利用高 LR 阶段探索，再平滑收敛。

---

## 3. 实验矩阵

### 3.1 等算力原则

所有实验使用**完全相同的** `ITERATIONS` / `TRAIN_BATCH_TOKENS` / 模型形状，**唯一变量**是要测的开关。这样 BPB 差值才能归因到那一个改动。

### 3.2 本地配置（与官方口径的差异必须明示）

| 参数 | 官方 baseline | 本地实验 | 为什么这样配|
|------|-------------|---------|-----------|
| GPU | 8× H100 SXM | 1× RTX 3050 4GB | 硬约束 |
| 控制变量 | wallclock 600s | **固定步数** | 单卡速度不可比，固定步数才能保证算力相等 |
| NUM_LAYERS | 9 | 6 | 4GB 显存限制 |
| MODEL_DIM | 512 | 256 | 同上 |
| TRAIN_SEQ_LEN | 1024 | 512 | 同上 |
| TRAIN_BATCH_TOKENS | 524,288 | 32,768 | 同上 |
| ITERATIONS | 13,780（实测） | 600 | 在单卡上可行的规模 |
| VOCAB_SIZE | 1024 | 1024 | **保持一致**——BPB 是 tokenizer 无关的，同 vocab 才能对照 |

**必须强调**：这个规模**足够验证各改动的相对贡献**（我的核心问题），但**不足以复现官方绝对分数**。我不会把本地数字外推到 8×H100。

### 3.3 实验列表

| ID | 配置 | 检验假设 | 主要看|
|----|------|---------|--------|
| E0_baseline | 官方原样 | 建立本地参照系 | val_bpb、artifact |
| E1_sliding_eval | E0 + A | 上下文增益能否复现 | **sliding vs chunked 差值** |
| E2_fp16_embed | E0 + B | 量化退化能否压到~0.0005 | **quant_gap**、artifact |
| E3_parallel_residual | E0 + C | 架构改动独立贡献 | val_bpb |
| E4_qk_gain | E0 + D(QK=5.25) | QK-gain 是否单调有效 | val_bpb |
| E5_tuned_lr | E0 + E | schedule 是否是瓶颈 | val_bpb、final train_loss |
| E6_all_combined | A+B+C+D+E | 各组件是否协同 | val_bpb、artifact |
| E7_seeds | E6 × 3 seeds | 结论是否稳定 | 均值 ± stderr |

### 3.4 三个必看指标（缺一不可）

1. **`val_bpb`** —— 榜单分数，越低越好
2. **`artifact_bytes`** —— 必须 ≤ 16,000,000，超了直接判负
3. **`quant_gap` = chunked_bpb − sliding_bpb** —— 我的方法论护城河

**为什么第 3 个必不可少**：榜单分数用的是**量化后**的模型。如果只看 pre-quant 数字，我会把「模型变强了」和「压缩变松了」混为一谈。比如 fp16 嵌入会让量化退化变小——如果我不单独测 quant_gap，就会误以为它「提升了模型能力」，而实际上它只是**减少了压缩损失**。这两个是完全不同的结论。

---

## 4. 否决清单：明确不做的事及理由

这一节是本方案最重要的部分之一。**知道什么不该做，比知道该做什么更能说明判断力。**

| 技术 | 上游收益 | 我的否决理由 |
|------|---------|-------------|
| **SP8192 tokenizer** | -0.03 ~ -0.05（最大单项） | 需要重新导出整个训练/验证集。我**无法验证**重导出的 BPB 计算与官方是否一致——官方明确警告「改 tokenizer 的提交会被更严格审查 since bugs may unjustly improve your score」。在没有官方环境交叉验证前提交，风险大于收益。**这是能力边界内的诚实否决，不是 ignorance。** |
| **3-layer depth recurrence** | SOTA 组成部分 | 上游 `FP16Embed_WD3600` 明确记录失败教训：「depth recurrence 想法有潜力，但 10 分钟给不了它足够的步数」。而且它在 SOTA 里依赖 11 层物理层，我本地 6 层根本无法验证。 |
| **Legal score-first TTT** | -0.003 量级 | 合规性判定我无法在本地完整验证。一旦被判违规，整个提交作废。收益与风险严重不对称。 |
| **GPTQ / SDClip** | 量化精度改善 | 需要 Hessian 估计，实现复杂且我无法验证其正确性。在 int8 已能压住 artifact 的情况下，收益边际。 |
| **int6 QAT** | artifact 更小 | 本地 artifact 远未到 16MB 上限（6 层 256 维远小于官方配置），**省空间不是我的瓶颈**，做它是过度工程。 |
| **SwiGLU 替代 relu²** | 上游测为负收益 | 上游 `FP16Embed_WD3600` 实测：「better per-step quality but 45% slower，net negative」。有明确证据的负收益，不重复踩。 |
| **更高 embed LR (0.08)** | — | 上游实测「hurt convergence」。有明确证据的负收益。 |

**否决的共同逻辑**：优先选择「我能自己验证」的改动，而非「收益最大但我验证不了」的改动。这是在当前算力约束下唯一负责任的策略。

---

## 5. 风险登记

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| fp16 嵌入导致 artifact 超 16MB | **高** | 提交作废 | 缩 MLP hidden 腾空间（需实测）；实在不行放弃该项，用空间换模型容量 |
| 本地结论与上游差异大 | **高** | 结论不可移植 | 不外推。分层陈述「本地实测」与「上游已验证」，绝不混写 |
| 滑窗评估在本机超时 | 中 | 无法出分 | 调大 `EVAL_STRIDE`（收益递减但仍优于 chunked）；本地不限时，官方口径下需精算 |
| 并行残差/ QK-gain 无效或有害 | 中 | 需剔除 | 单独跑隔离验证；有害就剔除并如实记录 |
| 单卡训练步数过少，模型欠拟合 | **高** | 绝对分数失真 | 这是**已知且已声明**的限制；用等算力对照保证相对比较仍然有效 |
| 过拟合验证集 | 低 | 分数虚高 | 我**不用验证集调超参**，只用它做最终评估；超参选择依据是上游记录与 train loss |

---

## 6. 复现方案

### 6.1 本地复现（我实际跑过的）

```bash
# 环境
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install numpy tqdm sentencepiece huggingface-hub

# 数据（官方导出的 sp1024FineWeb）
python data/cached_challenge_fineweb.py --variant sp1024 --train-shards 8

# 单个实验
cd code
python run_experiments.py --only E0_baseline
python run_experiments.py --ablation# 完整矩阵
python run_experiments.py --seeds       # 3 seed 稳定性
```

### 6.2 官方 8×H100 口径（**待拿到算力后执行**）

```bash
# 完整配置（A+B+C+D+E 全开）
RUN_ID=meteorain_c2g_full \
DATA_PATH=./data/datasets/fineweb10B_sp1024/ \
TOKENIZER_PATH=./data/tokenizers/fineweb_1024_bpe.model \
VOCAB_SIZE=1024 NUM_LAYERS=9 MODEL_DIM=512 NUM_HEADS=8 NUM_KV_HEADS=4 \
MLP_MULT=2 TIE_EMBEDDINGS=1 \
SLIDING_WINDOW_EVAL=1 EVAL_STRIDE=64 \
FP16_EMBED_PASSTHROUGH=1 \
PARALLEL_RESIDUAL=1 PARALLEL_RESIDUAL_START=7 \
QK_GAIN_INIT=5.25 TUNED_LR=1 \
MAX_WALLCLOCK_SECONDS=600 \
torchrun --standalone --nproc_per_node=8 train_gpt.py
```

⚠️ **按方案草案 4.2 的逻辑，此配置很可能超 16MB**（fp16 嵌入多占约 512KB，而 baseline 只剩约 136KB 余量）。必须在同一次运行里同步把 `MLP_HIDDEN` 从 1024 降到 992（上游验证过的做法），或按实测逐步下调。**绝不能提交超限 artifact。**

---

## 7. 与 Level 4 的差距（诚实评估）

我清楚当前方案**不是** Level 4（要求原创架构改动 + 英文 6 页技术报告 + 视频 + 讲座）。差距：

| Level 4 要求 | 当前状态 |
|--------------|---------|
| 原创架构改动 | ❌ 我的改动全部有上游先例，我是**组合与验证**，不是原创 |
| 原创训练策略 | ❌ 同上 |
| 完整 ablation + 理论解释 | ⚠️ 有 ablation，理论解释不够深 |
| 3 seed 日志 | ✅ 计划内|
| 英文 technical report (PDF 6+页) | ❌ 未产出 |
| GitHub Repo + CI | ⚠️ 会上传，但无 CI |
| 讲解视频 + 群内分享 | ❌ 未产出 |

**为什么不做**：Level 4 需要 8×H100 上跑数十次实验来支撑「原创」二字。在单卡上我只能验证别人的想法，无法产生原创贡献。**与其包装，不如诚实标注位置。**

我的判断是：**把 Level 2/3 做到扎实、证据链完整、每个数字可追溯，价值高于包装成Level 4 但核心结论无法验证。**

---

## 8. 一页总结

- **主线**：滑窗评估（零训练成本、纯工程收益、已验证 -0.03 量级）
- **保真**：fp16 嵌入直传（减少量化损失，需验证 artifact 空间）
- **增益**：并行残差 / QK-gain / LR 调优（待实测，收益依赖规模，不假设有效）
- **方法论**：等算力固定步数对照 + 三指标（val_bpb / artifact / quant_gap）+ 3 seed 稳定性
- **诚实边界**：单卡 RTX 3050 验证方法论，不外推榜单分数，不伪造任何数字
- **否决原则**：优先「我能验证的」而非「收益最大但我验证不了的」