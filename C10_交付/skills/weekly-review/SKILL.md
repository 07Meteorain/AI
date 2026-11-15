---
name: weekly-review
description: 生成某一周的复盘报告：跑了多少次、哪些意图重复、失败在哪、沉淀了什么
version: 1.0
when: 每周结束时，或想看清"这周系统/我到底在干什么"
inputs:
  week: ISO 周，如 2026-W46；留空表示本周
  out: 输出路径；留空则写到 memory/reviews/
tags: review, 复盘
tools: memory.search, memory.write
handler: handler.py
---

# weekly-review

## 解决什么问题

一周过去，trace 里躺着几百行 JSON，没人会去读。复盘要的不是数据，是**从数据里
挑出三件值得改的事**。这个技能把"读 JSON"变成"读一页纸"。

## 输入 / 输出

- 输入：`week`（可空）、`out`（可空）
- 输出：`summary`（一行结论）、`path`（报告路径）、`counts`（各层统计）

## 步骤

1. 按 ISO 周算出周一到周日的日期区间（`date.fromisocalendar`，不手算闰年）；
2. 从 AR 层取该区间的行动记录，统计意图分布、失败数、平均步数；
3. 从 T 层取该周结束的任务；
4. 写 Markdown 报告，**只写数据与三类发现**，不做激励式总结。

## 什么时候会失败

- 该周没有任何记录 → 返回 `empty=True`，不生成空报告；
- 周编号写成 `2026-46` 或 `46` → 直接报错，不猜。
