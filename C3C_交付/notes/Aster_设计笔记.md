# Aster 设计笔记（SEL-1）

> 交接对象：Bramble（工程侧）与主持人 Meteorain。
> 对应实现：`duolog/merge.py`、`duolog/analyze.py`。
> 已对齐契约 **v1.2**：画像、迁移、占比全部按**原始条目**统计；`authors`
> 并入 `skill_owner` 的非空作者名。

## 1. SEL-1 是什么

一句话：**SEL-1 是把两个人的协作日志按事件编号做确定性合并（含 R0–R3 分级裁决）、
并输出可复现指纹与协作画像/技能迁移的算法能力。**

## 2. 三个关键取舍

### 取舍一：先全量排序再分组，而不是边扫描边建表

所有 Entry 先按 `eid_key` 排序、每个 eid 内部再按 `(author, clock, line, text, eid)`
排序，然后才裁决与算指纹。多出来的 `line/text` 只是给"同一作者重复 eid"这种脏数据
做确定性兜底。

**不这样会怎样**：`dict` 插入顺序会跟着命令行里 `--a` / `--b` 的先后走，
同一组日志换个传参顺序就得到不同指纹，"同一份协作记录必须同一指纹"这条
互检底线直接失效，测试也无法用 golden 指纹。

### 取舍二：R3 坚持不裁决，`winner=None` 且双方原文都保留

R3 不是"随机挑一个"或"取作者名靠前的"：正文按作者名排序后用 `【作者】` 标注逐条拼接
（主持人已确认用单个换行分隔），冲突对象里 `winner` 留空、`resolution="needs_review"`。
被裁决掉的版本仍保留在 `MergedItem.versions` 与 `Conflict.versions` 里
（按 `(author, clock)` 排序）。

**不这样会怎样**：等于工具替人伪造了一个"共识"，真正的分歧被藏进指纹里，
人再也看不到另一方写了什么；而且 R1/R2 费劲建立的"强证据优先、弱证据次之、
拿不准就承认"的分级语义会被最后一步自毁。代价是渲染更长、`--strict` 更容易非零，
这是有意的代价。

### 取舍三：画像的每个按人数字都逐条回看原始条目（契约 v1.2）

`skill_tags` / `type_tags` / `transfers` 都只遍历 `item.versions`，按 `v.author`
把标签与证据落到具体的人；`share` 的分母是所有 `item.versions` 的总数（原始条目数），
不是合并条目数。`authors` 再把 `skill_owner` 里的非空作者名并进来。

**不这样会怎样**：用合并条目的并集标签，E-003 这种"A 写决策、B 写实现"的冲突
会被记成"B 也做了决策、也用了 SEL-1"，与逐版本的迁移边打架（Bramble 有 SEL-1
计数却查不到 SEL-1 迁移边），读的人会先怀疑工具再怀疑数据。反过来若 `authors`
只取写过日志的人，一个技能拥有者只要没写日志就会从画像里消失，等于拿日志数量
抹掉了团队成员。

## 3. 给 Bramble 的接口使用说明（交接重点）

### 3.1 导入与调用

```python
from duolog.merge import Conflict, MergeResult, MergedItem, merge
from duolog.analyze import Profile, TransferEdge, profile

result = merge(entries_aster + entries_bramble)   # 列表、元组都行
prof = profile(result.items, {"SEL-1": "Aster", "SEL-2": "Bramble"})
```

- 在 `C3C_交付/` 目录下运行（即 `duolog` 包的父目录），模块内部用的是
  `from duolog.model import ...` 绝对导入；`python -m duolog` 天然满足。
- `merge` 只读入参，不会修改你的列表；传 `Sequence[Entry]` 即可，别传生成器
  （类型上能用，但契约要求 Sequence，传列表最稳）。

### 3.2 `--json` 怎么写

```python
json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
```

- **不要** `json.dumps(result)`：它返回的是 dataclass，不是 dict，会直接 TypeError。
- `to_dict()` 的 items 顺序、stats、fingerprint 一次算好；**不要**再自行
  `sorted(result.items)` 后拼 JSON，否则 JSON 里的 items 与 fingerprint
  对应的顺序不一致（指纹算的是原顺序）。
- `--strict` 判据：`result.stats["needs_review"] > 0` 即可，等价于
  `any(item.status == "needs_review" for item in result.items)`。
- `stats` 固定 8 个键：`total_items`、`single`、`confirmed`、`resolved`、
  `needs_review`、`conflicts`、`authors`、`entries`。渲染概览直接取，
  不要再重新数一遍。

### 3.3 渲染冲突清单

- `result.conflicts` 只含 R1/R2/R3，**R0 与单版本不在其中**；不要拿
  `status != "single"` 去反推冲突，`confirmed` 也不是冲突。
- 每条 Conflict 有 `eid / versions / winner / rule / resolution / note`；
  `winner is None` 就是 R3，渲染时明确写"待人工复核"，不要显示成"已解决"。
- 想展示原文用 `item.versions`（tuple[Entry]），`Entry` 自带 `author/clock/line/text/tags`，
  也有 `to_dict()`；但 `versions` 故意**不**进 `MergeResult.to_dict()`，
  别指望 `--json` 里有它。

### 3.4 画像与迁移（v1.2 统一口径）

- `profile(result.items, skill_owner)` 的 `skill_owner` 是 `{技能编号: 拥有者}`。
- **所有按人统计都只看 `item.versions`**：`skill_tags` / `type_tags` 只统计
  `v.author == author` 的那条原始条目自带的标签；`transfers` 只认
  `v.author != owner` 且 `v` 自己带 `技能:<S>` 的条目，证据是 `v.eid`。
  不要拿 `item.tags`（并集）或 `item.authors` 反推，否则会把共同条目的标签
  算到没写它的人头上。
- `prof.transfers` 已按 `(skill, src, dst)` 排好序，同一组合的 `evidence`
  已排序去重；展示时 `", ".join(edge.evidence)` 即可。
- `prof.share` 的分母是**原始条目总数**（`sum(len(item.versions))`），不是
  `len(result.items)`，也不是 `stats["entries"]`（对正常输入二者相等，但不要
  混用）。样例里 Aster 是 6/11≈0.5455、Bramble 是 5/11≈0.4545。
  展示请用 `f"{v:.4f}"` 补零，不要再次 `round`。
- `prof.authors` 是"原始条目作者 ∪ `skill_owner` 非空作者名"，按名字排序。
  因此零条目的技能拥有者也会出现：`share` 为 `0.0`，`skill_tags` / `type_tags`
  里是空 dict，不要当成异常删掉。
- `profile` 输入空列表是合法的：若 `skill_owner` 也空，`authors` 为空元组、
  `share` 为空字典；若给了 owner，则 `authors` 含该 owner、`share` 全 0.0。
  两种情况都不抛 ZeroDivisionError。

### 3.5 空输入与指纹

- `merge([])` 合法：`items=[]`、`conflicts=[]`、`stats` 全 0、
  `fingerprint = fingerprint_of({"version": 1, "items": []})`，是固定常量。
- 指纹只依赖 `{version, items[*].to_dict()}`；`stats` 和 `conflicts` 不进指纹，
  所以渲染层改展示方式不会影响指纹（但也别拿 stats 当唯一校验）。

## 4. 我认为契约里最容易被误解的一处

**"条目"在 §7 里到底指哪一份（v1.2）。** 画像里所有按人统计的"条目"都指
`item.versions` 里的**原始条目**，不是合并后的 `MergedItem`：技能/类型计数、
迁移证据、`share` 分母全都如此。只有 `MergeResult.stats` 里的 `total_items`、
`single`、`confirmed` 等才是合并条目；同在这份 stats 里的 `entries` 又是原始
条目数。同一个词在两层里指两种粒度，最容易串。

误解成"计数看并集"会造出伪证据（A 没打 SEL-2 却被记成用过）；
误解成"share 分母用合并条目"会让"两人共同确认"同时抬高两个人的占比；
误解成"authors 只取写过日志的人"会让零日志的团队成员消失。

## 5. 留给主持人的待确认项（集成时请重点看）

1. R0 正文长度相同时，按 `(author, clock, line)` 取第一份；样例 E-001 两版正文
   完全相同，不受影响，但脏数据会依赖这个兜底。
2. `skill_owner` 里的名字若带首尾空白，我按**原名**并入 `authors`、迁移 `src`
   也用原名，只有全空白才跳过；契约没规定是否要 strip，我选择不改写人名。
3. 本机无法运行 Python（PowerShell 起不来），以上实现只做了逐行静态核对，
   语法/缩进/字段拼写请以集成测试为准。
