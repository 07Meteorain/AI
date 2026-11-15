# ARCHITECTURE · 第二大脑的五层架构

> 本文回答四个问题：**分了哪几层、层与层的契约是什么、为什么这么分、什么时候它会坏。**
> 图见 [`docs/架构图.svg`](docs/架构图.svg)（矢量，可放大看字）。
> 决策记录用 ADR 格式，包含**被否掉的方案**——只写结论的架构文档等于没写。

---

## 1. 目标与非目标

### 目标

| # | 目标 | 可验收的形式 |
| --- | --- | --- |
| G1 | 五层各自可工作、可单独测试 | 196 项测试按层分布；`doctor` 逐层自检 |
| G2 | 零第三方依赖，`clone` 即可运行 | `python -m brain doctor` 在干净环境通过 |
| G3 | 每次运行可追溯 | 每条回答对应一条 `RunTrace`（JSONL） |
| G4 | 记忆可沉淀、可检索、可衰减 | KSTAR 四层 + BM25 排序 + 三条沉淀规则 |
| G5 | 重复任务能被固化，且固化可度量 | `evolve` 生成草稿技能；`trend` 按意图对比步数 |
| G6 | 失败可复现、可定位 | 工具熔断 + 失败进 trace + AAR 记录 8 条真实故障 |

### 非目标（明确不做，避免"什么都做一点"）

- **不做多用户/权限系统**：单机单用户，为不存在的需求写代码只会让核心变脆。
- **不做向量检索**：向量要依赖（`numpy`/模型），而本项目的第一承诺是零依赖。
  代价写在第 8 节。
- **不做自主长程任务**：没有 cron、没有后台自循环。一次调用一次闭环。
- **不做 Web UI**：命令行足够；UI 会让"可运行"的验证成本上升一个数量级。

---

## 2. 总览

```text
                    ┌──────────────────────────────────────────────┐
   人 ──────────────▶│ L1 接口层  brain/interface/                  │
                    │   cli.py（14 条命令）· render.py（回执排版） │
                    └───────────────────┬──────────────────────────┘
                                        │ App 组装（brain/app.py = 唯一组合根）
                    ┌───────────────────▼──────────────────────────┐
                    │ L3 循环层  brain/loop/                       │
                    │   planner（意图→步骤）· engine（执行/反思）   │
                    │   compose（结果→人话）· trace（留痕）        │
                    └───┬──────────────┬──────────────┬────────────┘
                        │              │              │
        ┌───────────────▼───┐  ┌───────▼────────┐  ┌──▼──────────────────┐
        │ L2 工具层         │  │ L4 技能层      │  │ L5 记忆层           │
        │ brain/tools/      │  │ brain/skills/  │  │ brain/memory/       │
        │ 12 个工具         │  │ 发现/执行/记账 │  │ KSTAR 四层 + 索引   │
        │ 权限·超时·熔断    │  │ 渐进披露       │  │ 沉淀 + 同义词       │
        └─────────┬─────────┘  └───────┬────────┘  └──┬──────────────────┘
                  │                    │              │
                  ▼                    ▼              ▼
          文件 / git（只读）    skills/*/handler.py   memory/db/*.jsonl
                                                     memory/knowledge/*.md
```

**进化层**（`brain/evolve/`）不参与一次运行，它**读取 trace 与记忆，反过来修改技能与记忆**：

```text
trace/*.jsonl ──▶ miner（挖重复/失败/未命中的说法）──▶ scaffold（写草稿技能）
                                              └────▶ promote（AR→K，S 归档）
                                              └────▶ metrics（before/after）
```

---

## 3. 层契约

每一层只承诺三件事：输入、输出、不变量。**不变量被破坏就是架构被破坏。**

| 层 | 输入 | 输出 | 不变量（不可违反） |
| --- | --- | --- | --- |
| L1 接口 | argv / stdin | 文本回执 + 退出码（0 正常 / 1 有检查未过 / 2 用户输入错） | 不直接操作记忆或工具，只经 `App` |
| L2 工具 | `ctx` + 声明过的参数 | `ToolResult(ok, data, error, ms)` | 任何异常都在边界被捕获；失败也是结果 |
| L3 循环 | 一句话 + session | `RunResult(trace, answer, evidence)` | 无论成败都落 trace；步数 ≤ 上限 |
| L4 技能 | `(ctx, args)` | `dict`（必须含 `summary`） | 只能在 `_drafts/` 自动生成；不得静默失败 |
| L5 记忆 | 记录 / 查询 | `Record` / `Hit` | K 不衰减；删除只能归档；echo 不参与检索 |

### 为什么依赖必须单向

如果 L5 去调用 L3（例如"记忆自己决定要不要反思"），那么"记忆"就依赖了"循环的策略"，
两者将无法单独测试，也无法单独替换。**单向依赖是让每一层都能被单元测试的前提**，
也是 `tests/` 里 196 项测试能各自独立跑的原因。

---

## 4. 一次 `ask` 的时序

```text
人：brain ask "上次那个检索排序怎么定的？"
 │
 ├─ L1  cli.cmd_ask → App.ask(text, session)
 │
 ├─ L3  RulePlanner.classify  → Intent(recall, conf=0.60, "疑问句")
 │      RulePlanner.plan      → [memory.search(query="…", k=5)]
 │
 ├─ L2  ToolRegistry.call("memory.search")
 │       ├─ 契约校验（必填/未知参数）
 │       ├─ 权限闸门（read 放行；write/exec 看 allow_write）
 │       └─ 执行 → ToolResult(ok, hits, ms)
 │
 ├─ L5  KSTARMemory.search
 │       ├─ tokenize（CJK 二元组 + 拉丁词）
 │       ├─ BM25 → 候选
 │       ├─ 同义词扩展（权重 0.5 叠加）
 │       ├─ 重排：层先验 × 重要度 × 新近度 × 命中次数
 │       └─ 跳过 echo 记录 + 命中计数 +1
 │
 ├─ L3  compose → 抽取式回答（带分数与命中词）+ evidence ids
 │
 ├─ L3  reflect → 写 AR（含 workflow/steps/ok/error）+ 写 S（含 echo 标记）
 │
 └─ L3  trace.append → memory/db/traces/YYYY-MM-DD.jsonl
        → 回执：意图 / 步数 / 每步结果 / 记忆水位 / trace 路径
```

**关键点：回答不是终点。** 回答之后一定跟着"写回记忆"和"落 trace"，
这两步才让下一次运行有机会比这次更好。

---

## 5. 数据结构

```python
Record(id, layer, title, text, created, updated,
       tags, source, importance, status, hits, last_hit, meta)   # L5 的最小记忆单元

Step(index, tool, args, ok, ms, note, error)                     # 一次工具调用
RunTrace(run_id, session, input, intent, confidence, started, ended,
         steps, answer, evidence, recall_hits, status, degraded, meta)  # 一次运行

ToolResult(tool, ok, data, error, ms, args, note)                # 工具边界上的统一形状
Skill(name, description, path, version, when, inputs, tools,
      handler, body, tags, status)                               # L4 的契约对象
```

三个刻意的设计：

1. **`ToolResult` 成功与失败同构**。循环层不需要 try/except 分支，只需要看 `ok`。
2. **`RunTrace.meta` 是开放字典**。加字段不用改 schema，也不会破坏历史 trace 的可读性。
3. **`Record.meta` 承载层特有语义**（`workflow`、`echo`、`covers`、`archived`），
   而不是给每层建不同的表——四层共用一套存储，是"能一次查全"的前提。

---

## 6. 六个架构决策（含被否方案）

### ADR-001 为什么零第三方依赖

- **决策**：只用 Python 标准库。
- **被否**：`click`+`rich`（CLI 好看一倍）、`pyyaml`（front matter 解析更省事）、`jieba`（中文分词更准）。
- **理由**：本项目的核心承诺是"评审者 clone 下来两条命令就能验证"。
  每加一个依赖，就多一类"在我机器上跑不起来"的可能；而漂亮的 CLI 对"能不能跑"零贡献。
- **代价**：自己写 YAML 子集解析（约 80 行）、中文按二元组切词（见 ADR-002）。

### ADR-002 为什么不用 SQLite FTS5 / 向量检索

- **决策**：纯 Python 倒排索引 + BM25，内存加载。
- **被否**：FTS5（依赖 SQLite 编译开关）、`sqlite-vec`/`faiss`（二进制依赖）。
- **理由**：记忆量级是几千条，BM25 在毫秒级；FTS5 省下的时间不够解释"为什么你要建虚表"。
- **代价**：全量加载进内存，十万条以上必须换实现——写进 README「规模边界」。

### ADR-003 为什么默认离线、模型只做"规划"

- **决策**：`RulePlanner` 为默认；LLM 只替换"分类 + 选工具"，不替换"回答的事实来源"。
- **被否**：默认接模型（更"AI"）、纯 prompt 不写代码（更"轻"）。
- **理由**：**规划错了，回答再漂亮也没用**；而规划是可以用 20 条规则覆盖 80% 场景的。
  离线可跑优先于"看起来更像 AI"。
- **代价**：语义理解弱（"帮我想想上次那个事"判不出来）；靠 `--provider openai` 补齐。

### ADR-004 为什么记忆用 JSONL 而不是数据库

- **决策**：一层一个 append-only `.jsonl`，更新时整体重写。
- **被否**：SQLite（并发好）、单文件 SQLite + WAL。
- **理由**：记忆是长期资产，**可读、可 diff、可手工修复** 比写入性能重要。
  一行坏了只丢一条（`read_jsonl` 跳过坏行）；SQLite 坏了通常整库打不开。
- **代价**：无并发控制（两个进程同时写会互相覆盖）；更新是 O(n)。

### ADR-005 为什么「问句回声」要单独标记

- **决策**：`recall/chat` 运行写入的 AR/S 打 `meta.echo=True`，检索默认跳过。
- **经过**：演示阶段发现"同一句话问两遍，第二遍命中第一遍的问句"，命中率虚高到 100%。
- **理由**：问句不是证据。它进了索引就会自我强化，让"检索成功"变成一句空话。
- **代价**：想查"我问过什么"要显式 `--echo`。

### ADR-006 为什么进化只写 `_drafts/`

- **决策**：自动生成的技能一律在 `skills/_drafts/`，`version=0.1`，`status=draft`。
- **被否**：直接改进人工技能（"更自动化"）。
- **理由**：一个会悄悄给自己加代码的系统，迟早会长出没人能审计的行为。
  草稿可以**自动接管**（省掉重新规划），但升级到 1.0 必须有人读过它的 handler。
- **代价**：进化需要人工"签收"，不是全自动。

---

## 7. 失败模式与恢复

| 故障 | 现象 | 是否自愈 | 恢复动作 |
| --- | --- | --- | --- |
| 单个工具抛异常 | 该步 `ok=False`，其余继续 | 是 | 看 trace 的 `error`；连续 3 次自动熔断 |
| 技能 handler 崩 | `skill.run` 失败，循环记 failed | 是 | `skill list` 看 status；修 handler |
| 模型超时/无 key | 回落规则规划器，`fallback=True` | 是 | 回执会打印降级原因 |
| 记忆文件写坏一行 | 该行被跳过，其余可读 | 是 | 手工修那一行 JSON |
| 索引与记录不一致 | `doctor` 的「KSTAR 索引一致」变红 | 否 | 重启即重建索引（每次进程启动重建） |
| 两个进程同时写 | 后写覆盖先写（更新操作） | 否 | 单进程使用；批量导入用 `import-notes` |
| 自动技能过拟合 | 技能回放写死的参数 | 否 | 草稿需人工 review；`version` 不升就不用 |

---

## 8. 规模与性能边界

| 维度 | 当前实测 | 设计上限 | 超限会怎样 |
| --- | --- | --- | --- |
| 记忆条数 | 35 条（演示库） | ~1 万条 | 启动时全量建索引变慢（O(n)） |
| 单条记忆长度 | 演示均值 < 300 字 | 4000 字（`import-notes` 截断） | 长文会主导 BM25 的 `avgdl` |
| trace 条数 | 14 条（演示库） | 按天分文件，无硬上限 | `brain trend` 全量扫，变慢 |
| 技能数 | 4 个（含 1 个草稿） | ~50 个 | 清单变长，常驻上下文成本上升 |
| 单次运行耗时 | 2–11 ms | — | 主要花在 Python 启动（~60ms） |

**换实现的触发条件**（写清楚，免得以后拍脑袋）：记忆 > 1 万条 → 换 SQLite + FTS5；
需要语义检索 → 加一个可选的 embedding 后端，但**默认路径必须保持零依赖**。

---

## 9. 扩展点

| 想加什么 | 改哪里 | 不要改哪里 |
| --- | --- | --- |
| 新工具 | `brain/tools/builtin.py` 加一个 `@reg.tool`，写清 `Param` 与 `danger` | 不要动 `registry.py`（除非要改权限模型） |
| 新技能 | `skills/<name>/SKILL.md` + `handler.py`（或 `brain skill new`） | 不要动 `loader.py` 的解析规则 |
| 新意图 | `loop/planner.py` 的 `INTENT_KEYWORDS` + `plan()` 加一条 | 不要在 `engine.py` 里加 if 分支 |
| 新记忆层 | `store.py` 的 `LAYERS` + `kstar.stats` + 文档 | **不建议**——四层是一个整体语义，加第五层通常是没想清楚 |
| 换模型 | 实现 `BaseProvider` 三个方法，用 `build_provider` 注册 | 不要在 `engine.py` 里直接发 HTTP |

---

## 10. 与提交要求的对应

| 要求 | 落在哪 |
| --- | --- |
| 五层架构 | 第 2–3 节 + `brain/{interface,tools,loop,skills,memory}` |
| 各层可工作 | `doctor` 七项检查 + 196 项测试 |
| 设计有据 | 第 6 节六个 ADR（含被否方案与代价） |
| KSTAR 四层 | 第 3/5 节 + [`docs/KSTAR记忆规范.md`](docs/KSTAR记忆规范.md) |
| 重复任务抽象为技能 | 第 2 节进化链路 + [`docs/进化机制.md`](docs/进化机制.md) |
| 每次使用都在进化 | `evolve` + `trend`（review 3.0→1.0 步） |
