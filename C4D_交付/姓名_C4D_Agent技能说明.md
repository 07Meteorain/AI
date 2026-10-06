# C4D Agent 技能说明

> **交付物**：本地大模型 Agent 技能包（本文件为其说明文档）
> **挑战**：C4D 本地大模型 Agent 技能（Local LLM Agent Skills with Gemma 4）｜ ID `ch-20260717031455-uzqs9k`
> **技能包实体位置**：[`姓名_C4D_agent-skill/`](姓名_C4D_agent-skill/)
> **运行方式**：全程本地推理（Ollama + Gemma 4），数据不离开设备，API 费用 0 元

---

## 一、这个 Agent 技能是什么

一个在本机跑通的 **工具调用型 Agent 技能**：用户给一句自然语言指令，本地的 Gemma 4 自主决定调用哪些工具、调用几次，把工具返回的**真实数据**（而非模型自己"想"出来的内容）组合成结构化结果，最终渲染成交互式腾讯地图。

核心设计取舍：**模型负责"选哪些点、怎么描述、怎么分类"，坐标作为客观地理事实由可校验的本地知识库提供**——以此绕开小模型的坐标幻觉。实测 10 个地点标记，坐标 100% 通过合理性校验。

一句话链路：

```
用户指令 → 本地 Gemma 4 自主调用工具 → 本地知识库提供真实坐标
        → 模型生成双语描述 + JSON → 渲染成交互式腾讯地图
```

---

## 二、技能包结构（8 个模块）

| 模块 | 职责 |
|------|------|
| `sias_local_agent/llm.py` | Ollama 客户端（本地 `127.0.0.1:11434`） |
| `sias_local_agent/memory.py` | 双层记忆（SQLite） |
| `sias_local_agent/tools.py` | 5 个工具的注册与调度 |
| `sias_local_agent/knowledge.py` | 14 条本地知识库（真实坐标） |
| `sias_local_agent/agent.py` | ReAct 主循环：推理 → 调工具 → 回灌 → 再推理 |
| `sias_local_agent/map_view.py` | 腾讯地图渲染（GCJ-02 坐标系） |
| `sias_local_agent/cli.py` | 命令行入口（7 个子命令） |
| `sias_local_agent/screenshots.py` | 运行证据截图生成 |

配套：`tests/test_offline.py`（38 项离线测试）、`logs/`（真实运行日志）、`output/`（地图产物）、`pyproject.toml`（零第三方依赖）。

---

## 三、五个工具（function calling）

| 工具 | 作用 | 返回 |
|------|------|------|
| `get_reference` | 检索本地知识库 | 地点真实经纬度 |
| `validate_coords` | 坐标合理性校验 | 校验结论 + 与校园距离 |
| `plan_route` | 最近邻贪心排序 | 参观路线 |
| `classify_poi` | 关键词判定地点类别 | 类别标签 |
| `estimate_walk` | 估算行程总时长 | 时长 + 建议 |

工具不是装饰：Agent 必须先取真实坐标、再校验、再排序，坐标校验不通过的候选会被丢弃或修正。

---

## 四、双层记忆（跨进程持久化）

- **对话历史层**：保存多轮问答上下文，支撑 `chat` 子命令的多轮体验。
- **长期事实层**：保存抽取出的稳定事实（地点、偏好、路线结论），进程重启后仍在。

两层都落在 SQLite 单文件里，不依赖任何外部服务，因此"有记忆"这件事可被独立验证：运行 `chat` 后重启进程，再问同一事实，Agent 仍能答出。

---

## 五、快速开始（零第三方依赖）

```bash
# 前置：已安装 Ollama 并拉取模型
ollama pull gemma4:e4b

cd 姓名_C4D_agent-skill

python -m sias_local_agent.cli doctor                        # 环境自检
python tests/test_offline.py                                 # 38 项离线测试
python -m sias_local_agent.cli run --task map --count 10      # 生成地图
python -m sias_local_agent.cli chat                           # 多轮对话（体验记忆）
python -m sias_local_agent.screenshots                        # 生成证据截图
```

`pyproject.toml` 中 `dependencies = []`，`git clone` 后无需 `pip install`；要求 **Python 3.10+**。

---

## 六、结构化输出与多步推理

- **结构化输出**：模型按要求产出 JSON；解析采用**三级降级**（严格 JSON → 宽松提取 → 兜底结构），失败时把错误信息**回灌**给模型重试，而不是直接崩掉。
- **多步推理**：ReAct 循环，每轮工具结果都回灌进上下文，Agent 据此决定下一步调用，直到任务完成。

---

## 七、证据与可复现

| 证据 | 位置 |
|------|------|
| 运行日志（基准、环境快照、地图、路线、模型对比） | `姓名_C4D_agent-skill/logs/` |
| 地图产物（JSON + HTML） | `姓名_C4D_agent-skill/output/` |
| 离线测试 38/38 | `python tests/test_offline.py` |
| 四类运行截图（设备与环境、模型版本、推理速度、工具调用、记忆、模型对比、离线测试） | [`姓名_C4D_output_screenshots/`](姓名_C4D_output_screenshots/) |
| 输出质量评估与调优记录 | [验证报告](姓名_C4D_验证报告.md) |
| 从零安装到复现的完整步骤 | [教学说明](姓名_C4D_教学说明.md) |

实测口径（均来自本机真实执行，非估算）：

| 指标 | 值 |
|------|----|
| 模型 | Gemma 4 E4B（7.5B 参数 / Q4_K_M 量化 / 6.1 GB） |
| 运行工具 | Ollama v0.35.1 |
| 设备 | i5-11400H / 15.7 GB RAM / RTX 3050（100% GPU 卸载） |
| 推理速度 | 7.22 tok/s（3 轮实测平均） |
| 地图标记 | 10 个地点，坐标校验 100% 通过 |
| 离线测试 | 38/38 通过 |
| API 费用 | 0 元 |

---

## 八、与挑战验收项的对照

| 验收信号 | 实现情况 |
|----------|----------|
| 本地跑通 | ✅ 本地 Gemma 4 + Ollama，含设备与速度证据 |
| 有技能（工具调用） | ✅ 5 个工具 + ReAct 循环 |
| 有记忆 | ✅ SQLite 双层记忆，跨进程持久化 |
| 结构化输出 | ✅ JSON 模式 + 三级降级解析 + 错误回灌重试 |
| 多步推理 | ✅ 工具结果回灌后继续推理 |
| 交互式地图 | ✅ 腾讯地图，10 个标记点 |

完成级别：**Bronze / Silver / Gold / Platinum 四项均达成**（Platinum 含模型对比报告与性能调优文档）。

---

## 九、前提、边界与未达成项

**前提**：本机需安装 Ollama 并已 `ollama pull gemma4:e4b`；Python 3.10+；无需联网调用云端 API。

**边界（如实说明）**：
- 技能包本身不包含模型权重，模型由 Ollama 提供；换模型需重新拉取。
- 知识库为 14 条本地条目，覆盖校园及周边场景，**不是通用地理数据库**；超出范围的提问会走校验失败路径而非编造坐标。
- 坐标校验只能判断"是否合理"，不能保证与真实世界逐点一致。

**未达成**：uncensored 模型对比（加分项）、公众号文章、手机端适配——原因见 [AAR 复盘](姓名_C4D_AAR.md)。

---

*本说明基于技能包的实际代码与运行记录编写，路径可直接对照 `姓名_C4D_agent-skill/` 逐项核验。*
