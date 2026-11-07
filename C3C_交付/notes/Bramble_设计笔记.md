# Bramble 设计笔记（SEL-2 · 零依赖 CLI 工程化与终端渲染）

> 配对的算法侧（Aster，SEL-1）负责"合并得对不对"；我负责"结果能不能被人和 CI
> 可靠地消费"。以下记录我做的取舍、我踩过的边界，以及给 Aster 的交接说明。

## 1. SEL-2 到底是什么（一句话）

把确定性合并的结果变成三种可靠界面：**退出码可判定的 CLI**、
**中文按显示宽度对齐的终端报告**、**可直接贴 PR 的 Markdown 报告**，
外加一个不读任何文件也能跑通全链路的 `selfcheck`。

## 2. 三个关键取舍

### 取舍一：自己实现 `display_width`，不用 `len()`，也不引 `wcwidth`

- **做法**：`unicodedata.east_asian_width` 为 `W/F` 记 2 列；组合符（`unicodedata.combining` 非 0）
  与 `Mn/Me/Cf/Cc` 记 0；换行不计；其余记 1。所有列宽、截断、补白都只走这一套。
- **不这样做会怎样**：用 `len()` 时，表头每多一个汉字就多错 1 列，且错位量随单元格内容变化，
  是那种"看起来只是没对齐"、极难排查的 bug；引 `wcwidth` 则直接违反"零第三方依赖"，
  还多出一个版本兼容面（不同终端宽度表还不一致）。
- **代价与自洽**：`Ambiguous` 字符（`·`、`×`、`…`）统一按 1 列。个别终端把它渲染成 2 列时，
  与那些终端会有 1 列差；但本工具内部所有表格行宽严格相等（测试用
  `display_width` 逐行断言行宽一致），不会出现"同一张表内部歪掉"。
- 数据侧还做了一道 `_scrub`：把正文里的 ESC 等控制字符换成空格。否则 `color=False`
  只能保证"渲染器不加 ANSI"，挡不住日志正文自带 ANSI —— 那条契约就名存实亡。

### 取舍二：终端表格强制单列截断（`max_col=40`），且冲突清单只保留四列

- **做法**：`事件 | 裁决 | 规则 | 理由`，每列内容上限 `max_col`，超出截断加 `…`；
  长理由在终端必然被截掉。完整信息走 `--report` 的 Markdown 和 `--json`。
- **不这样做会怎样**：一段冲突理由就能把 80 列终端撑到自动换行，框线一换行整张表散架；
  评审者看到的是"一坨"，反而要回去读 JSON。终端是"扫读"界面，不是存档界面。
- **代价**：终端里看不到完整理由；这是故意的详略分工 —— 终端扫读、报告存档、JSON 给机器，
  三者不共享同一份详略。`--json` 永远不截断。

### 取舍三：解析出 `error` 就中止，不写 `--out` / `--report`

- **做法**：两份日志的 `ParseIssue` 全部打到 stderr；只要有一条 `level == "error"`，
  打印"已中止"并返回退出码 1，不产出任何文件。
- **不这样做会怎样**：坏表头会让某个 eid 静默消失，合并结果照样"看起来完整"；
  更糟的是残缺结果会被 `--out` 写成下一轮的输入，错误被固化成数据。
  一个坏表头换一份似是而非的报告，是自动化里最贵的交易。
- **代价**：一次日志里有一处坏表头，整次 merge 都不出报告，只能看 stderr。
  这是有意的"失败要响"：解析错误是数据错误，`--strict` 管的是业务上的 `needs_review`。

## 3. 给 Aster 的交接说明（怎么调 render / cli 不踩坑）

### 3.1 渲染层 API

```python
from duolog.render import display_width, render_terminal, render_markdown

text = render_terminal(result, prof, color=False, max_col=40)  # 无末尾换行
report = render_markdown(result, prof)                          # 无 ANSI、无时间戳
```

- `render.py` **不 import** `merge.py` / `analyze.py`，只按契约字段做属性访问（鸭子类型）。
  我在单测里用 `SimpleNamespace` 假对象验收渲染，所以字段名一旦改，测试会立刻红。
- `result` 需要：`items`、`conflicts`、`fingerprint`、`stats`；
  每个 item 需要：`eid`、`authors`、`tags`、`text`、`status`、`rule`、`versions`；
  每个 conflict 需要：`eid`、`versions`、`winner`、`rule`、`resolution`、`note`。
- **我不排序 `items` / `conflicts`**：完全信任你按 §4 输出的顺序。请确保
  `items` 已按 `(eid_key(eid), authors)` 排序，否则报告顺序会跟着乱。
- `prof` 可以为 `None`（只渲染合并结果）；但正常路径请传 `Profile`。
  画像表里的"参与条目"是我从 `item.authors` 数出来的，不是从你的 `share` 反推的。
- `note` 请给一句话中文、不要换行和竖线：终端里换行会被压成 ` / `，
  Markdown 里会变 `<br>`、`|` 会被转义，可读性都会打折。

### 3.2 CLI

- 默认技能归属：`SEL-1 → --author-a`、`SEL-2 → --author-b`（契约 §0 的 A/B 分工）。
  真实作者名不同也没关系；要覆盖用可重复的 `--skill-owner SEL-1=某人`。
  `selfcheck` 内置样例固定使用 `Aster` / `Bramble`。
- 颜色策略：只有 stdout 是 tty、且没有 `--json` / `--no-color` 时才开色。
  `--json` 分支**根本不调用** `render_terminal`，所以 stdout 只有 JSON。
- `--out` 依赖 `MergedItem.versions` 非空（取 `max(clock)` 写回 header）；
  R3 的 `text` 请保留 `【作者】` 标注，否则回读后无法区分来源。
- `--out` 与 `--report` 是两种文件：前者是**可被 `parse_log` 再读回的日志**，
  后者才是 `render_markdown` 报告。不要混用。
- 测试：`python -m unittest discover -s tests -v`。你的模块缺失时集成测试会
  `skip` 而不是 `fail`（但字段/规则写错会立刻红）。

## 4. 我认为契约里最容易让 A 误解的一处

**§3 的 R0 与 `conflicts` 的关系**：两个以上版本只要规范化正文相同，就是
`status="confirmed"`、`rule="R0"`，但**不进入** `MergeResult.conflicts`。
因此 `stats["conflicts"]` 必须等于 `len(result.conflicts)`（只统计 R1/R2/R3），
而不是"有多版本的条目数"；`single` 同样不进 conflicts。
如果这里理解错，`stats` 和报告里的"冲突清单"会同时失真。

相邻的第二个坑是**R1 优先于 R2**：即使另一方 `clock` 更大，只要恰好一个版本带
`类型:决策`，也必须先命中 `R1-决策优先`。我写的
`test_r1_decision_beats_newer_clock` 专门钉这个：Aster clock=1 带决策、Bramble
clock=5 不带决策，赢家必须是 Aster。若按"时钟最大者优先"实现，sample 里的
`E-003` 会直接判错。

## 5. 我留的测试护栏（宿主集成时会跑）

- 宽度：ASCII / 中文 / 混排 / 全角 / 组合符 / 换行 / emoji，以及"每张表逐行
  `display_width` 相等"。
- 裁决：R0 最长原文、R0 三版本不算冲突、R1 压过更大时钟、R2、R3、single。
- 指纹：打乱输入顺序指纹不变；按契约 §4 重算 payload 与 `fingerprint` 相等。
- 渲染：`color=False` 无任何 ANSI（含数据自带 ESC 的清洗）、`color=True` 有 ANSI、
  无末尾换行、Markdown 的 `|` / 换行转义、`needs_review` 人工复核提示。
- CLI（真实子进程）：退出码 0/1/2、`--json` 可 `json.loads` 且无 ANSI、
  `--out` 能被 `parse_log` 回读、`--report` 内容、相对路径按 cwd 解析、
  `selfcheck` 在任意 cwd 都能跑。
