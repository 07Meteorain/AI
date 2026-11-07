# Bramble 评审 Aster（第二轮）

> 评审基线：第二轮集成后的 `duolog/explain.py`（324 行）、`duolog/cli.py`（409 行）、
> `duolog/render.py`（534 行）。`render.py` / `cli.py` 上一轮是我交的，这一轮被 Aster
> 改了；以下是"我认什么、不认什么"。我只做了静态分析，未运行命令；标"按代码推断"
> 的条目请主持人实测（涉及死循环的那条请加 timeout）。

## 0. 一句话结论

找到 **6 条问题**：3 条中等（固定 72 列、`_wrap` 潜在死循环、`_load_entries` 吞解析告警），
3 条低（`winner=None` 语义过载、`explain` 不收 `--no-color`、`_fmt_tags` 多一个顿号）。
最高严重度：**中**（explain 固定 72 列，窄终端整框断行）。
另有一条"我查过、没走样"的结论放在第 3 节，避免重复报。

## 1. 她改了我的文件，我认不认

### 1.1 `render.py` 的 `_fmt_tags` 折叠数 —— 认

她把我原来的 `等 {总类别数} 类` 改成 `等 {len(ordered) - limit} 类`（剩余未展示数），
并补了"4 类只展示 3 类 → 等 1 类""恰好 3 类不出现等 0 类"两条测试。这个修复是对的：
原来的"总数"口径会让读者把已展示的类别再算一遍；现在 3 + 剩余 1 = 4，能对上。
唯一遗留是顿号位置（见问题 6，低）。

### 1.2 `render.py` 画像表「原始条目」列 —— 认

她把 `参与条目` 改成 `原始条目`，计数也从 `item.authors`（合并后的参与）改成遍历
`item.versions`（逐版本）。这是对的，且与契约 v1.2 的 `analyze.profile` 口径一致：
`share` 的分母是原始条目总数，`stats["entries"]` 也是原始条目数；现在画像表这一列
求和正好等于 `stats["entries"]`，不会再出现"共同确认的事件把两个人的参与数同时抬高"。
`render_terminal` 与 `render_markdown` 两处都同步了，我认。

### 1.3 `cli.py` 抽出 `_load_entries` —— 退出码/消息基本认，但有一个诊断缺口

她把我 merge 路径里的"读文件 + 解析 + 打印 ParseIssue"抽成 `_load_entries`，merge 与
explain 共用。退出码我逐分支对过：

- 读文件失败 → `None` → 调用方 2；
- 解析出现 error → `(entries, True)` → 调用方 1；
- 只有 warn → `(entries, False)` → 正常合并/溯源，退出码 0。

merge 的告警格式仍是 `duolog: path:line: [level] message`，原 merge 的输出没有变。
这部分我认。但"先 return、后打印"的顺序有一个吞告警的缺口，见问题 3。

## 2. 问题清单

### 问题 1（中）：explain 固定 72 列，窄终端整框断行

**位置**：`duolog/explain.py:32-36`（`_BOX_WIDTH = 72`、`_INNER_WIDTH = 68`）、
`_box` 第 145-151 行。

**复现**：

```
python -m duolog explain --a examples/sample_a.md --b examples/sample_b.md \
  --eid E-003 --author-a Aster --author-b Bramble
```

在 60 列终端里执行（或把窗口拖到 60 列；`COLUMNS=60` 在部分终端不改变实际渲染宽度）。

**实际输出（按代码推断）**：每一行（含边框）的 `display_width` 都恰好是 72；
60 列终端会对每行做软换行，`│` / `└` 被折到下一视觉行，框看起来是断的。
`tests/test_explain.py` 只断言"所有行等宽"，没有断言"行宽 ≤ 终端宽度"，所以测试全绿。

**期望输出**：终端是 tty 时按 `shutil.get_terminal_size().columns` 取宽度（留 1-2 列余量），
或提供 `--width N`；窄于 40 列时退化为无框的段落输出也比断框可读。宽终端（>72）
只是留白，不算错，但 72 在 100+ 列里显得过窄。

**严重度**：中。契约 §8.1 没有规定宽度来源，所以不算违约；但 explain 是"给人翻证据"
的界面，分屏/CI 60-70 列很常见，断框会直接毁掉可读性。

### 问题 2（中，潜在）：`_wrap` 的禁则兜底会死循环

**位置**：`duolog/explain.py:63-106`，重点是 99-105 行的 `if break_at == start` 兜底。

**复现**（请加 timeout，按代码推断会挂起）：

```
timeout 3 python -c "from duolog.explain import _wrap; print(_wrap('中', 1))"
```

**实际输出（按代码推断）**：无输出、进程不退出。原因是：`width_limit=1` 时，
首字符 `中` 宽 2，内层循环 `end == start`；`break_at` 从 `end` 开始，回退循环不执行，
`break_at == start` 成立后兜底又把它设回 `end`（仍等于 `start`），
`lines.append(paragraph[start:start])` 追加空串，`start = break_at` 原地不动；
下一轮重复，`lines` 无限增长。

**期望输出**：至少让 `start` 前进一个码点（例如 `break_at = start + 1`，后续由
`_fit` 截到宽度）、或直接抛 `ValueError("width too small")`；不能挂起。

**严重度**：中（潜在）。当前 `explain` 的固定前缀让 `_wrap` 的 limit 最小为 62
（`_INNER_WIDTH 68 - 版本正文前缀 6`），CLI 不会触发；但 `_wrap` 是模块级函数，
docstring 明确承诺"避免死循环"，且 `_BOX_WIDTH` / 前缀一旦调整就会踩到。
这条更像是她修顿号时引入的回归：原来的版本在 `limit < 首字符宽` 时也不会挂
（原实现 `current` 为空时直接收下宽字符，下一轮会换行）。

### 问题 3（中）：`_load_entries` 在后续文件读不了时，吞掉前面的解析告警

**位置**：`duolog/cli.py:170-199`；`_load_entries` 第 186 行在"打印 problems"（194-198 行）
之前就 `return None`。

**复现**：

```
# bad_a.md 内容：
# ## E-001 | 1 | 类型:分工 | 多余字段
# 正文
python -m duolog merge --a bad_a.md --b does_not_exist.md
# explain 同样：
python -m duolog explain --a bad_a.md --b does_not_exist.md --eid E-001
```

**实际输出（按代码推断）**：退出码 2；stderr 只有
`duolog: 无法读取输入文件 does_not_exist.md: ...`。
`bad_a.md` 的 `[error] 条目标题格式不合法：...` 完全不会出现——因为 A 的 ParseIssue
已经收进 `problems`，但 B 读失败时函数直接 `return None`，194 行的循环永远没执行。

**期望输出**：先打印已经收集到的 parse issue，再报读文件失败（退出码仍是 2）；
或者改成"先读完全部文件，再统一打印所有问题"，让用户一次看到全部错误。

**严重度**：中。退出码没走样（2 是对的），但诊断信息丢了；用户修完路径后重跑，
才会发现 A 里还有个坏表头。这条在 merge 与 explain 两条路径都成立。

**备注**：这是我上一轮 `_run_merge` 里就存在的行为，她原样搬进了公共函数；
抽成公共函数后影响面从 1 条路径变成 2 条，所以现在值得修。不是她新引入的。

### 问题 4（低，疑似设计/契约解释）：`explain_dict` 的 `winner=None` 语义过载

**位置**：`duolog/explain.py:192-205`（`_winner_author`）、`266-272`（`explain_dict`
返回 `winner`）、`208-221`（`_verdict_line`）。

**复现**：

```
python -m duolog explain --a examples/sample_a.md --b examples/sample_b.md \
  --author-a Aster --author-b Bramble --eid E-001 --json   # confirmed
python -m duolog explain ... --eid E-002 --json             # single
python -m duolog explain ... --eid E-006 --json             # needs_review
```

**实际输出（按代码推断）**：三条都是 `"winner": null`，只有 `status` 不同
（`confirmed` / `single` / `needs_review`）。

**期望输出**：这不是说 §8.1 违规（§8.1 只写"winner 作者名，无则 None"），而是接口
陷阱：下游若用 `winner is None` 判断"没有裁决/需要人工复核"，会把 `single` 和
`confirmed` 一起误判。建议至少把"必须结合 status"写进契约/文档；如果主持人愿意
扩展形状，`single` 可以返回唯一作者（E-002 就是 Aster），`confirmed` 保留 null，
或增加一个 `resolution` 字段。**需要主持人裁定，不能由实现单方面改。**

**严重度**：低（设计风险；文本版 explain 已经用 status 区分了，只有 JSON 消费方会踩）。

### 问题 5（低）：`explain` 不收 `--no-color`，`--json --no-color` 直接用法错误

**位置**：`duolog/cli.py:142-161`（explain 子命令参数），对照 `merge` 的
`--no-color`（第 129 行）；契约 §9 的 explain 命令行确实没列这个 flag。

**复现**：

```
python -m duolog explain --a examples/sample_a.md --b examples/sample_b.md \
  --eid E-003 --json --no-color
```

**实际输出（按代码推断）**：退出码 2；stdout 为空；stderr 是 argparse 的
`duolog: error: unrecognized arguments: --no-color`。

**期望输出**：explain 本来没有颜色，`--no-color` 作为 no-op 接受最省事（退出码 0，
JSON 正常输出）；或者在 help 里明确"explain 不支持 --no-color"。
现在 merge 和 explain 的通用命令模板不一致，CI 里复制一行就会失败。

**严重度**：低。stdout 没有被错误信息污染（为空），但命令整体失败；不是颜色泄漏。

> 同组的 `--json` + eid 不存在（`E-999`）我查了：退出码 1、stdout 为空、错误只在
> stderr，**干净**；`--json` + 解析 error 也是退出码 1、stdout 为空。这两条不用改。

### 问题 6（低）：`_fmt_tags` 的「、等 N 类」多一个顿号

**位置**：`duolog/render.py:224-242`，第 241 行把 `等 {剩余} 类` 作为一个独立 part
和前面用 `、` 连接。

**复现**：

```
python -c "from duolog.render import _fmt_tags; print(_fmt_tags({'实现': 2, '互检': 2, '决策': 1, '分工': 1}))"
```

**实际输出（按代码推断）**：`互检×2、实现×2、决策×1、等 1 类`（"等"前面多一个顿号）。

**期望输出**：`互检×2、实现×2、决策×1 等 1 类` 或 `互检×2、实现×2、决策×1（等 1 类）`。

**严重度**：低（纯排版）。和已经修掉的 explain 行首禁则是同一类标点问题，但这是
`render.py` 的另一个落点，不是重复报 explain 折行本身；顺手记一笔。

## 3. 我查过、没走样的（避免重复报）

- **`_load_entries` 的退出码**：merge/explain 在"读文件失败 2 / 解析 error 1 / 仅 warn 0"
  三条分支上完全一致；merge 的告警格式没有变。唯一问题是问题 3 的"告警被吞"，
  不是退出码走样。
- **`--json` + eid 不存在**：explain 退出 1、stdout 空、stderr 一行"未找到事件"，
  JSON 没有被错误信息污染。
- **`--json` + 解析 error**：explain 退出 1、stdout 空、stderr 有 error/中止说明；
  explain 不会在半截数据上输出 JSON。
- **`merge --json --no-color`**：0、JSON 可解析、无 ANSI（上一轮行为保留）。
- **`render.py` `_fmt_tags` 折叠数**：4 类→等 1 类、恰好 3 类不出现"等 0 类"，
  口径正确；只有问题 6 的标点。
- **`render.py` 「原始条目」列**：逐 `versions` 计数，求和等于 `stats["entries"]`，
  与 `analyze.profile` 的 share 分母一致；我认这个改动。
- **explain 文本的等宽/无 ANSI**：`test_explain` 的逐行等宽断言与 `\x1b` 清洗都覆盖到了；
  问题是"等宽不等于适配终端宽"（问题 1），不是宽度算错。
- **`explain_dict` 的字段/版本顺序**：六个键与契约 §8.1 一致，`versions` 按
  `(author, clock, line, text, eid)` 重排后与 merge 的 `versions` 顺序一致；
  没有发现字段缺失或顺序漂移。

## 4. 建议修复顺序

1. **问题 1（固定 72 列）**：决定宽度来源（tty 检测 + `--width`），影响所有 explain 用户。
2. **问题 3（吞告警）**：把 `problems` 的打印提前到 `return None` 之前，或先读完再统一打印。
3. **问题 2（`_wrap` 兜底死循环）**：`break_at == start` 时强制前进一个码点或抛错；
   即使当前 CLI 不触发，也应在函数级修掉。
4. **问题 4/5/6**：文档/契约裁定、`--no-color` 是否接受、顿号位置；都是低风险改动。

## 5. 评审边界

- 我没有运行任何命令（沙箱 PowerShell 起不来），以上"实际输出"都是按代码路径推断；
  问题 1/3/5 的退出码与输出可直接复现，问题 2 请务必加 timeout。
- 问题 4 是设计判断，不是 §8.1 的硬违规；需要主持人决定是否改契约，我不建议实现
  单方面改变 JSON 形状。
- 我认可 `_load_entries` 的抽离本身（重复逻辑收口是对的），只不认它在"后续文件
  读失败"时的打印顺序；这是可以局部修的，不需要回滚重构。
