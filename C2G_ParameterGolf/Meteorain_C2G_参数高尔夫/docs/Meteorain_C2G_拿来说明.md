# Meteorain_C2G_拿来说明.md

> **作者**：07Meteorain（Meteorain）
> **日期**：2026-10-05
> **本文档回答**：从 nanoGPT / 官方 repo / 历史 top 方案**拿了什么、改了什么、为什么改**

CHALLENGE.md 明确要求这三句话作为工程能力证明。本文逐项拆解，并标注每处改动的**具体行级依据**。

---

## 0. 拿来主义原则的遵守声明

> **严禁从零写 Transformer。** 正确起点是 nanoGPT / OpenAI 官方 `train_gpt.py` / 历史 top 方案。

**我的实际做法**：

| 我自己从零写的部分 | 占比 |
|------------------|------|
| **无** | 0% |

我的 `train_gpt.py` 是官方脚本的**衍生作品**，保留了它的一切核心机制。所有新增代码都是「评估策略」「量化路径开关」「架构开关」「实验驱动」这四类**胶水逻辑**，没有任何一个模块是从零实现的。

---

## 1. 来源一：官方 `openai/parameter-golf` `train_gpt.py`

### 1.1 原样保留（未改一行）

| 组件 | 说明 | 为什么不该改 |
|------|------|-------------|
| `load_data_shard` / `TokenStream` / `DistributedTokenLoader` | `.bin` 数据读取与分发 | 官方格式已验证，改它等于引入 bug 风险而无收益 |
| `build_sentencepiece_luts` | BPB 所需的字节数LUT | **这是 BPB 计算的核心**，官方明确警告 tokenizer 相关的 bug 会「unjustly improve score」。我一行没动 |
| `Muon` + `zeropower_via_newtonschulz5` | Muon 优化器 | baseline 已在用。换掉它属于自找麻烦 |
| `RMSNorm` / `CastedLinear` / `Rotary` / `CausalSelfAttention` | 基础算子 | 已是优化过的版本（QK-Norm、GQA、`F.rms_norm` 原生融合） |
| `MLP` | relu² MLP | modded-nanoGPT 验证过的版本 |
| `restore_low_dim_params_to_fp32` | 控制参数精度保护 | 合理设计 |
| `quantize_float_tensor` 的 per-row int8 逻辑 | 量化核心 | per-row scale 的动机（输出通道动态范围差异大）是正确的 |
| 训练循环的 warmdown 时间估算逻辑 | `lr_mul` | 用时间而非步数估算剩余预算，这个设计是对的 |
| warmup 后还原权重/优化器状态 | 保证计时区间干净 | 细节但重要，我保留了 |
| artifact 大小计算方式 | 代码字节 + 压缩权重 | 官方定义，不能改 |
| `16,000,000` 十进制上限 | 硬约束 | 官方明确说「16 MiB / 16,777,216」**不算**，是十进制 16MB |

### 1.2 我改的部分：重构 `eval_val` →拆成两个函数

**原始代码**：官方 `eval_val` 一个函数，内部把验证集切成不重叠块。

**问题**：我无法用它来**对照**滑窗和分块两种评估——因为它只能算一种。CHALLENGE.md 要求「先写假设 → 跑对照 → 看差值」，而我的主线假设就是「评估方式本身有 0.03 的空间」。

**我的改动**：拆成
- `eval_val_chunked(...)` —— 原逻辑，几乎照搬（我修正了一个自己引入的冗余变量）
- `eval_val_sliding(...)` —— 新增，参考 `2026-03-19_SlidingWindowEval` 的实现

**为什么这么改**：因为滑窗和分块必须能在**同一个 checkpoint** 上跑，才能把差值干净地归因到评估方式本身。如果用两个不同训练的模型对比，就混淆了「模型差异」和「评估差异」——这是上游 `SlidingWindowEval` 记录里 pre-quant 数字几乎相同（1.2172 vs 1.2196）的原因，也是我想复现的实验设计。

---

## 2. 来源二：`records/.../2026-03-19_SlidingWindowEval`

### 拿了什么

`eval_val_sliding` 的完整实现思路（该记录目录下 `train_gpt.py` 第 837–931 行）。我**逐行读过**这段代码。

### 改了什么

1. **重写为独立函数**，参数通过 `Hyperparameters` 传入而非模块级常量
2. **补充字节数统计**：`upstream` 版本用 `float64` 直接累加，我统一走同一套LUT 逻辑，确保与 chunked 路径的字节数计算**完全一致**——否则 sliding 和 chunked 的 BPB 不可比，我的对照实验就失去意义
3. **保留其边界处理逻辑**：`s = 0 if ws == 0 else max(wlen - stride, 0)`——第一个窗口必须计分全部，否则开头的 token 永远拿不到分。这是这段代码里最容易写错的地方
4. **保留其因果性设计**：窗口只用前缀信息，无未来泄漏

### 为什么改

上游的代码是为了「刷一个分数」，我需要的是「**能开关、能对照、能归因**的实验装置」。所以我要把它变成可消融的组件，而不是固定行为。

**这段代码是我整个方案的地基**。它对应上游实测的 -0.0319 BPB，是全部改动里收益最大、风险最低的一项。

---

## 3. 来源三：`records/.../2026-03-18_FP16Embed_WD3600`

### 拿了什么

两个具体做法：
1. **fp16 嵌入直传**：「Instead of int8-quantizing `tok_emb.weight`, we pass it through as fp16... Drops the post-quant BPB degradation from ~0.007 to basically nothing (~0.0005)」
2. **腾空间的手法**：「shrunk the MLP hidden from 1024 to 992 to stay under 16MB」

### 改了什么

我实现了 `FP16_PASSTHROUGH_PATTERNS` 环境变量白名单机制，命中 `tok_emb` 的张量以 fp16 保留。

**我没有照搬「MLP hidden = 992」这个具体数字**，而是把它做成**决策流程**：

```
1. 先测 artifact 实际余量
2. 若余量 < 嵌入增量 → 缩 MLP hidden
3. 每次缩容后重测 artifact 和 BPB（因为缩 MLP 会损失能力）
4. 若所有腾挪都不划算 → 放弃 fp16 嵌入，把空间给模型容量
```

### 为什么改

上游的 992 是在**他们的具体配置**下试出来的。我本地是 6 层 256 维，和他们 9 层 512 维 + 缩到 992 的情况完全不同。**照搬别人的超参数而不验证，就是把别人的结论当自己的实验结果。**

另外我在 `方案草案` 4.2 里写明了放弃条件：如果fp16 嵌入的 0.007 收益不值得让模型整体变小，**我会放弃这项改动**。这是权衡，不是死磕。

---

## 4. 来源四：`records/.../2026-04-09_SP8192_3LayerRecur_ParResid_QK525_LegalTTT`（当前 SOTA 1.0810）

这份记录列了 7 项技术。我**筛掉了 5 项，只拿 2 项**，这个筛选本身是本节最重要的内容。

### 拿了什么（2 项）

**并行残差（Parallel Residuals）**
> 「Parallel Residuals (layers 7+) — GPT-J style, attention and MLP read from same input」

我实现了 `Block.forward` 的两条路径：
```python
# 串行（baseline）
x = x + attn_scale * attn(attn_norm(x))
x = x + mlp_scale  * mlp(mlp_norm(x))

# 并行（PARALLEL_RESIDUAL 且 layer_idx >= start）
h = x
x = x + attn_scale * attn(attn_norm(h))
x = x + mlp_scale  * mlp(mlp_norm(h))
```

**QK-gain**
> 「QK-Gain 5.25 — learnable per-head query scaling, monotonic improvement from 4.0 to 5.25」

baseline 已有 `q_gain` 参数（init 1.5），我只是把初值做成可配置并扫描。

### 明确没拿什么（5 项）及理由

| 技术 | 为什么放弃 |
|------|-----------|
| **SP8192 tokenizer** | 需要重新导出数据。我**无法验证**重导出的 BPB 计算与官方一致，而官方明确警告改tokenizer 的提交会被更严格审查。**这是能力边界，不是懒惰。** |
| **3-layer depth recurrence** | 上游 `FP16Embed_WD3600` 有明确失败记录：「needs way more steps than 10 min allows」。而且它依赖 11 层物理层，我本地 6 层无法验证。 |
| **Legal score-first TTT** | 合规性无法在本地验证。判违规则整个提交作废，风险与收益（-0.003 量级）严重不对称。 |
| **GPTQ / SDClip 量化** | 需要 Hessian 估计，实现复杂且正确性无法验证。int8 已能压住 artifact，边际收益低。 |
| **MuonEq-R / WD=0.095 / EMA=0.9965等超参** | 这些是针对 11 层 + SP8192 调出来的。我本地 6 层 + SP1024 直接照搬，大概率有害。**要扫，不要抄。** |

### 为什么这么筛

SOTA 方案是一个**整体**，它的各项技术在特定规模（11层/SP8192/8×H100）下互相支撑。拆开来搬到完全不同的规模（6层/SP1024/单卡）上，很可能水土不服。

我的原则是：**只拿「机制上可解释、我能独立验证」的改动，放弃「依赖特定规模调出来、我验证不了」的改动。**

---

## 5. 来源五：KellerJordan `modded-nanogpt` / Muon

### 拿了什么

- `Muon` 优化器 + Newton-Schulz 正交化（经官方 `train_gpt.py` 转手）
- relu² MLP
- QK-Norm（注意力 logit 归一化，防 softmax 饱和）
- skip connection 的 U-Net 式结构（前半存、后半反序取）

### 改了什么

**什么都没改。**

### 为什么不改

这三个是官方 baseline 已经在用的，也是 modded-nanoGPT 被反复验证过的部分。我把它们当**已知良好的基座**，不做无意义的改动。

**「知道什么不该改」和知道该改一样重要。** 每一个我主动加的开关，都是在基座上做加法，而不是重写基座——这样每个改动的贡献都能被单独测量。

---

## 6. 引用汇总

| 来源 | 类型 | 用途 |
|------|------|------|
| `openai/parameter-golf` `train_gpt.py` | 官方基座 | 骨架、BPB、Muon、数据、量化 |
| `records/.../2026-03-19_SlidingWindowEval` `train_gpt.py` L837–931 | 官方记录 | `eval_val_sliding` 实现思路 |
| `records/.../2026-03-18_FP16Embed_WD3600` `README.md` | 官方记录 | fp16 嵌入直传、缩 MLP 腾空间 |
| `records/.../2026-04-09_..._LegalTTT` `README.md` | 官方记录 | 并行残差、QK-gain |
| `records/.../2026-04-08_SP8192_ParallelResid_ScoreFirstTTT` | 官方记录 | 并行残差的交叉验证 |
| KellerJordan `modded-nanogpt` / Muon | 上游项目 | 优化器、MLP、QK-Norm、skip 结构 |
| `willdepueoai/parameter-golf` (HF) | 官方数据 | FineWeb sp1024 训练/验证集、tokenizer |

**许可**：官方仓库为 Apache-2.0。本项目在 `THIRD_PARTY_NOTICES.md` 中保留原始版权与许可声明，衍生作品沿用同一许可。

---

## 7. 三句话总结（CHALLENGE.md 要求的格式）

> **我拿了什么**：OpenAI 官方 `train_gpt.py` 的完整骨架（含 BPB 计算、Muon、数据加载、int8 量化），加上官方 `records/` 里三个 top 方案的已发表技术（滑窗评估、fp16 嵌入直传、并行残差 + QK-gain）。
>
> **我改了什么**：把单一 `eval_val` 重构为 `chunked` / `sliding` 双路径以支持对照实验；新增 fp16 嵌入直传白名单；新增并行残差可配置起始层；新增 16MB artifact 自检；新增实验驱动脚本与结构化结果收集。**没有重写任何基座组件。**
>
> **为什么改**：因为我的核心假设是「评估方式本身浪费了约 0.03 BPB，而量化让嵌入层损失了约 0.007」——这两个都不需要重新发明，只需要**做成可开关的组件并严格对照测量**。架构类改动（并行残差、QK-gain）我标注为「待实测决定」而非默认采纳，因为它们的收益依赖模型规模，而我没有 8×H100 去验证那个规模下的收益是否成立。

---

## 8. 诚实的局限声明

1. 我的方案**没有一个原创技术**。所有改动都有上游先例。我的贡献是**组合、验证与量化各项贡献**，这是当前算力条件下能做到的最诚实的事。
2. 我**没有在 8×H100 上验证过任何东西**。所有实测都在单卡 RTX 3050 上以缩小配置完成。
3. 我**没有跑出榜单级分数**。我的 BPB 数字只在本地配置下有意义，不可与官方榜单比较。
4. 我**否决了收益最大的技术（SP8192）**，理由是无法验证而非不认同。这个决策的代价是真实的：如果我有 8×H100 和充足时间，SP8192 应该是我第一个做的。

**最后一点尤其重要**：一个诚实的「我做不到 X，因为 Y」比一个包装过的「我做到了 X」更有价值。前者可以被信任，后者一旦被复现就会崩塌——而官方明确说了「Any non-reproducible results can be disqualified」。