# Aster 评审 Bramble（render.py / cli.py）

> 评审对象：第二轮开始时的 `duolog/render.py`、`duolog/cli.py`（Bramble，SEL-2）。
> 结论先说：这两份代码的工程骨架比我第一轮写的算法模块更稳；下面的"不同意"
> 都是具体可复现的问题，不是口味问题。前两处我已经在 `render.py` 里改掉。

## 一、我认可的两处设计

### 1. 表格几何只有 `display_width` 一个入口，颜色永远不参与宽度

位置：`render.py:56-68`（`display_width`）、`render.py:107-117`（`_pad`）、
`render.py:120-178`（`_render_table`）。

`_render_table` 先把每个单元格 `_flatten` 成单行，再用 `display_width` 求列宽、
`_pad` 补白，最后才把**已经补好白**的文本交给 `paint_cell` 上色。这个顺序很关键：
ANSI 转义序列不占列，如果在补白前上色，`display_width` 会把 ESC 序列算进宽度，
表格立刻歪掉。把"几何"和"颜色"拆成两个阶段，是这套渲染能同时支持 `color=True`
与 `color=False` 的根本原因。`_flatten` 把单元格里的换行压成 ` / `，也避免了
框线被多行内容撑断——这是一个容易被低估的边界。

### 2. 退出码是 `main()` 的返回值，`--json` 分支根本不进渲染器

位置：`cli.py:79-100`（`main` 把 argparse 的 `SystemExit` 翻译成 int）、
`cli.py:235-241`（`--json` 只 `json.dumps`，不调用 `render_terminal`）。

很多 CLI 会在 `--json` 前先打印一行表头，或者用 `sys.exit()` 散落在各分支，
结果是"错误退出码 0""JSON 里混 ANSI""测试没法直接调 main"。Bramble 把出口
收敛成 `main() -> int`，`--json` 与终端渲染在控制流上互斥，而不是靠"记得关颜色"，
这让 `--json` 的 stdout 洁净是结构上成立的。`_write_stdout` 还兜住了终端编码
容不下字符的情况，避免整份报告因为一个生僻字丢失。

## 二、我不同意 / 已修的两处

### 1. `_fmt_tags` 的"等 N 类"报的是总类别数（`render.py:224-241`）

`parts.append("等 {0} 类".format(len(ordered)))` 在 `limit=3`、实际 4 类时输出
"等 4 类"：前三个类别已经显示过了，读者会以为还有四个没显示。正确值是
`len(ordered) - limit`（4 - 3 = 1）。我已改成剩余数，并保留 `len(ordered) > limit`
的判断，所以恰好 3 类时不会出现"等 0 类"。

另外我保留了一点意见：`、` 后面直接挂"等 N 类"读起来仍像并列项，写成
"（另 N 类）"更清楚；但为了不改变既有文案与测试断言，我只修了数字。

### 2. 画像表的"参与条目"和 `share` 不是同一个分母（`render.py:360-365`、`render.py:487-492`）

这一列原来遍历 `item.authors` 数**合并条目**，而 v1.2 之后 `share` 的分母是
**原始条目**数（`item.versions` 的总数）。样例里 Aster 恰好都是 6 条，所以看起来
没事；一旦某人在同一 eid 上写了两版，或双方共同记录同一 eid，两列就会给出
无法互相解释的数字（例如"6 条 / 54.5%"，读者按 6/7 算不出 54.5%）。Bramble 在
自己的笔记里也写了"参与条目是从 item.authors 数出来的"——那句话在 v1.2 之前
成立，之后就成了过期约定。

我已把终端与 Markdown 两处都改成遍历 `item.versions` 按 `version.author` 计数，
表头改为"原始条目"（`render.py:379`、`render.py:494`），让这一列与 `share` 同源。
`tests/test_duolog.py` 里断言旧表头的那一行也同步改了，否则 56 个测试会红。

## 三、一个没改但想记下的观察

`cli.py` 的 `_run_merge` 原来把"读两个文件 → 解析 → 收集 ParseIssue → 判断
error"这一整段写死在函数里。我接 `explain` 时需要一模一样的语义（读不了=2、
解析 error=1、stderr 前缀 `duolog:`），复制一遍就会留下两份迟早漂移的退出码
判断，所以抽成了 `cli.py:170-199` 的 `_load_entries`，`_run_merge` 与
`_run_explain` 共用。这是重构而不是行为变更：告警格式、打印顺序、返回值都
保持原样。
