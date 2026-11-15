---
name: auto-review-c264
description: [草稿] 自动固化的工作流：memory.search>skill.run>memory.promote，来自 3 次重复。
version: 0.1
when: 当你又要做一遍「review」这件事时
inputs:
  query: 本次的输入文本（会替换掉当初记录的那句话）
tags: auto, draft, review
tools: memory.search, skill.run, memory.promote
handler: handler.py
---

# auto-review-c264

> 本技能由 `brain evolve` 从 3 次重复执行中自动生成，**未经人工审核**。
> 生成时间：2026-11-15T16:09:47+08:00

## 它复现的流程

```
1. memory.search({"query": "复盘 记录", "k": 5, "layers": "AR,T"})
2. skill.run({"name": "weekly-review", "args": "{\"week\": \"\"}"})
3. memory.promote({"apply": false})
```

## 为什么会有它

系统在 trace 里发现同一组工具被同样的顺序调用了 3 次：

- `run-20261115-a2e3e6`  周复盘  → 技能 `weekly-review` 执行完成（2.26ms）。 2026-W…
- `run-20261115-845580`  周复盘  → 技能 `weekly-review` 执行完成（1.35ms）。 2026-W…
- `run-20261115-10bc85`  周复盘  → 技能 `weekly-review` 执行完成（1.63ms）。 2026-W…

所以把这条路径固定下来。以后再遇到同类任务，走技能只花 1 步，
而不是重新规划 3 步。

## 什么时候不该用它

- 输入不是同一类任务时（本技能不做意图判断，它只回放流程）；
- 流程里含有本项目的临时状态时（比如某次特定的文件路径）。

## 怎么改进它

1. 读一遍 `handler.py`，把写死的参数改成真正有意义的输入；
2. 把 `version` 改成 1.0，移出 `_drafts/`；
3. 在 `tests/` 里加一条针对它的测试。
