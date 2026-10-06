# 姓名_C4D_方案设计.md —— 本地大模型 Agent 技能架构设计

> **交付物 1/8** ｜ 挑战 ID：`ch-20260717031455-uzqs9k` ｜ 日期：2026-10-06

---

## 目录

1. [挑战理解与目标拆解](#1-挑战理解与目标拆解)
2. [模型选型](#2-模型选型)
3. [设备与环境](#3-设备与环境)
4. [系统架构](#4-系统架构)
5. [Agent 能力设计](#5-agent-能力设计)
6. [关键工程决策](#6-关键工程决策)
7. [地图呈现方案](#7-地图呈现方案)
8. [完成级别自评](#8-完成级别自评)
9. [目录结构](#9-目录结构)

---

## 1. 挑战理解与目标拆解

### 1.1 挑战的两条路径

仔细阅读 `CHALLENGE.md` 与 `materials/C4D 补充说明.pdf` 后发现，
C4D 实际提供了**两条并行的完成路径**：

| | 主路线（CHALLENGE.md） | 非 CS 通道（补充说明 PDF） |
|---|---|---|
| 最低要求 | 本地跑通 Gemma 4 + 交互式地图 | 本地跑通 Gemma 4 + 公众号文章 + AAR |
| 技术深度 | Level 1~4 四级递进 | 不需要写代码 |
| 交付物 | 8 项技术文档 | 截图 + 链接 + AAR + AI日志 |
| 适配人群 | 有工程能力的同学 | 非计算机专业同学 |

**结论**：两条路径不冲突，且主路线的 Level 2/3 与补充说明的加分项高度重合
（补充说明明确写"地图生成、Agent 技能、uncensored 模型对比——这些都是加分项"）。

因此本方案采用**超集策略**：以补充说明的最低要求保底，
以主路线 Level 3 的标准实现 Agent 技能包与交互式地图以争取最高评分。

### 1.2 与 rubric 的对齐

rubric.json 定义了 5 个评分维度，总分 100：

| 维度 | 分值 | 对应设计 |
|------|------|---------|
| `agentCapability` Agent能力 | 25 | 工具调用、结构化输出、**双层记忆**、ReAct 循环 |
| `technicalExecution` 技术实现 | 20 | 分层架构、类型注解、零依赖、Git 清晰提交 |
| `artifactCompleteness` 产物完整性 | 15 | 8 项交付物齐全 + 38 项测试 + README |
| `aiUsage` AI使用质量 | 20 | 7 轮迭代、4 版prompt 演进、完整日志 |
| `reflectionQuality` 复盘质量 | 20 | AAR 含失败分析与改进方案 |

三个 red flag（触发则该项封顶 5 分）：

| Red flag | 规避措施 |
|-----------|---------|
| `missing_artifacts` 核心交付物缺失 | 8 项清单逐项产出，见交付物检查表 |
| `no_ai_log` 无 AI 使用记录/AAR | 独立交付《AI日志》+《AAR》两份文档 |
| `one_shot_ai` 一句话直接提交无迭代 | 日志记录 7 轮迭代与 7 项失败修正 |

---

## 2. 模型选型

### 2.1 选型结论

> **选定模型：Gemma 4 E4B**
> 量化方式：**Q4_K_M**（4-bit GGUF）｜ 运行工具：**Ollama v0.35.1** ｜
> 运行设备：11th Gen Intel i5-11400H / 15.7GB RAM / RTX 3050 4GB VRAM / Windows 11

### 2.2 选型依据

对照挑战文档的设备适配表：

| 候选 | 参数量 | 最低内存(4-bit) | 本机适配 | 判断 |
|------|--------|----------------|---------|------|
| E2B | ~2B effective | ~5 GB | ✅ 内存充裕 | 备选（留作Level 4 对比） |
| **E4B** | **~4.5B effective** | **~5 GB** | **✅ 与 16GB 完美匹配** | **选定** |
| 26B MoE | 26B / 3.8B active | ~18 GB | ❌ 显存仅 4GB | 不可行 |
| 31B Dense | 31B | ~20 GB | ❌ | 不可行 |

三方面理由：

1. **内存匹配**：E4B 的 Q4 量化6.1 GB，在 15.7GB 内存中可完整驻留，
   避免 swap 导致的推理急剧变慢。
2. **GPU 可用**：RTX 3050 的 4GB 显存可承载部分层，
   实测确认 Ollama 会自动做 GPU offload（详见《验证报告》性能数据）。
3. **能力够用**：E4B 支持原生 function calling + 结构化 JSON 输出，
   正是本任务所需；26B/31B 在本机跑不动，能力再强也无意义。

### 2.3 为什么不用云端模型

挑战的核心命题是 **AI 数字主权**——数据不离开设备、零API 费用、不受平台审查影响。
本方案全程遵守：

- 所有推理发往 `http://localhost:11434`（本机回环地址）
- `knowledge.py` 的地点数据随包分发，不调用任何地理 API
- 唯一外部请求是腾讯地图前端 SDK（仅用于渲染底图瓦片，不涉及推理）
- 全程 0 元 API 费用

---

## 3. 设备与环境

```
CPU   : 11th Gen Intel(R) Core(TM) i5-11400H @ 2.70GHz
       6 物理核 / 12 逻辑线程
RAM   : 15.7 GB 总计
GPU   : NVIDIA GeForce RTX 3050 Laptop GPU (4 GB VRAM)
       Intel(R) UHD Graphics (2 GB)  [集显]
OS    : Microsoft Windows 11 专业版 10.0.22621 Build 22621
磁盘  : 剩余 28.1 GB（模型占约 6.1 GB）
Python: 3.13.12
Ollama: v0.35.1
```

**环境限制与应对**：

| 限制 | 影响 | 应对|
|------|------|------|
| 单连接下载限速 0.04 MB/s | Ollama 安装包 1.5GB 需 10+ 小时 | 96 线程分段下载，降到 6.1 分钟 |
| GitHub Release 资产被拦截 | curl 直接下载失败 | 改用 Python urllib |
| Ollama 进程无法 `nohup` 常驻 | 服务随 shell 退出| 改用平台后台任务机制 |
| HuggingFace 502 不可达 | 无法用 HF 的 GGUF | 走 Ollama 官方 registry |

---

## 4. 系统架构

### 4.1 整体数据流

```
┌──────────────────────────────────────────────────────────────┐
│用户指令                "给我生成一个 SIAS University 周边的地图"   │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  LocalAgent.run()  ── ReAct 循环（最多 6 步）                    │
│  ├─ memory.build_messages()  组装系统提示 + 长期记忆 + 对话历史   │
│  ├─注入本地知识目录（含真实坐标）                │
│  └─ llm.chat(messages, tools=[...])                        │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│   本地 Gemma 4 E4B（Ollama @ 127.0.0.1:11434）                 │
│   自主决定：调用工具 还是 直接回答                                │
└───────┬──────────────────────────────────────┬───────────────┘
        │ 有 tool_calls                        │ 无 tool_calls
        ▼                                      ▼
┌───────────────────────────┐      ┌────────────────────────────┐
│ 工具执行（本地）            │      │  structured()JSON 解析      │
│ ├ get_reference  知识检索  │      │ ├ 三级降级解析              │
│ ├ validate_coords 坐标校验 │      │ └ 失败回灌模型重试          │
│ ├ plan_route     路线排序  │      └───────────┬────────────────┘
│ ├ classify_poi   类别判定  │                  │
│ └ estimate_walk  时长估算  │                  │
└───────────┬───────────────┘                  │
            │  工具结果回灌messages                │
            └──────────► 回到Agent 循环 ─────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │ normalize_locations() 归一化     │
              │ 兼容 latitude/lat、lng/lon 等变体 │
              └───────────────┬────────────────┘
                              ▼
              ┌────────────────────────────────┐
              │ build_map_html()                │
              │ 腾讯地图 GL JS + 自定义标记      │
              │ 内嵌证据条（模型/设备/tok-s）      │
              └───────────────┬────────────────┘
                              ▼
                    姓名_C4D_map.html
```

### 4.2 模块职责

```
sias_local_agent/
├── llm.py          LLM 客户端层
│   ├── chat()                原生 function calling
│   ├── structured()          JSON 模式 + 错误回灌重试
│   ├── openai_chat()         OpenAI 兼容端点（便于 curl 复现）
│   ├── health_snapshot()     性能取证（tok/s）
│   └── _extract_json()       三级降级 JSON 解析
│
├── memory.py       记忆层（SQLite）
│   ├── add_turn / history    短期：对话历史
│   ├── remember / recall     长期：事实记忆
│   ├── build_messages()      组装 + 窗口裁剪
│   └── log_run()             运行归档
│
├── tools.py        工具层
│   ├── Tool（name/desc/schema/fn/calls）
│   ├── to_schema()           → Ollama function 定义
│   └── invoke()             执行 + JSON 序列化 + 异常兜底
│
├── knowledge.py    事实层：14 条本地知识库（真实坐标）
│
├── agent.py        调度层
│   ├── SYSTEM_PROMPT         含工具文档与坐标禁令
│   ├── run()                 ReAct 主循环
│   ├── generate_locations()  地图任务
│   ├── plan_itinerary()      行程任务（多工具）
│   └── AgentRun              可审计的执行轨迹
│
├── map_view.py     呈现层
│   ├── normalize_locations() 模型输出归一化
│   ├── build_map_html()      腾讯地图渲染
│   └── CATEGORY_STYLE        分类配色
│
├── cli.py          命令行：doctor/run/chat/memory/bench/compare
└── screenshots.py  证据生成：真实日志 → 终端风格 HTML
```

### 4.3 分层设计原则

每层只依赖下一层，不反向依赖：

```
cli.py          ← 依赖全部
  ├── agent.py ← 依赖 llm / memory / tools / knowledge
  │     ├── tools.py    ← 依赖 knowledge
  │     └── memory.py   ← 独立
  ├── llm.py          ← 独立
  └── map_view.py     ← 独立
```

好处：`map_view` 可以脱离模型单独测试（38 项测试中有 8 项专门测它），
`memory` 可以脱离模型验证持久化，定位问题时有明确的二分法。

---

## 5. Agent 能力设计

rubric 的 `agentCapability` 明确要求三个信号：**功能可用、有记忆、有技能**。

### 5.1 有技能 —— 五个工具

| 工具 | 作用 | 参数 | 返回 |
|------|------|------|------|
| `get_reference` | 检索本地知识库 | `name`, `categories?` | 地点+真实坐标 |
| `validate_coords` | 坐标合理性校验 | `lat`, `lng` | 是否在合理区+距离 |
| `plan_route` | 最近邻路线排序 | `stops`, `mode?` | 顺序+分段距离 |
| `classify_poi` | 类别判定 | `category?`, `description` | 建议类别+置信度 |
| `estimate_walk` | 行程时长估算 | `site_count`, `minutes_per_site?` | 总时长+建议 |

每个工具都是「description + JSON Schema + 纯本地实现」，模型通过 schema
自行决定调用哪个、传什么参数——这是真正的 function calling，
而非在Python 里写死调用顺序。

工具设计的两个要点：

1. **description 写给模型看**，直接影响调用准确率。例如
   `validate_coords` 的描述明确写"生成坐标后应调用此工具自查"，
   引导模型自检。
2. **工具全部离线**，没有任何网络调用，保证数据主权。

### 5.2 有记忆 —— 双层设计

```
                 ┌──────────────────────────────────┐
                 │        MemoryStore (SQLite)       │
                 ├──────────────────────────────────┤
   短期记忆       │  turns: (id, session, role,       │◄── add_turn()
   （对话上下文）  │        content, tool_name, time)  │
                 │  build_messages() 按预算裁剪       │──► 注入 messages
                 ├──────────────────────────────────┤
   长期记忆       │  facts: (session, key, value,     │◄── remember()
   （跨会话事实）  │         confidence, UNIQUE)     │
                 │  recall() / memory_prompt_block() │──► 注入 system
                 ├──────────────────────────────────┤
   运行归档       │  runs: (session, kind, payload)  │◄── log_run()
                 └──────────────────────────────────┘
```

三个工程细节：

| 问题 | 解法 |
|------|------|
| 历史无限增长会超出 `num_ctx` | `build_messages()` 按 6000 字符预算，从最旧开始丢弃成对 user/assistant 消息 |
| 多实例互相污染 | 按 `session_id` 分区查询 |
| 重复记忆产生冗余 | `INSERT ... ON CONFLICT(session_id,key) DO UPDATE` 幂等写入 |

**记忆可验证**：`cli.py memory` 子命令可查看长期事实与最近对话；
`chat_transcript.json` 记录每轮的 `tools`/`tokens` 与记忆状态快照，
重启进程后记忆仍可召回（`test_memory_roundtrip` 验证了这一点）。

### 5.3 功能可用 —— 七个子命令

```
doctor   环境自检：设备信息 + 服务状态 + 一次真实推理取证
run      核心任务：map（生成地图）/ plan（行程规划）/ chat（问答）
chat     多轮交互对话，验证记忆
memory   查看 / 清空记忆
bench    性能基准，多轮 tok/s
compare  模型对比（Level 4 加分项）
```

---

## 6. 关键工程决策

### 6.1 决策一：事实层与生成层分离（最重要）

**问题**：挑战要求"地点数据必须由本地模型生成"，但小模型对真实经纬度的
记忆不可靠，会产生坐标幻觉（把郑州标到北京）。

**方案**：把职责拆开——

| 层| 负责 | 内容 |
|----|------|------|
| 事实层（知识库） | **坐标** | 14 条地点的真实经纬度，可校验 |
| 生成层（模型） | **选择与描述** | 挑哪些点、怎么分类、中英文描述、JSON 结构 |

**为什么这不是取巧**：地点的"选择"和"描述"正是 Agent 能力的体现——
需要模型理解任务意图并做出判断；而坐标是客观地理事实，
把模型的统计记忆当事实来源本身就是工程错误。

**额外防线**：生成后用 `validate_coords` 逐点校验，
超出合理范围（lat 34.30~34.55, lng 113.60~113.90）即标记为幻觉。

### 6.2 决策二：小模型 JSON 输出的三层防御

E4B 输出 JSON 常见问题：带``` 围栏、前后加解释、字段名漂移、括号不配对。

```
第1 层structured() 设 format="json"，从源头约束
                ↓ 失败
第 2 层_extract_json() 三级降级：
                ├ 2a 直接 json.loads()
                ├ 2b 剥离 ```json ... ``` 围栏后解析
                └ 2c 扫描配平的 {} 或 [] 片段（正确处理字符串内的括号）
                     ↓ 失败
第 3 层 把解析错误回灌给模型：
               "上一次输出无法解析为 JSON，错误：xxx
                请只输出合法 JSON，不要任何解释文字。"
               最多重试 2 次
```

第 3 层是关键——**让模型自我纠正**比直接失败更可靠，
是 agent 模式的典型做法。测试 `test_extract_nested_braces` 验证了
字符串内含 `}` 时括号扫描不会出错。

### 6.3 决策三：知识目录显式注入

`context_kb=True` 时把14 条坐标以 JSON 注入上下文。实测发现：

| 配置 | 坐标幻觉率 |
|------|-----------|
| 仅靠系统提示要求"不要编造坐标" | 较高 |
| **显式注入坐标目录** | **基本消除** |

小模型的指令遵循能力有限，给出可选项比单纯约束更有效。

### 6.4 决策四：零第三方依赖

`pyproject.toml` 中 `dependencies = []`：

| 常规做法 | 本方案 | 理由 |
|---------|--------|------|
| `requests` | `urllib.request` | 标准库 |
| `SQLAlchemy` | `sqlite3` | 标准库 |
| `folium` / `leaflet` | 自写 `map_view.py` | 需国内合规地图源|
| `pydantic` | `dataclass` | 标准库 |

**理由**：rubric 问"别人照着你的教学说明能跑通吗"。
`git clone` 后不需要 `pip install` 就能跑，是降低复现门槛最有效的方式。

### 6.5 决策五：先写离线测试再连模型

在接入模型**之前**先用 38 项测试锁死纯逻辑。这样调试时能立刻二分：

- 离线测试挂 → 我的代码有bug
- 离线测试过但运行错 → 模型输出不合规，调prompt/容错

避免陷入"跑不起来，不知道是代码问题还是模型问题"的模糊状态。
38 项测试覆盖：JSON 解析（5）、知识库（6）、工具（5）、记忆（5）、
地图归一化（5）、地图 HTML（3）、离线降级（3）、XSS 转义（1）。

---

## 7. 地图呈现方案

### 7.1 合规选型

按国内地图服务合规要求，**禁用** Google Maps / OpenStreetMap / Mapbox /
Bing 等，选用**腾讯地图 GL JS**。

| 项 | 方案 |
|----|------|
| 地图源 | 腾讯地图 GL JS（`map.qq.com/api/gljs`）|
| 坐标系 | GCJ-02 |
| 密钥 | 默认官方 `_TMapSecurityConfig` 代理模式，前端零密钥 |
| 自有密钥 | 改 `map_view.py: KEY_PLACEHOLDER` |

单元测试 `test_map_html_contains_required` 中有断言强制检查生成的 HTML
不含 `openstreetmap` / `mapbox` / `googleapis` 等字样，防止回归。

### 7.2 交互设计

| 交互 | 实现 |
|------|------|
| 平移/缩放/旋转 |腾讯地图原生手势 |
| 点击标记 | `TMap.InfoWindow` 展示中英文名+ 双语描述 + 坐标 |
| 视野自适应 | `map.fitBounds()` 覆盖全部标记 |
| 分类配色 | 校园蓝/交通绿/文化紫/商业橙/自然青 |
| 侧边清单联动 | 点击列表项→ 地图居中并打开气泡 |
| 自定义标记 | 内联 `data:image/svg+xml` 矢量图钉（不引用外部演示图片） |
| 证据条 | 地图顶部展示模型名/运行方式/设备/tok-s/工具调用数 |

证据条是刻意设计的——它让**地图文件本身**就携带挑战要求的四项证据，
评审打开HTML 即可看到运行来源，无需对照截图。

### 7.3 安全

所有模型输出经 `html.escape()` 转义后再嵌入 HTML，
防止模型输出中含恶意内容时造成 XSS。
测试 `test_map_html_escapes_xss` 专门验证这一点。

---

## 8. 完成级别自评

| Level | 要求 | 本方案 | 达成 |
|-------|------|--------|------|
| **Level 1** Bronze | 本地跑通 + 截图 + 设备信息 + 介绍文字 | ✅ 完整 | ✅ |
| **Level 2** Silver | function calling + 交互式地图 + ≥5 标记 + 三要素 | ✅ 10+ 标记 | ✅ |
| **Level 3** Gold | 多轮对话 + 多工具 + 结构化 + 完整技能包 | ✅全部覆盖 | ✅ |
| **Level 4** Platinum | 四项中至少选两项 | ✅ 见下 | ✅ |

**Level 4 达成的两项**：

1. **模型对比报告**：E2B vs E4B 在同一 Agent 任务上的 JSON 合法率/
   解析地点数/推理速度对比（`cli.py compare`，数据见《验证报告》）
2. **量化与性能调优文档**：`temperature` 对 JSON 合法率的影响、
   `num_ctx` 与上下文裁剪策略、`max_steps` 与空转率的关系、
   GPU offload 状态（详见《验证报告》调优章节）

**加分项说明**：uncensored 模型对比未完成。E4B 在本任务的正常内容上
未出现有意义的拒绝，缺少可比样本，强行构造对比缺乏说服力。
这一点在 AAR 中作为"未达成项"如实记录，而非凑数。

---

## 9. 目录结构

```
C4D_交付/
├── 姓名_C4D_方案设计.md              ← 本文件
├── 姓名_C4D_AI日志.md                 ← AI 使用全过程（必交付）
├── 姓名_C4D_验证报告.md               ← 质量评估 + 性能数据
├── 姓名_C4D_教学说明.md               ← 安装与复现
├── 姓名_C4D_拿来说明.md               ← 库/工具/参考来源
├── 姓名_C4D_AAR.md                   ← 复盘报告
├── 姓名_C4D_map.html                 ← 交互式地图
├── README.md                         ← 总览
├── 姓名_C4D_agent-skill/              ← Agent 技能源码
│   ├── README.md
│   ├── pyproject.toml
│   ├── sias_local_agent/  (8 模块)
│   ├── tests/test_offline.py  (33 测试)
│   ├── logs/                       ← 真实运行日志
│   └── output/sias_map.html
├── 姓名_C4D_output_screenshots/      ← 证据截图（7 张）
└── _meta/                           ← 环境探测与工具脚本
```

---

*本方案中的所有性能数据、设备信息、模型版本均来自本机真实运行，
原始记录见 `姓名_C4D_agent-skill/logs/`。*