# Third-Party Notices

本项目 **Meteorain_C2G_参数高尔夫** 是 [OpenAI Parameter Golf](https://github.com/openai/parameter-golf)
的衍生作品，遵循其 **Apache License 2.0** 许可。

原仓库许可证副本见 [`LICENSE`](LICENSE)。

---

## OpenAI Model Craft Challenge: Parameter Golf

- 来源：https://github.com/openai/parameter-golf
- 许可：Apache License 2.0
- 版权：OpenAI

### 本项目使用/改编的部分

| 文件 / 机制 | 用途 | 改编程度 |
|------------|------|---------|
| `train_gpt.py` — `load_data_shard` / `TokenStream` / `DistributedTokenLoader` | `.bin` 数据读取与分布式分发 | **原样保留，未改一行** |
| `train_gpt.py` — `build_sentencepiece_luts` | BPB 计算所需的字节数LUT | **原样保留，未改一行**（核心指标，官方警告此类代码易引入 bug）|
| `train_gpt.py` — `Muon` / `zeropower_via_newtonschulz5` | Muon 优化器 | **原样保留，未改一行** |
| `train_gpt.py` — `RMSNorm` / `CastedLinear` / `Rotary` / `CausalSelfAttention` / `MLP` | 基础 Transformer 算子 | 保留结构；`CausalSelfAttention` 增补 GQA 后端自动降级 |
| `train_gpt.py` — `GPT` / `Block` | 模型主体 | 增补并行残差分支（`Block.forward`）|
| `train_gpt.py` — `quantize_float_tensor` / `dequantize_state_dict_int8` | per-row int8 量化 | 增补 fp16 直传白名单分支 |
| `train_gpt.py` — `eval_val`（分块评估） | 基线评估 | 重构为 `eval_val_chunked`，逻辑等价 |
| `train_gpt.py` — 训练循环 / warmdown 逻辑 / artifact 大小计算 | 训练骨架 | 保留 |

### 引用的官方已发表记录（`records/` 目录）

以下记录为 OpenAI 公开仓库中的已发表内容，本项目**引用其结论与思路**，并在本地独立验证：

| 记录 | 引用内容 |
|------|---------|
| `records/track_10min_16mb/2026-03-19_SlidingWindowEval` | `eval_val_sliding` 实现思路（第 837–931 行）与实测结论 |
| `records/track_10min_16mb/2026-03-18_FP16Embed_WD3600` | fp16 嵌入直传思路、缩 MLP hidden 腾空间手法、负收益记录 |
| `records/track_10min_16mb/2026-04-09_SP8192_3LayerRecur_ParResid_QK525_LegalTTT` | 并行残差（GPT-J 风格）与 QK-gain 做法 |
| `records/track_10min_16mb/2026-04-08_SP8192_ParallelResid_ScoreFirstTTT` | 并行残差的交叉验证 |
| `records/track_10min_16mb/2026-03-17_NaiveBaseline` | 基线配置与 BPB 参考值 |

**本项目没有复制上述记录的 `train_gpt.py` 全文**。所有代码均以官方主`train_gpt.py` 为基座编写，
仅在必要时参考上述记录的**技术思路**（并在代码注释与 `docs/Meteorain_C2G_拿来说明.md` 中逐项标注）。

### 数据集

- FineWeb sp1024 训练/验证分片与 tokenizer 来源：HuggingFace 数据集
  [`willdepueoai/parameter-golf`](https://huggingface.co/datasets/willdepueoai/parameter-golf)
- FineWeb 原始数据集：https://huggingface.co/datasets/HuggingFaceFW/fineweb
- **本项目仅使用验证集进行评估，未在训练中访问验证集**（符合赛事规则）。

---

## KellerJordan/modded-nanogpt

- 来源：https://github.com/KellerJordan/modded-nanogpt
- 许可：MIT License
- 版权：© 2024 Keller Jordan

MIT License

Copyright (c) 2024 Keller Jordan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### 引用内容

| 内容 | 说明 |
|------|------|
| Muon 优化器 / Newton-Schulz 正交化 | 经官方 `train_gpt.py` 转手使用；背景见 https://kellerjordan.github.io/posts/muon/ |
| `relu²` MLP | 官方 `MLP` 类的来源 |
| QK-Norm（注意力 logit 归一化） | 官方 `CausalSelfAttention` 的来源 |
| U-Net 式skip 连接 | 官方 `GPT.forward` 的结构来源 |

---

## 第三方依赖

| 依赖 | 许可 | 用途 |
|------|------|------|
| [PyTorch](https://github.com/pytorch/pytorch) | BSD-3-Clause | 张量运算与分布式训练 |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause | `.bin` 数据读取 |
| [SentencePiece](https://github.com/google/sentencepiece) | Apache-2.0 | 分词器与 BPB 字节数统计 |
| [huggingface-hub](https://github.com/huggingface/huggingface_hub) | Apache-2.0 | 数据集下载 |
| [tqdm](https://github.com/tqdm/tqdm) | MPL-2.0 / MIT | 进度显示 |

完整依赖见 `requirements.txt`。

---

## 本项目的新增内容声明

以下部分为本项目**新增**，不属于上述任何来源：

1. `eval_val_chunked` 与 `eval_val_sliding` 的**双路径重构**及开关机制
2. fp16 嵌入直传的**可配置白名单**机制（`FP16_PASSTHROUGH_PATTERNS`）
3. **并行残差**的可配置实现（`PARALLEL_RESIDUAL` / `PARALLEL_RESIDUAL_START`）
4. **GQA 后端自动探测与降级**（`GQA_IMPL` / `probe_fused_gqa` / SDPA 回退链）
5. **Triton 缺失时的 eager 降级**（`USE_COMPILE`）
6. **16MB artifact 自动自检**（`ARTIFACT_SIZE_OK` / `ARTIFACT_SIZE_VIOLATION`）
7. **验证集规模显式标注**（`MAX_VAL_TOKENS` + `val_set_is_full_official`）
8. 消融实验驱动脚本 `run_experiments.py` 及全部实验矩阵设计
9. 全部文档：`docs/` 下7 份报告

---

*最后更新：2026-10-05 · 07Meteorain*