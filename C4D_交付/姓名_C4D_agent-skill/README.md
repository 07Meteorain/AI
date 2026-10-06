# C4D 本地大模型 Agent 技能 · sias-local-agent

> 一个**完全离线**运行的地图与规划 Agent。所有推理由本机 GPU/CPU 上的
> Gemma 4 完成，**不调用任何云端 LLM API，零 API 费用**。

---

## 这是什么

C4D（Local LLM Agent Skills）挑战的完整交付：把一个大模型跑在自己的电脑上，
并让它真正做事——而不是只会聊天。

```
你的指令
   ↓
本地 Gemma 4（Ollama，无网络推理）
   ↓ 自主决定调用哪个工具
工具层：本地知识库检索 / 坐标校验 / 路线规划 / 类别判定 / 时长估算
   ↓
结构化 JSON 输出
   ↓
交互式地图 HTML（腾讯地图，零成本可分享）
```

## 亮点

| 能力 | 实现 | 证据 |
|------|------|------|
| **原生函数调用** | Ollama `tools` 端点，模型自主选工具 | `logs/run_map.json` 的 `steps[].tool` |
| **结构化输出** | JSON 模式 + 三级降级解析 + 错误回灌重试 | `llm.py: structured()` |
| **有记忆** | SQLite 双层记忆（对话历史 + 长期事实），跨进程持久化 | `memory.py`，`logs/chat_transcript.json` |
| **多步推理** | ReAct 循环，最多 6 步，工具结果回灌上下文 | `agent.py: LocalAgent.run()` |
| **多工具** | 5 个工具，覆盖检索/校验/规划/分类/估算 | `tools.py: build_registry()` |
| **零第三方依赖** | 全部标准库，`git clone` 后直接跑 | `pyproject.toml: dependencies = []` |
| **38 项离线测试** | 不需要模型即可验证全部核心逻辑 | `tests/test_offline.py` |

## 快速开始

### 前置条件

1. 安装 [Ollama](https://ollama.com/download)（Windows / macOS / Linux）
2. 拉取模型：
   ```bash
   ollama pull gemma4:e4b     # 16GB 内存笔记本推荐
   # ollama pull gemma4:e2b   # 8GB 内存 / 旧电脑
   ```
3. 确认服务在跑：`curl http://localhost:11434/api/tags`

### 运行

```bash
cd 姓名_C4D_agent-skill

# 环境自检（会打印设备信息 + 一次真实推理的 tok/s）
python -m sias_local_agent.cli doctor

# 生成交互式地图（核心任务）
python -m sias_local_agent.cli run --task map --count 10

# 规划一条多站行程（会真实调用多个工具）
python -m sias_local_agent.cli run --task plan --count 6

# 多轮对话，验证记忆
python -m sias_local_agent.cli chat

# 性能基准
python -m sias_local_agent.cli bench --rounds 3

# 模型对比（Level 4 加分项）
python -m sias_local_agent.cli compare --models gemma4:e2b gemma4:e4b
```

产物位置：

- `output/sias_map.html` — 交互式地图（浏览器直接打开）
- `logs/*.json` — 完整推理轨迹、工具调用记录、性能数据
- `data/memory.db` — 记忆数据库

### 测试

```bash
python tests/test_offline.py     # 无需模型，38 项
# 或
python -m pytest tests/ -v
```

## 项目结构

```
姓名_C4D_agent-skill/
├── pyproject.toml              # 打包配置（零运行时依赖）
├── README.md                   # 本文件
├── sias_local_agent/
│   ├── __init__.py
│   ├── llm.py                  # Ollama 客户端：对话/结构化输出/function calling
│   ├── memory.py               # 双层记忆：对话历史 + 长期事实（SQLite）
│   ├── tools.py                # 5 个工具的注册表与实现
│   ├── knowledge.py            # 本地知识库（真实坐标，杜绝幻觉）
│   ├── agent.py                # ReAct 主循环 + function calling 路由
│   ├── map_view.py             # 腾讯地图 HTML 渲染 + 输出归一化
│   └── cli.py                  # 命令行入口（7 个子命令）
├── tests/
│   └── test_offline.py         # 38 项离线测试
├── logs/                       # 运行日志（由程序自动生成）
└── output/                     # 地图与行程产物
```

## 设计取舍（为什么这么做）

**为什么给模型提供真实坐标，而不是让它自己编？**
4B 级别模型对真实经纬度的记忆很不可靠，直接让它凭空生成会产出
「幻觉坐标」（比如把郑州标到北京）。所以我把职责拆开：
知识库提供**事实**（坐标），模型负责**生成**（选点、双语描述、分类、结构化）。
这既满足「数据由模型生成」的要求，又避免了错误——
`tools.validate_coords` 会在生成后再做一次兜底校验。
这一取舍在《验证报告》里有详细讨论。

**为什么用腾讯地图而不是 Leaflet + OSM？**
国内地图服务的合规要求。本项目不使用 Google Maps / OSM / Mapbox。
默认走腾讯地图官方密钥代理模式，前端不暴露任何密钥。

**为什么零第三方依赖？**
挑战的评审维度里有「可复用性：别人照着说明能跑通吗」。
`git clone` 之后不需要 `pip install` 就能跑，是降低复现门槛最有效的方式。

## 许可

MIT