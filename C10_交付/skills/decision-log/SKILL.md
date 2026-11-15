---
name: decision-log
description: 记一条决策（ADR 风格）：当时有哪些选项、为什么选这个、什么时候该回头看
version: 1.0
when: 做完一个以后可能会反悔或忘记理由的决定
inputs:
  query: 决策内容，一句话
  reason: 理由（可选）
  options: 被放弃的选项，逗号分隔（可选）
  revisit: 什么时候该回看，如 2027-01（可选）
tags: decision, 决策
tools: memory.write
handler: handler.py
---

# decision-log

## 解决什么问题

半年后有人问"当初为什么不用 X"，答案通常已经不存在了——聊天记录被清、文档被覆盖。
决策日志的价值不在记录结论，而在记录**当时排除了什么、依据是什么**。

## 输入 / 输出

- 输入：`query`（决策）、`reason`、`options`、`revisit`
- 输出：`summary`、`id`（K 层记录）、`path`（ADR 文件）

## 步骤

1. 生成 `ADR-YYYYMMDD-<slug>` 编号；
2. 写 `memory/knowledge/decisions/<编号>.md`，含"背景 / 选项 / 决定 / 理由 / 回看日期"五节；
3. 同时写一条 K 记录（带 `tags=decision`、`revisit` 元数据），让它能被检索到。

## 什么时候会失败

- `query` 为空 → 报错（没有决策内容的 ADR 没有意义）；
- 同一天同一句话重复记录 → 走记忆层去重，返回已有 id，不会产生两条。
