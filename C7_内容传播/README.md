# C7 内容传播 · 一次内容传播的最小系统

> **C7 内容传播** ｜ 挑战 ID `ch-20260717031536-sfz852` ｜ 截止 2026-12-31
>
> | 必需交付物 | 位置 |
> | --- | --- |
> | **文章标题** | [文章/标题库.md](文章/标题库.md)（32 条候选 + 评分器 + 人工否决记录） |
> | **数据截图** | [数据/screenshots/](数据/screenshots/)（6 张 PNG，由 `tools/chartgen.py` 从 CSV 生成） |
> | **AI 日志** | [AI日志.md](AI日志.md)（12 轮，含 5 次失败与修正） |
>
> 另有：[AAR复盘.md](AAR复盘.md) ／ [拿来说明.md](拿来说明.md) ／ [提交说明.md](提交说明.md)

**一句话**：把"发一篇文章"拆成一条能复算的流水线——文章 → 标题评分 → 渠道埋点 → 数据回收 → AAR，每一步都有产物，每一步都能被检查。

它做四件具体的事：

1. **一篇文章**：`2,529` 字的公众号长文，6 个主关、127 次提交里挑出三个真实事故，提出"验收三层"；
2. **一个标题评分器**：32 条候选 × 5 维打分 + 一票否决，Python 与 JS 两套实现必须给出同一个分；
3. **一套传播设计**：4 个渠道 × 6 个参数、UTM 埋点矩阵、A/B 样本量计算（结论是"这个量级做不了 A/B"）；
4. **六张数据截图**：标题榜、渠道漏斗、七日增长、A/B 功效、正文体检、仓库事实，全部由脚本从 CSV 生成。

---

## 30 秒验收（不用装任何东西）

```bash
# 1) 打开控制台：双击 app/index.html（file:// 也能跑，无需服务器）
#    或者起一个静态服务：
python -m http.server 8000 --directory app
```

| 步骤 | 你会看到 |
| --- | --- |
| 1. 首屏「阅读」 | 正文已按公众号排版渲染，右侧按钮可新窗口打开、可看《验收清单》单页 |
| 2. 点「标题实验室」 | 输入框里是最终标题，**75/100 · 主推**；改一个字，"钩子强度"实时变化 |
| 3. 把标题改成「震惊！AI 写的东西 99% 都是假的，必看！」 | 立刻掉到 **40 分 · 弃用**（一票否决），理由里写明封顶 |
| 4. 点「渠道」 | 4 张渠道卡 + UTM 生成器（四个渠道一次生成）+ 10 条发布清单（勾选会存本机） |
| 5. 点「数据」 | 漏斗 / 七日曲线 / 仓库事实表 / 6 张截图缩略图 |
| 6. 点「复盘」 | AAR 模板（可导出 Markdown）+ 数据回收 CSV 模板 |

---

## 为什么做这个

这门课前面 6 个挑战都在做**工具**：翻译流水线、论文、prompt 检查器、评审器、仓库分析器。做到第 7 个我想做一件不一样的事：**让做出来的东西被看见**。

但"被看见"这件事本身也有工程问题：

- 标题靠灵感？那就不知道"为什么这条比那条好"，也没法复盘。
- 渠道靠感觉？那就不知道流量从哪来、哪一条值得再做一次。
- 数据靠"感觉还不错"？那就永远不知道自己错在哪。

所以这一关的产物不是"一篇文章"，而是**一条能把文章推出去的流水线**，以及**一套让每个数字都能被追溯的口径**。

文章讲的是"验收"，这一关本身也在被同一套标准验收：数字有脚本、截图有指纹、文案有漂移检测。

---

## 交付物对照

| 平台要求 | 我们的产物 | 怎么验证 |
| --- | --- | --- |
| **文章标题** | [文章/标题库.md](文章/标题库.md) | 32 条候选、5 个公式、评分表由 `tools/title_score.py` 生成；`python tools/title_score.py --check` 校验是否过期 |
| **数据截图** | [数据/screenshots/](数据/screenshots/) 6 张 PNG | `python tools/chartgen.py --check` 比对数据指纹；PNG 由 CSV 确定性渲染 |
| **AI 日志** | [AI日志.md](AI日志.md) | 12 轮，每轮含 prompt、输出要点、我的判断、失败与修正 |

---

## 目录结构

```
C7_内容传播/
├── app/                          # 传播控制台（零依赖，双击 index.html 即可）
│   ├── index.html                # 五个页签：阅读 / 标题实验室 / 渠道 / 数据 / 复盘
│   ├── styles.css                # 深色模式 + 打印样式
│   ├── article.html              # 生成的正文（公众号排版）
│   ├── checklist.html            # 生成的《验收清单》单页
│   ├── assets/shots/             # 6 张截图的副本（让 app 可以单独分发）
│   └── js/
│       ├── core/                 # 纯逻辑：titlescore / metrics / utm / csv / data(生成物)
│       ├── ui.js                 # 数据 → HTML/SVG 字符串（不碰 DOM）
│       └── app.js                # 唯一持有状态的一层
├── 文章/
│   ├── 正文.md                    # 文章源文件（唯一真源）
│   ├── 微信版.html                # 生成物：可全选粘贴进公众号编辑器
│   ├── 标题库.md                  # ← 必需交付物①
│   ├── 多平台改编.md              # 知乎 / 小红书 / 即刻 三版改编
│   └── 验收清单.html              # 转化用的单页（12 条清单）
├── 数据/
│   ├── 指标口径.md                # 每个数字的定义、来源、能不能复算
│   ├── title_rubric.json          # 评分规则（单一真源，Python/JS 共用）
│   ├── titles.csv                 # 32 条候选（手写）
│   ├── titles_scored.csv          # 生成物：评分结果
│   ├── 标题评分表.md              # 生成物：人看的排行榜
│   ├── projection_params.csv      # 4 渠道 × 6 参数的推演口径
│   ├── repo_facts.csv             # 生成物：仓库事实快照（钉在 master@165f7d3）
│   ├── declared_tests.csv         # 各关 README 自报的测试数（带出处与证据串）
│   ├── utm.csv                    # 四渠道埋点链接
│   └── screenshots/               # ← 必需交付物②（6 张 PNG + manifest.json）
├── tools/
│   ├── title_score.py             # 标题评分（确定性，生成 CSV/MD/fixture）
│   ├── chartgen.py                # CSV → 6 张 PNG（Pillow，手绘坐标系）
│   ├── repo_facts.py              # 仓库事实快照 + 自报/实测对账
│   ├── gen_data_js.py             # CSV → app 用的 data.js（带 --check）
│   └── build_article.py           # 正文 → 公众号 HTML + app 资源（带 --check）
├── tests/                         # 50 项，node --test，零依赖
├── AI日志.md / AAR复盘.md / 拿来说明.md / 提交说明.md / README.md
```

---

## 怎么跑

### 只看：双击打开

双击 `app/index.html`。所有脚本都是普通 `<script>`（不是 ES module），所以 `file://` 下也能跑。

### 重新生成全部产物

```bash
# Python 侧（需要 Pillow；标题评分与仓库事实只用标准库）
python tools/title_score.py        # -> 数据/titles_scored.csv、标题评分表.md、tests/fixtures/title_scores.json
python tools/chartgen.py           # -> 数据/screenshots/*.png + manifest.json
python tools/gen_data_js.py        # -> app/js/core/data.js
python tools/build_article.py      # -> 文章/微信版.html、app/article.html、app/checklist.html、app/assets/shots/
```

`repo_facts.py` 需要完整 git 历史（重新统计提交数时才跑）：

```bash
python tools/repo_facts.py --repo ..    # 在仓库根跑，重新生成 数据/repo_facts.csv
```

### 校验（CI 就是跑这些）

```bash
python tools/title_score.py --check     # 评分产物是否过期
python tools/chartgen.py --check        # 截图与数据是否同步（比对数据指纹，不是像素）
python tools/gen_data_js.py --check     # data.js 是否过期
python tools/build_article.py --check   # 正文改了但没重新渲染会红
python tools/repo_facts.py --check      # 自报=实测、证据串存在、合计对得上
python tools/pages_check.py             # 发布前自检：截图副本 / 正文 HTML / 数据指纹
node --test tests/*.test.js             # 50 项
```

### app 里没有服务端

所有数据在 `app/js/core/data.js` 里（由 CSV 编译而来）。这是刻意的：`file://` 下 `fetch()` 会被 CORS 拦掉，而"双击就能用"比"数据实时"重要。

---

## 数据从哪来（三层，全部可复算）

| 层 | 例子 | 谁生成 | 性质 |
| --- | --- | --- | --- |
| 仓库事实 | 127 次提交、1,355 个文件、464 项测试 | `tools/repo_facts.py` | **实测**，钉在 `master@165f7d3` |
| 正文实测 | 2,529 字、36 段、8.4 分钟 | `tools/chartgen.py` 解析 `文章/正文.md` | **实测** |
| 传播推演 | 曝光 9,860、进入正文 962 | `projection_params.csv` → `chartgen.py` | **推演**，参数公开、可复算 |

推演值不是"编"的：它是 6 个公开参数的确定性结果，参数含义、取值理由、误差范围都写在 [数据/指标口径.md](数据/指标口径.md)。发布后把真实数字填进 `数据/metrics.csv` 覆盖参数，同一张图就把误差暴露出来。

**没有任何一个数字是手打的。** 这条规则本身也有代价（见 [AAR复盘.md](AAR复盘.md) §3 第 2 条：我第一版凭印象写了 438 项测试，脚本数出来是 464）。

---

## 测试

`node --test tests/*.test.js` → **50 项，全部通过**。零测试框架依赖（只用 `node:test` + `node:assert`）。

| 文件 | 覆盖点 | 项数 |
| --- | --- | --- |
| `tests/titlescore-parity.test.js` | JS 与 Python 分数逐条一致、否决、越界、排序、纯函数 | 8 |
| `tests/metrics.test.js` | 漏斗、七日累积、权重和为 1、A/B 样本量与功效 | 9 |
| `tests/utm.test.js` | 渠道矩阵、参数顺序、不重复叠加、非法输入 | 6 |
| `tests/csv.test.js` | BOM/CRLF/引号转义/空行/round-trip | 6 |
| `tests/ui.test.js` | XSS 转义、SVG 无 NaN、渲染完整性 | 8 |
| `tests/data.test.js` | data.js ↔ CSV 对账、自报=实测、rubric 同步、快照带 commit | 7 |
| `tests/assets.test.js` | 引用完整性、生成物非空、目录条数、截图副本一致、交付物齐全 | 6 |

几条刻意的设计：

- **跨语言一致性测试**（最重要的一条）：`title_rubric.json` 是单一真源，Python 与 JS 是两套实现。32 条候选的分数必须逐条相等——这是"同一份规则不许有两种行为"的兜底。
- **目录条数 = 小标题数**：C4B 的目录生成会漏掉第一个 h2（用它的时候才发现），测试把"补齐"这件事固定下来。
- **SVG 无 NaN**：一个除零就会让整张图静默变空白，肉眼很难发现。
- **XSS 回归**：标题是用户输入，评分卡会把标题渲染出来，转义漏一处就是一个洞。
- **副本逐字节一致**：`app/assets/shots/` 与 `数据/screenshots/` 是两份，测试防它们漂移。

---

## 诚实边界

1. **没有线上数据。** 这一关交付的是"传播系统 + 可回收的模板"，不是"10 万阅读的后台截图"。所有传播数字都标了"推演"，参数公开可改（见 [数据/指标口径.md](数据/指标口径.md) §4）。
2. **不投微博/B站/视频号。** 需要持续高频或视频能力，不在本次范围内，写清楚比硬做诚实（见 [文章/多平台改编.md](文章/多平台改编.md) §5）。
3. **做不了 A/B。** 860 次曝光对 3,531 的样本需求，只有 12%。硬做只能得到噪声，所以给了替代方案（三条标题按周轮换 + 换主指标）。
4. **评分器有边界。** 它能识别"震惊体"，识别不了"看起来严谨但没出处的百分比"——B1 那条「90% 的工夫」分数很高，是我人工否决的（见 [文章/标题库.md](文章/标题库.md) §5）。
5. **测试计数是静态的。** `def test_` 计数包含被 skip 的用例；它衡量"写了多少"，不是"跑了多少通过"。
6. **读完率 / 打开率是行业经验值。** 公众号后台只有估算，其他平台不提供。误差可能到 ±50%。
7. **`app/` 里的数字是编译时快照。** 改了 CSV 要重跑 `gen_data_js.py`，否则页面显示旧的——`--check` 和 CI 会拦住这件事，但它不会自动更新。

---

## 和前面 6 个挑战的关系

C1–C6 攒下来的是**证据**：3 条被拦下的引用幻觉（C2）、4 档判定的审计器（C4C）、81 项测试的 lint（C5）、131 项测试的体检工具（C6）。这篇文章把它们串成一个观点：**生成成本归零之后，赢的是"验得快"的人。**

技术上也有复用：

- 复用 **C4B** 的 `wechat_publisher` 把 Markdown 转成公众号 HTML（顺手修了它目录漏条的缺陷，见 [AI日志.md](AI日志.md) 第 6 轮）；
- 复用 **C6** 的工程约定：零依赖、`file://` 可跑、`--check` 漂移检测、`node --test`；
- 复用 **C5** 的"规则单一真源 + 两套实现对齐"思路（那次是 12 条规则，这次是 5 个评分维度）。

---

## License

MIT，见仓库根目录 LICENSE。
