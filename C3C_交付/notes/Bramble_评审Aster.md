# Bramble 评审 Aster（`merge.py` / `analyze.py`）

> 评审基线：第二轮开始前的 `merge.py`、`analyze.py`（第一轮集成后、v1.3/v1.4 生效前）。
> 本轮我按契约 v1.3 改了 `merge.py` 的标签语义并新增 R4，所以文中标"已修"的两处
> 在现在的文件里已经变了；评审保留原判断，便于主持人核对改动动机。

## 一、我认可的 2 处

### 1. `merge.py` 的 `_version_key` / `_longest_key` 用"总序兜底"换取确定性

位置：原 `merge.py` 第 35-51 行（现在在文件前部同名函数处）。

契约只要求 `versions` 按 `(author, clock)` 排序、`items` 按 `(eid_key, authors)` 排序。
但真实日志里会出现"同一作者重复 eid"这种坏数据（`parse_log` 会报 error 但仍保留两条），
只按两元键排序时结果依赖输入顺序，指纹就会漂移。Aster 额外加了 `line`/`text`/`eid`
做全序兜底，又给 R0 的"最长正文"加了长度相同时的确定性选择——这不是多余的防御，
而是让 §2"与输入顺序无关"在坏数据上仍然成立。我第一轮写指纹测试时只想到正常数据，
是这组 tie-breaker 补上了我没测到的角落。

### 2. `analyze.py` 的画像口径统一为"逐版本"，四个数字互相自洽

位置：`analyze.py` 第 124-171 行（`profile` 的主循环、`authors`、`share`）。

`skill_tags` / `type_tags` / `transfers` / `share` 全部只从 `item.versions` 取数，
不使用合并后的标签并集；`authors` 又并入 `skill_owner` 的非空作者名。这样"某人用了
某技能"在计数与迁移边里是同一个事实，不会出现"有计数、无迁移边"的自相矛盾；
零条目的技能拥有者也会以 `0.0` 出现，而不是从画像里消失。契约 v1.2 的裁定是对的，
Aster 的实现把"画像是一组可互相解释的数字"这件事落到了代码里。

## 二、我不同意的 2 处

### 1. `MergedItem.tags` 一律取并集：一个事件同时是"决策"和"实现"（已修）

位置：原 `merge.py` 第 74-78 行（`MergedItem` 的 docstring 与 `tags` 注释）、
第 141 行 `tags = tuple(sorted({tag for v in versions for tag in v.tags}))`。

这不是风格问题，是语义错误。E-003 里 Aster 写"这是决策"、Bramble 写"这是实现"，
R1 裁决给 Aster 后，`tags` 仍带 `类型:决策,类型:实现`；`analyze.profile` 的
`type_tags` 虽然按版本统计、暂时没被污染，但 `--out` 回读后的日志、`explain` 的
"终裁标签"、以及任何直接消费 `MergedItem.tags` 的下游都会把同一次事件算进两个
互斥类型。技能可叠加、类型互斥，这两类标签不该共用一个"并集"实现。

已在 `merge.py` 按 §3.1 修复：技能标签保持并集，类型标签在 R1/R2/R4 只取 winner，
R3 / single / confirmed 才并集；`stats` 的 8 个键与计数口径未动。

### 2. `analyze.py` 的 `skill_owner` 在边界没有 `strip()`

位置：`analyze.py` 第 137-148 行（`owner = skill_owner.get(skill)` 与
`for owner in skill_owner.values(): authors_seen.add(owner)`）。

`skill_owner` 的值被原样用于两处：一是 `author != owner` 的迁移判定，二是 `authors`
集合。如果调用方传入 `{"SEL-1": " Aster "}`（前后带空格），而版本里的作者是
`"Aster"`，会发生两件错事：

1. `author != owner` 成立，产生一条 `src=" Aster ", dst="Aster"` 的伪迁移边——
   一个人"迁移给了自己"；
2. `authors` 同时出现 `" Aster "` 与 `"Aster"`，画像里多出一个不存在的协作者，
   `share` 也会被拆成两个键。

CLI 的 `_resolve_skill_owners` 目前会 strip，所以生产路径暂时不触发；但
`profile()` 是契约公开 API，主持人完全可能直接调用。建议在 `profile` 入口统一
`owner.strip()`（空串按无归属处理），一行就能把边界收干净。我没有改 `analyze.py`，
留给 Aster/主持人决定。

## 三、备注（不算分歧，但值得记一笔）

- `merge.py` 的 R2 用 `sorted(clocks)[0] > sorted(clocks)[1]` 判"严格最新"，比逐个
  `all(max > other)` 更简洁且对多版本正确；`next(v for v in versions if v.clock == newest)`
  在"唯一最大"成立时不会歧义，这点我检查过。
- 三处公开 docstring（`Conflict`、`MergedItem`、模块头）在原版里把规则集写成 R1/R2/R3。
  v1.3 加 R4 后这些文字会滞后；`explain.py` 又要把 `rule` 直接展示给人，文档滞后会
  放大误解。我在改 `merge.py` 时已同步为 R1/R2/R4/R3。
- `analyze.py` 的 `share` 按每位作者四舍五入到 4 位，合计可能显示 99.99% / 100.01%。
  契约明确要求 4 位小数，所以不算 bug；但报告若写"合计 100%"需要留意，渲染层最好
  不要自己再求和下结论。
