# C10H · 安装并驾驭 Hermes Agent

> 一台 4 GB 显存的 Windows 笔记本，没有云端 API Key，GitHub API 还被限流。
> 在这个条件下把 Nous Research 的 **Hermes Agent** 装起来，配成本地 64k 上下文的工具型 agent，并用**原始轨迹**证明它真的能读文件、写文件、记东西、建技能。

| 项 | 内容 |
| --- | --- |
| 挑战编号 | C10H |
| 挑战 ID | `ch-20260717031609-rnur5a` |
| 课程 | `aix-course-elite20` |
| 记录 ID | `recvpB3s1xN9uv` |
| 交付形态 | 独立目录 `C10H_HermesAgent/`，文档 + 可复跑脚本 + 原始轨迹 |
| 安装环境 | Windows 11 22621 / i5-11400H / 15.7 GB RAM / RTX 3050 4 GB |
| Hermes 版本 | v0.23.1 · commit `3b4215785882` |
| 模型 | Ollama `gemma4-e2b-64k`（4.6B Q4_K_M，num_ctx 65536） |

---

## 30 秒验证

```powershell
$env:HERMES_HOME='E:\hermes'

E:\hermes\bin\hermes.exe --version      # v0.23.1
E:\hermes\bin\hermes.exe doctor         # 核心项全绿
E:\hermes\bin\hermes.exe gateway status # ✓ running（没有就先 gateway run）

cd C10H_HermesAgent\demo
.\run_demo.ps1 -Scenario 01             # 真实读写文件，exit_code=0
```

不想跑？直接看这三份：

- [`demo/transcripts/01_summary.md`](demo/transcripts/01_summary.md) —— 4 次工具调用的完整轨迹；
- [`安装记录/安装记录.md`](安装记录/安装记录.md) —— 9 个真实故障与修复；
- [`复盘/AAR复盘.md`](复盘/AAR复盘.md) —— 为什么差点交了一个假 demo。

---

## 结果摘要

| 指标 | 结果 |
| --- | --- |
| 安装 | 成功；v0.23.1，PM 运行时 Python 3.14.9，Node 26.12.1，Chromium 1208 |
| 配置 | `custom` provider + Ollama `/v1`，64k 上下文，100% GPU |
| 工具调用 | `read_file` / `write_file` / `terminal` / `memory` / `skill_manage` 全部实跑成功 |
| demo | 4 个场景，全部 `exit_code=0`，共 10 次工具调用 |
| 记忆 | `USER.md` 真实写入 57 字符，新会话可读 |
| 技能 | 44 个 bundled + 1 个自建 `c10h-delivery-check` |
| 排错 | 9 个安装/配置故障 + 1 个模型幻觉，全部留证据 |
| AI 协作 | 14 轮迭代，prompt 从「只给任务」到「四件套」 |

**最重要的一条**：第一次 demo 时，模型声称写入了 `out/summary.md`，但文件根本不存在。加上「写完必须 `read_file` 回读」之后才成功。这件事直接改变了整个交付的设计——**所有结论都必须有可检查的副作用**。

---

## 交付物地图

| 文件 | 内容 | 对应评分 |
| --- | --- | --- |
| [`README.md`](README.md) | 本文件：总览、验证、结构、边界 | 产物完整性 |
| [`提交说明.md`](提交说明.md) | 要求对照、阅读顺序、红旗自查 | 产物完整性 |
| [`安装记录/安装记录.md`](安装记录/安装记录.md) | 时间线、9 个故障、版本与哈希、验收命令 | 安装记录 / 驾驭程度 |
| [`配置说明/配置说明.md`](配置说明/配置说明.md) | config 逐项解释、模型、人格、记忆、技能、网关、安全 | 配置说明 / 集成质量 |
| [`配置说明/配置模板/`](配置说明/配置模板/) | `config.yaml.example`、`.env.example`、`Modelfile` | 可复现 |
| [`demo/`](demo/) | 4 个场景的 prompt、原始 JSONL、可读 Markdown、复跑脚本 | demo / 可运行 |
| [`AI日志/AI使用日志.md`](AI日志/AI使用日志.md) | 14 轮记录、prompt 迭代、失败清单、人机分工 | AI 使用质量 |
| [`复盘/AAR复盘.md`](复盘/AAR复盘.md) | 预期 vs 实际、5 Whys、改进方案、方法论、自评 | 复盘质量 |
| [`排错/排错手册.md`](排错/排错手册.md) | 10 个故障：症状/根因/修复/预防 | 驾驭程度 |
| [`扩展/`](扩展/) | SOUL 人格、自建技能、64k 上下文、demo 协议 | 个性化扩展 |
| [`证据/`](证据/) | doctor、版本、日志、失败样本、技能与记忆原文 | 可追溯性 |

---

## 目录结构

```
C10H_HermesAgent/
├── README.md                  # 你在这里
├── 提交说明.md
├── 安装记录/
│   └── 安装记录.md
├── 配置说明/
│   ├── 配置说明.md
│   └── 配置模板/{config.yaml.example, .env.example, Modelfile}
├── demo/
│   ├── README.md
│   ├── run_demo.ps1
│   ├── prompts/               # 01–04 原始 prompt
│   ├── transcripts/           # 原始 JSONL + 渲染后的 Markdown
│   ├── tools/render_transcript.py
│   └── workspace/             # 沙盒：project/ + out/
├── AI日志/AI使用日志.md
├── 复盘/AAR复盘.md
├── 排错/排错手册.md
├── 扩展/{扩展说明.md, SOUL-阿赫.md, skill-c10h-delivery-check/}
└── 证据/                      # doctor、日志、失败样本、版本
```

---

## 为什么这样设计

1. **安装到 E 盘**：C 盘只剩 16 GB，而 Node + Chromium + 模型缓存很快超过 3 GB；官方安装器支持 `-InstallDir/-HermesHome`。
2. **用 Ollama 而不是云 API**：没有可用的云端 key，也不应该借别人的；本地模型让 demo 完全离线、可复现。
3. **把上下文拉到 64k**：Hermes 的系统提示 + 工具 schema 就有 2–4 万 token，Ollama 默认 2048 会让模型「看不见工具」。
4. **demo 保留 JSONL**：截图可以 P，JSONL 里的 `tool_use/result/exit_code` 更难伪造。
5. **失败样本不删**：`证据/失败-01-幻觉写入.jsonl` 是这次交付里最有信息量的文件。

---

## 评分维度对照

| 维度 | 证据 |
| --- | --- |
| 驾驭程度（25） | 9 个故障的根因分析、10 条排错手册、SOUL/技能/上下文三类扩展、`doctor` 全绿 |
| 集成质量（20） | 与 Ollama / Git Bash / PM 运行时 / DSH 环境适配；配置模板可复现；密钥隔离 |
| 产物完整性（15） | README/安装/配置/demo/AI日志/AAR/排错/证据齐全；demo 一键复跑 |
| AI 使用质量（20） | 14 轮迭代、prompt v1→v2 对比、原始轨迹、失败与修正、人机分工 |
| 复盘质量（20） | 预期 vs 实际、5 Whys 追到「验收设计」、可执行改进、含失败经验 |

---

## 边界

- **消息平台未接入**：没有 bot token；gateway 只验证了「能启动、无平台」，配置方法见 `配置说明` 第 8 节。
- **模型能力有限**：4.6B 在路径、复杂多步任务上会出错；demo 03 第一版把记忆路径答错，第二版靠「允许说不知道」修正。
- **`hermes update` 未验证**：GitHub API 403；恢复网络后可补测。
- **未用 Docker 后端**：本机没有 Docker；`terminal.backend: local` 的风险已在配置说明标注。

---

## 来源

- Hermes Agent 官方文档：<https://hermes-agent.nousresearch.com/docs>
- GitHub：<https://github.com/NousResearch/hermes-agent>
- 挑战原文：`../挑战说明.md`、`../challenge.json`
