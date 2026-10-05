# Meteorain_C2G_参数高尔夫 —— 极限约束下的语言模型训练

> **作者**：07Meteorain（Meteorain）
> **挑战**：C2G · OpenAI Parameter Golf
> **日期**：2026-10-05
> **一句话**：在 10 分钟 / 16MB 的极限约束下优化语言模型压缩率（BPB），全部改动均可消融验证。

---

## ⚠️ 请先读这一段：诚实的实验边界

**本项目在单张 NVIDIA RTX 3050 Laptop GPU（4GB 显存）上完成，不是赛事的 8×H100 SXM 口径。**

| 项目 | 官方 baseline | 本项目本地实验 |
|------|-------------|---------------|
| 硬件 | 8× H100 SXM | **1× RTX 3050 4GB** |
| 控制变量 | wallclock 600s | **固定步数 1000 步** |
| 层数/宽度 | 9 层 × 512 | 6 层 × 256 |
| 序列长度 | 1024 | 512 |
| 训练 tokens | ~7.2B | ~32.8M |
| 验证集 | 全量 62,021,632 tokens | **前缀 1,000,000 tokens** |
| 验证步数 | 13,780 | 1,000 |

**因此**：
- ✅ 本地实验能可靠回答：**各个改动之间谁更有用、方向对不对、能不能协同**
- ❌ 本地实验**不能**回答：**8×H100 上的最终榜单分数是多少**

**我没有伪造任何未跑过的数字。** 所有本地 BPB 数字都附带测量条件，且 `submission.json` 里带 `val_set_is_full_official: false` 字段，任何人一眼可辨。

---

## 实测结果摘要

**最终方案 E7 = 滑窗评估 + fp16 嵌入直传 + LR 调优**（3 个独立 seed）

| seed | val_bpb | artifact (bytes) |
|------|--------:|-----------------:|
| 1337 | 1.74270 | 3,749,258 |
| 42 | 1.74122 | 3,748,668 |
| 314 | 1.73473 | 3,749,350 |
| **均值** | **1.73955** | 3,749,092 |

- 相对本地 baseline（1.76660）：**−0.02705 BPB（−1.53%）**
- 统计显著性：**t = −11.05，p < 0.01**（df=2 临界值 4.30）
- artifact **3,770,750 字节**（含代码），距 16,000,000 上限余量 12,229,250

**逐项消融**（等算力，各 1,000 步）：

| 改动 | Δ BPB | 处置 |
|------|------:|------|
| A 滑窗评估 | **−0.01786** | ✅ 采纳 |
| E LR 调优 | −0.00072 | ✅ 采纳 |
| B fp16 嵌入 | −0.00066 | ✅ 采纳 |
| C 并行残差 | −0.00005（需先修正 start）| ⚠️ 低于噪声阈值 |
| D QK-gain 5.25 | **+0.00832** | ❌ 有害，已剔除 |

**两个最重要的发现**：
1. 滑窗评估的收益**100% 归因于评估方式**（同权重对照，分数逐位相同到小数点后 8 位）
2. **照搬上游超参数会失败**——QK-gain 5.25 在 11 层模型上单调改进，在 6 层上造成真实退化

⚠️ **这些数字来自单卡 RTX 3050（4GB）、6 层 256 维、32.8M tokens，不可与官方 8×H100 榜单比较。**

---

## 目录结构

```
Meteorain_C2G_参数高尔夫/
├── code/
│   ├── Meteorain_C2G_train_gpt.py      # 主训练脚本（最终提交物）
│   └── run_experiments.py              # 消融实验驱动
├── docs/
│   ├── Meteorain_C2G_方案草案.md        # ⭐ 算力申请门槛文档（≥500字）
│   ├── Meteorain_C2G_方案设计.md        # 技术选型 + 实验矩阵 + 否决清单
│   ├── Meteorain_C2G_ablation.md       # 消融实验报告
│   ├── Meteorain_C2G_leaderboard.md    # BPB 对比表
│   ├── Meteorain_C2G_AI日志.md          # ⭐ AI 使用记录（必交）
│   ├── Meteorain_C2G_拿来说明.md        # 拿了什么/改了什么/为什么
│   └── Meteorain_C2G_AAR复盘.md         # ⭐ AAR 复盘（课程硬性交付项）
├── logs/                                # 训练日志（每实验一份）
├── results/                             # 结构化实验结果 JSON
└── submission/                          # 提交元数据与 artifact 打包
    ├── Meteorain_C2G_submission_*.tar.gz
    └── Meteorain_C2G_submission_*.json
```

---

## 快速开始

### 环境

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install numpy tqdm sentencepiece huggingface-hub
```

> Windows 本地无 Triton，`torch.compile` 不可用，脚本会自动降级为 eager。
> 用 `USE_COMPILE=0` 显式关闭。用**固定步数**做对照，因此 eager 慢不影响结论。

### 数据（官方导出的 FineWeb sp1024）

```bash
python data/cached_challenge_fineweb.py --variant sp1024 --train-shards 8
```

镜像地址可用 `HF_ENDPOINT=https://hf-mirror.com`（本次实测 `huggingface.co` 直连被拒，镜像可用）。

### 跑实验

```bash
cd code
python run_experiments.py --smoke      # 冒烟测试（~4 分钟）
python run_experiments.py --ablation   # 完整消融矩阵 E0~E6
python run_experiments.py --seeds      # 最佳配置 3 seed 稳定性
```

### 官方 8×H100 口径（需先拿到算力券）

```bash
RUN_ID=meteorain_c2g_full \
DATA_PATH=./data/datasets/fineweb10B_sp1024/ \
TOKENIZER_PATH=./data/tokenizers/fineweb_1024_bpe.model \
VOCAB_SIZE=1024 NUM_LAYERS=9 MODEL_DIM=512 NUM_HEADS=8 NUM_KV_HEADS=4 \
MLP_MULT=2 TIE_EMBEDDINGS=1 \
SLIDING_WINDOW_EVAL=1 EVAL_STRIDE=64 MAX_VAL_TOKENS=0 \
FP16_EMBED_PASSTHROUGH=1 PARALLEL_RESIDUAL=0 QK_GAIN_INIT=1.5 TUNED_LR=1 \
MAX_WALLCLOCK_SECONDS=600 \
torchrun --standalone --nproc_per_node=8 train_gpt.py
```

⚠️ `MAX_VAL_TOKENS=0` 表示用**完整官方验证集**，这是提交口径的硬要求。
⚠️ `QK_GAIN_INIT=1.5`（**不是** SOTA 用的 5.25）—— 我的实测显示 5.25 在浅层模型上造成 +0.008 的真实退化。**但在 9~11 层官方配置下应重新扫描 1.5 / 3.0 / 5.25，不可直接照搬我的结论。**
⚠️ fp16 嵌入在 9×512 配置下多占约 512KB，而 baseline 只剩约 136KB 余量，**必须同步缩小 MLP hidden**（上游验证过 1024→992）。**绝不能提交超 16MB 的 artifact。**

---

## 我的五项改动

**最终采纳 A + B + E**（C 收益低于噪声阈值，D 实测有害已剔除）。全部通过环境变量开关，可单独关闭做消融。

| 改动 | 开关 | 类别 | 实测Δ | 一句话说明 |
|------|------|------|------:|-----------|
| **A. 滑窗评估** ✅ | `SLIDING_WINDOW_EVAL` | 评估 | **−0.01786** | 每个 token 用接近满额上下文打分，而非平均只有 256 |
| **B. fp16 嵌入直传** ✅ | `FP16_EMBED_PASSTHROUGH` | 量化 | −0.00066 | tied embedding 同时当 embedding 和 output head，量化误差直接打到 logits |
| **C. 并行残差** ⚠️ | `PARALLEL_RESIDUAL` | 架构 | −0.00005 | attention 与 MLP 读同一份输入（GPT-J 风格）；**收益低于噪声阈值，未采纳** |
| **D. QK-gain 调优** ❌ | `QK_GAIN_INIT` | 架构 | **+0.00832** | 可学习 per-head query 缩放；**上游 5.25 在 6 层模型上有害，已剔除** |
| **E. LR/warmdown 调优** ✅ | `TUNED_LR` | 训练 | −0.00072 | warmdown 窗口太短导致低 LR 收敛时间不足 |

**每项改动都来自官方 `records/` 里已发表的实测记录**，我做了本地独立验证。详见 `docs/Meteorain_C2G_拿来说明.md`。

---

## 我明确**没有**做的（否决清单）

| 技术 | 上游收益 | 否决理由 |
|------|---------|---------|
| **SP8192 tokenizer** | -0.03~-0.05（最大）| 需重导数据，我**无法验证** BPB 计算与官方一致，而官方警告改 tokenizer 会被严格审查。**能力边界内的诚实否决。** |
| 3-layer depth recurrence | SOTA 组成 | 上游明确记录「10 分钟步数不够」；且依赖 11 层物理层 |
| Legal score-first TTT | -0.003 | 合规性无法本地验证，判违规则提交作废，风险收益不对称 |
| GPTQ / SDClip | 量化改善 | Hessian 估计正确性无法验证，边际收益低 |
| int6 QAT | artifact 更小 | 本地 artifact 远未到上限，**省空间不是瓶颈**，属过度工程 |
| SwiGLU / 高 embed LR | — | 上游实测为**负收益**，不重复踩坑 |

**原则**：优先「我能独立验证的」而非「收益最大但我验证不了的」。

---

## 核心交付物索引

| rubric 要求 | 文件 |
|------------|------|
| `*方案草案*` | [`docs/Meteorain_C2G_方案草案.md`](docs/Meteorain_C2G_方案草案.md) |
| `*方案设计*` | [`docs/Meteorain_C2G_方案设计.md`](docs/Meteorain_C2G_方案设计.md) |
| `*AI日志*` | [`docs/Meteorain_C2G_AI日志.md`](docs/Meteorain_C2G_AI日志.md) |
| `*AAR*` | [`docs/Meteorain_C2G_AAR复盘.md`](docs/Meteorain_C2G_AAR复盘.md) |
| 训练代码 | [`code/Meteorain_C2G_train_gpt.py`](code/Meteorain_C2G_train_gpt.py) |
| 消融报告 | [`docs/Meteorain_C2G_ablation.md`](docs/Meteorain_C2G_ablation.md) |
| BPB 对比表 | [`docs/Meteorain_C2G_leaderboard.md`](docs/Meteorain_C2G_leaderboard.md) |
| 拿来说明 | [`docs/Meteorain_C2G_拿来说明.md`](docs/Meteorain_C2G_拿来说明.md) |
| 训练日志 | `logs/`（每实验一份，含完整 step 曲线）|
| 提交元数据 | `submission/` |

---

## 三条工程约束（脚本已内置自检）

1. **16MB 硬约束**：训练末尾自动检查并打印 `ARTIFACT_SIZE_OK` / `ARTIFACT_SIZE_VIOLATION`。上限是**十进制 16,000,000 字节**，不是 16MiB。
2. **不用验证集调超参**：验证集只用于最终评估和「同 checkpoint 上 sliding vs chunked」对照，不用于选超参。
3. **可追溯**：每份 `submission.json` 记录全部开关状态、seed、验证集是否全集、硬件型号。

---

## 许可与来源

本项目是 OpenAI [parameter-golf](https://github.com/openai/parameter-golf) 的衍生作品，遵循其 Apache-2.0 许可。原始版权与归属见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

核心技术来源：官方 `train_gpt.py`、官方 `records/` 已发表记录、KellerJordan 的 [modded-nanoGPT](https://github.com/KellerJordan/modded-nanogpt) 与 [Muon](https://kellerjordan.github.io/posts/muon/)。