# C4D 本地大模型 Agent 技能 —— 完整交付

> **挑战**：C4D 本地大模型 Agent 技能（Local LLM Agent Skills with Gemma 4）
> **ID**：`ch-20260717031455-uzqs9k` ｜ **日期**：2026-10-06
>
>在本机运行 **Gemma 4**，构建具备**工具调用 + 双层记忆 + 多步推理**的 Agent，
> 生成交互式地图。**全程本地推理，零API 费用，数据不离开设备。**

---

## 运行结果速览

| 指标 | 实测值 |
|------|--------|
| 模型 | **Gemma 4 E4B**（7.5B 参数 / Q4_K_M 量化 / 6.1 GB） |
| 运行工具 | **Ollama v0.35.1** |
| 设备 | i5-11400H / 15.7 GB RAM / **RTX 3050（100% GPU 卸载）** |
| 推理速度 | **7.22 tok/s**（3 轮实测平均） |
| 地图标记 | **10 个地点**，坐标 100% 通过合理性校验 |
| 离线测试 | **38/38 通过** |
| API 费用 | **0 元** |

---

## 一句话原理

```
你的指令 → 本地 Gemma 4 自主调用工具 → 本地知识库提供真实坐标
        → 模型生成双语描述+JSON → 渲染成交互式腾讯地图
```

**关键设计**：模型负责"选哪些点、怎么描述、怎么分类"，
坐标作为客观地理事实由可校验的知识库提供——避免小模型的坐标幻觉。

---

## 交付物清单

对照 `CHALLENGE.md` 的提交要求：

| # | 交付物 | 说明 |
|---|--------|------|
| 1 | [方案设计](姓名_C4D_方案设计.md) | 架构、模型选型、设备信息、关键决策 |
| 2 | [Agent 技能包](姓名_C4D_agent-skill/) | 8 个模块 + 38 项测试 |
| 3 | [交互式地图](姓名_C4D_map.html) | 腾讯地图，10 个标记点 |
| 4 | [运行截图](姓名_C4D_output_screenshots/) | 7 张，覆盖挑战要求的四项证据 |
| 5 | [验证报告](姓名_C4D_验证报告.md) | 输出质量评估 + 性能数据 + 调优记录 |
| 6 | [教学说明](姓名_C4D_教学说明.md) | 从零安装到复现，零基础可跟做 |
| 7 | [AI 日志](姓名_C4D_AI日志.md) | **必交付**：7 轮迭代全过程 |
| 8 | [拿来说明](姓名_C4D_拿来说明.md) | 库/工具/参考来源 + 合规声明 |
| 9 | [AAR 复盘](姓名_C4D_AAR.md) | 做了什么/学到了什么/怎么验证的 |
| 10 | [总览](README.md) | 本文件 |

---

## Agent 能力

| rubric 信号 | 实现 |
|------------|------|
| **功能可用** | 7 个 CLI 子命令，端到端可跑通 |
| **有记忆** | SQLite 双层记忆：对话历史 + 长期事实，跨进程持久化 |
| **有技能** | 5 个工具：知识检索/坐标校验/路线规划/类别判定/时长估算 |
| 结构化输出 | JSON 模式 + 三级降级解析 + 错误回灌重试 |
| 多步推理 | ReAct 循环，工具结果回灌上下文 |

### 五个工具

| 工具 | 作用 |
|------|------|
| `get_reference` | 检索本地知识库，返回真实坐标 |
| `validate_coords` | 坐标合理性校验，返回与校园距离 |
| `plan_route` | 最近邻贪心排序，生成参观路线 |
| `classify_poi` | 关键词判定地点类别 |
| `estimate_walk` | 估算行程总时长并给出建议 |

---

## 快速复现

```bash
# 前置：已安装 Ollama 并拉取模型
ollama pull gemma4:e4b

cd 姓名_C4D_agent-skill

python -m sias_local_agent.cli doctor              # 环境自检
python tests/test_offline.py                        # 38 项离线测试
python -m sias_local_agent.cli run --task map --count 10   # 生成地图
python -m sias_local_agent.cli chat                 # 多轮对话（体验记忆）
python -m sias_local_agent.screenshots              # 生成证据截图
```

**零第三方依赖**：`pyproject.toml` 中 `dependencies = []`，
`git clone` 后无需 `pip install`。需要 **Python 3.10+**。

详见 [教学说明](姓名_C4D_教学说明.md)。

---

## 项目结构

```
C4D_交付/
├── README.md                     ← 本文件
├── 姓名_C4D_方案设计.md
├── 姓名_C4D_AI日志.md
├── 姓名_C4D_验证报告.md
├── 姓名_C4D_教学说明.md
├── 姓名_C4D_拿来说明.md
├── 姓名_C4D_AAR.md
├── 姓名_C4D_map.html              ← 交互式地图
│
├── 姓名_C4D_agent-skill/          ← Agent 技能包
│   ├── README.md
│   ├── pyproject.toml
│   ├── sias_local_agent/
│   │   ├── llm.py# Ollama 客户端
│   │   ├── memory.py             # 双层记忆
│   │   ├── tools.py              # 5 个工具
│   │   ├── knowledge.py          # 14 条本地知识库
│   │   ├── agent.py              # ReAct 主循环
│   │   ├── map_view.py           # 腾讯地图渲染
│   │   ├── cli.py                # 命令行
│   │   └── screenshots.py        # 证据生成
│   ├── tests/test_offline.py     # 38 项测试
│   ├── logs/                     ← 真实运行日志
│   └── output/                   ← 地图产物
│
├── 姓名_C4D_output_screenshots/   ← 7 张证据截图
└── _meta/                        ← 环境探测脚本
```

---

## 完成级别

| Level | 内容 | 状态 |
|-------|------|------|
| **1 Bronze** | 本地跑通 + 截图 + 设备信息 | ✅ |
| **2 Silver** | function calling + 交互式地图 + ≥5 标记 | ✅ 10 个标记 |
| **3 Gold** | 多轮对话 + 多工具 + 结构化 + 完整技能包 | ✅ |
| **4Platinum** | 模型对比报告 + 性能调优文档 | ✅ 两项 |

> **未达成项**：uncensored 模型对比（加分项）、公众号文章、手机端适配。
> 原因在 [AAR](姓名_C4D_AAR.md) 中如实说明。

---

## 合规声明

| 项 | 状态 |
|----|------|
| LLM 推理位置 | ✅ 本地 `127.0.0.1:11434` |
| 云端 LLM API | ✅ **未使用** |
| API 费用 | ✅ **0 元** |
| 地图源 | ✅ 腾讯地图（合规白名单） |
| 前端密钥暴露 | ✅ 无（密钥代理模式） |
| 坐标系 | ✅ GCJ-02 |
| 个人位置数据 | ✅ 无（仅公共场所） |

---

## 核心价值

> 云端 AI 是租来的能力，本地 AI 是你拥有的能力。
> C4D 证明你不只会**使用** AI，还会**部署** AI。

---

*所有性能数据与运行记录均来自本机真实执行，
原始日志见 `姓名_C4D_agent-skill/logs/`。*