---
name: note-to-knowledge
description: 把一条随手记的笔记提炼进知识层，并找出它和已有记忆的关联
version: 1.0
when: 笔记里出现了"结论/方法/原则"，值得从情境层升格成知识层
inputs:
  query: 笔记原文
  title: 标题（可选）
tags: knowledge, 沉淀
tools: memory.search, memory.write
handler: handler.py
---

# note-to-knowledge

## 解决什么问题

随手记（S 层）会越积越多，而真正会反复用的是其中的结论（K 层）。
人的问题是"没时间整理"，机器的问题是"不知道怎么判断哪条值得升格"。

这个技能不判断价值，它只做三件机械的事：去重、找关联、补最小结构。

## 输入 / 输出

- 输入：`query`（笔记原文）、`title`（可空）
- 输出：`summary`、`id`、`related`（相关联的既有记录 id）

## 步骤

1. 用原文前 60 字做去重检查，已存在则返回已有 id（不制造近义重复）；
2. 用 `memory.search` 找出 3 条最相关的既有记录；
3. 写入 K 层，`meta.related` 记下关联 id，`source` 记下运行 id。

## 什么时候会失败

- 原文为空 → 报错；
- 原文只有一句情绪（如"今天好累"）→ 仍会写入，但标题会带上"（待提炼）"，
  这是刻意保留的粗糙：机器不该替人决定什么值得记住。
