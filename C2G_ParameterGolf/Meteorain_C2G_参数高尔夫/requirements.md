# 环境依赖

本项目实测可用的依赖组合（Python 3.13.12 + Windows + CUDA 12.4）。

## 核心依赖

```
torch==2.6.0+cu124
numpy==2.5.3
sentencepiece==0.2.2
huggingface_hub==2.1.1
tqdm==4.7.1
typing_extensions==4.16.0
```

## 安装

### CUDA（推荐，用于训练）

```bash
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
pip install numpy sentencepiece huggingface_hub tqdm
```

> ⚠️ **注意**：直接 `pip install torch` 装到的是 **CPU-only** 版本（PyPI 的 Windows
> 默认轮子），`torch.cuda.is_available()` 会返回 `False`。必须指定 CUDA index。

### 数据集下载

```bash
python data/cached_challenge_fineweb.py --variant sp1024 --train-shards 8
```

若 `huggingface.co` 直连不可用（本次实测返回 502），使用镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com   # Linux/macOS
set HF_ENDPOINT=https://hf-mirror.com      # Windows cmd
```

> ⚠️ `hf-mirror.com` 可用于 API 与文件下载，但 `cdn-lfs.huggingface.co`
> （大文件融合分发节点）可能仍被阻断。因此**大文件下载可能失败**，
> 需确认镜像的 LFS 通道可用。

## 硬件与平台差异（重要）

本项目在 **单张 NVIDIA RTX 3050 Laptop GPU（4GB 显存，sm_86）** 上完成本地实验，
与赛事目标环境（8× H100 SXM，sm_90，Linux）差异较大。以下差异已由脚本自动处理：

| 差异 | 官方 8×H100 | 本地环境 | 脚本处理方式 |
|------|------------|---------|-------------|
| **Triton** | Linux 自带 | **Windows 无** | `USE_COMPILE=0` → 降级 eager |
| **flash GQA 内核** | 可用 | **不可用**（不支持 kv head 广播）| `GQA_IMPL` 自动探测 → 降级 `repeat_interleave` 展开 |
| **SDPA 后端** | 仅 flash | flash/mem_eff 不可用 | 自动回退链，mem_efficient/math 始终开启 |
| **显存** | 80GB × 8 | **4GB** | 缩小模型至 6 层 × 256 维 |
| **验证集规模** | 全量 62,021,632 tokens | 全量评估约 20+ 分钟 | `MAX_VAL_TOKENS` 取前缀（报告中标注）|
| **控制变量** | wallclock 600s | 单卡速度不可比 | **固定步数 1000 步**（等算力对照）|

### 为什么用「固定步数」而非「固定 wallclock」做对照

这是本项目实验设计的**关键决策**。

如果用固定 wallclock，那么在 eager 模式下每个实验只能跑约 500 步，
而在编译模式下能跑 1000 步——**计算量不同，所有BPB 比较全部失效**。

用固定步数后：无论多慢，每个实验都精确跑 1000 步、消耗相同的 token 数，
**唯一的变量就是要测的那个开关**。换硬件、换编译模式，结论依然成立。

## 验证环境可用性

```bash
python -c "
import torch, sentencepiece as spm
print('torch', torch.__version__, 'cuda', torch.cuda.is_available())
print('gpu', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')
sp = spm.SentencePieceProcessor(model_file='./data/tokenizers/fineweb_1024_bpe.model')
print('tokenizer vocab', sp.vocab_size())
"
```

预期输出（本地环境）：

```
torch 2.6.0+cu124 cuda True
gpu NVIDIA GeForce RTX 3050 Laptop GPU
tokenizer vocab 1024
```