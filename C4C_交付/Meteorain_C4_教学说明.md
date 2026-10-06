# C4 教学说明：如何教别人用 citation-truth-auditor

> 目标：**让一个从没用过的人，照着这份文档能独立跑通，并知道该信什么、不该信什么。**
> 阅读时间约 6 分钟。

---

## 0. 给第一次使用者的30 秒版本

```bash
python3 citation_auditor.py 你的参考文献.bib
```

然后看输出里的这四类标签：

| 标签 | 你该做什么 |
|---|---|
| `[VERIFIED]` 绿色 | 不用管 |
| `[PARTIAL]` 橙色 | 看"建议修正"，改字段 |
| `[FABRICATED]` 红色 | **提交前必须删掉或换成真实文献** |
| `[UNCHECKED]` 灰色 | 自己查一遍，别当成没问题 |

就这么多。下面是细节。

---

## 1. 课前准备：确认环境（30 秒）

**唯一硬性要求：Python 3.8 或更高。**

```bash
python3 --version
# 或 Windows：
python --version
```

**不需要**：`pip install`、API key、虚拟环境、联网账号。

三个数据源（Crossref / arXiv / OpenAlex）都免费且免密钥。

> **常见疑问**："为什么不用 bibtexparser？"
> 因为装依赖会让别人第一步就卡住。零依赖是刻意设计——**能被真正用起来的技能，
> 才是好技能**。

---

## 2. 三步跑通

### 第1 步：解压

```bash
unzip Meteorain_C4_citation-truth-auditor.skill -d citation-truth-auditor/
```

Windows PowerShell：

```powershell
Expand-Archive -Path Meteorain_C4_citation-truth-auditor.skill -DestinationPath citation-truth-auditor
```

解压后应该是：

```
citation-truth-auditor/
├── SKILL.md
├── scripts/citation_auditor.py
└── references/
```

### 第 2 步：运行

```bash
python3 citation-truth-auditor/scripts/citation_auditor.py 你的文献库.bib
```

**把路径换成你自己的 `.bib` 文件。** 默认在当前目录生成报告。

### 第 3 步：看报告

终端会直接打印，同时生成 `<你的文献库>.audit.md`。

---

## 3. 读懂输出：一条长什么样

以demo 中真实运行的一条为例：

```
[FABRICATED] smith2023deep
    题名: A Deep Intelligent Neural Network Learning Model Based on Data Driven …
    作者: Smith, John A., Chen, Wei, Kumar, Rajesh
    年份: 2023  期刊: Journal of Advanced Artificial Intelligence Research  DOI: 10.1234/jair.2023.45112
    结论: 最佳匹配仅 0.39 < 阈值 0.82（最接近的是《Neural Network-Based
          Discrete-Time Adaptive ILC》），判定为编造引用
    ⚠ 幻觉指纹[2]: 标题由高频泛义词堆砌，疑似占位/编造
```

逐行解释：

| 行 | 含义 |
|---|---|
| `[FABRICATED]` | 判定结论。**这是唯一需要你行动的信息** |
| `citekey` | 你在 `.bib` 里的引用键，用于定位 |
| `题名/作者/年份/期刊/DOI` | 你**原来写的**内容 |
| `结论` | 为什么这么判。括号里的《…》是数据库里最接近的真实论文 |
| `幻觉指纹` | 静态检测到的可疑特征，`[2]`=几乎确定有问题，`[1]`=可疑 |

**关键**：`最接近的是《…》` 这句极有价值——它告诉你数据库里到底有什么，
避免你重复劳动，也帮你判断是否只是标题记错了。

---

## 4. 常用命令（按需查）

| 需求 | 命令 |
|---|---|
| 审计多个文件一起 | `python3 citation_auditor.py a.bib b.tex c.md` |
| **生成修正版文献库** | `... --fix` |
| 输出 JSON（给 CI用） | `... --json` |
| 网络慢/被限流 | `... --jobs 2 --timeout 20` |
| 完全没网 | `... --offline`（只做静态体检） |
| 误报太多 | `... --threshold 0.88` |
| 漏检太多 | `... --threshold 0.75` |

### 提交前的标准姿势

```bash
python3 citation_auditor.py references.bib --fix --json --out ./audit_out
```

产出三个文件：

| 文件 | 用途 |
|---|---|
| `references.audit.md` | 给人看的报告 |
| `references.fixed.bib` | 修正后的文献库，可直接替换 |
| `references.audit.json` | 给脚本/CI 读 |

---

## 5. CI 集成：把审计变成门禁

退出码 `1` 表示"发现编造引用"，可直接作为提交门禁：

```bash
#!/usr/bin/env bash
# pre-commit hook: 提交前自动核查引用真实性
set -e
if ! python3 citation-truth-auditor/scripts/citation_auditor.py references.bib --offline -q; then
    echo "❌ 提交被阻止：references.bib 中存在疑似编造引用，请先核查。"
    echo "   运行不带 --offline 的命令查看详情。"
    exit 1
fi
```

> 注意：`--offline` 只能查静态指纹，会漏掉"格式正确但不存在的引用"。
> CI 里建议用联网模式；网络受限时用 `--offline` 作为基础防线。

---

## 6. 常见坑（踩过的都写在这了）

### 坑 1：`python3` 命令不存在（Windows 常见）

改用 `python`，或试`py -3`：

```powershell
python citation-truth-auditor/scripts/citation_auditor.py references.bib
```

### 坑 2：全是 `UNCHECKED`，一条都没查出来

**几乎一定是断网或被限流。** 脚本不会在没有证据时瞎猜。

排查：

```bash
curl -s -o /dev/null -w "%{http_code}" https://api.crossref.org/works/10.1038/nature14539
```

返回 `200` 才说明网络通。条目很多时用 `--jobs 2` 降低并发，避免被限流。

### 坑 3：真实的会议论文被判`UNCHECKED`

因为它没有 DOI，且不在 Crossref/OpenAlex 收录范围。**这是正常现象**，
不是脚本坏了。这类情况请人工核查后保留。

### 坑 4：看到"年份不一致"就想改

**先看原因码。** 如果写的是"常见于同一论文存在重印/修订版本"，
说明是**版本漂移**——数据源记录的是另一版本，你的年份可能反而是对的。

脚本在这种情况下**故意不自动改year 字段**，就是为了避免把对的改错。
此时请人工判断，保留你确认正确的值。

### 坑 5：以为 `UNCHECKED` 就是没问题

这是最危险的误解。

> `UNCHECKED` = "我查不出结论"，不等于"没问题"。
> 把没验证过的当验证过的，等于没查。

### 坑 6：中文文献查不到

Crossref/OpenAlex 对中文期刊收录很差。这是本工具的**明确短板**，
不要因此认为你的文献有问题，但也**不能**认为它通过了——请人工核实。

### 坑 7：一条真正的论文被误判为编造

有可能。误报原因通常是：题目泛化、恰好与真实论文高度相似、或被检索到同名
不同篇的论文。

处理方式见下一节。

---

## 7. 收到 `FABRICATED` 后不要立刻删

**审计工具的判断可能出错。** 删除之前，按这个顺序确认：

1. **换个源再查** —— 把标题粘到 Google Scholar。**两个独立源都查不到**，
   才基本确定不存在。
2. **搜作者 + 关键词** —— LLM 也常把真实标题记错，未必是凭空编造。
3. **搜 arXiv / 会议官网** —— 部分会议论文不进 Crossref。
4. **确认是不是元数据错误** —— 论文真实存在、只是 bib 写错了，
   那应该**修字段而不是删条目**。
5. **检查正文是否依赖它** —— 如果依赖且找不到真实来源，
   把论述改成"该问题尚缺乏充分证据"，**不要保留假引用**。

> ⚠ 永远不要为了让报告"变绿"而删除审计结论。

---

## 8. 教别人时的三个建议

如果你是把这个技能介绍给同学，这三点最省事：

1. **先跑 demo 让他们看到红色标签。** `demo/sample_refs.bib` 里有两条
   故意编造的引用，跑一遍就会看到 `[FABRICATED]`。看到红色比听十句解释更有用。

2. **强调"存在 ≠ 支撑论点"。** 这是最容易被误解的点。脚本保证"这篇文章存在"，
   但保证不了"你引用的这句话出自这篇论文"。后半句仍然要靠读原文。

3. **给出提交前的标准命令，别给他们选择。**
   直接说："提交前跑这一条：`--fix --json`"。给出选项反而让人不做。

---

## 9. 练习题（课堂/自学用）

1. 拿你自己写过的任意 `.bib`，跑一次默认命令。几条 `VERIFIED`？
2. 故意把某条引用的年份改错，再跑一次。是否被抓出来？
3. 造一条假引用试试——
   标题用"基于深度学习的自适应智能系统框架"，作者 `Smith, John`。
   看能否被抓出来。
4. 读`references/hallucination_patterns.md` 的 3 个样例，
   找出每个的编造痕迹。

---

## 10. 一页速查

```
用法：python3 citation_auditor.py <文件.bib> [选项]
选项：--fix 生成修正版 | --json 输出JSON | --offline 离线
      --jobs N 并发数 | --timeout S 超时 | --threshold F 阈值

判定：VERIFIED 通过 | PARTIAL 修字段 | FABRICATED 删/换 | UNCHECKED 人工查
退出码：0 干净 | 1 有编造 | 2 输入不可读

三条铁律：
1. UNCHECKED ≠ 通过
2. FABRICATED 删除前先换源复核
3. VERIFIED ≠ 引用正确（存在 ≠ 支撑论点）
```

---

> **教学要点总结**：这个技能的核心价值不是"多了一个查文献的工具"，
> 而是**把一件大家知道该做、但因为枯燥而普遍不做的事，变成了自动化门禁**。
> 教别人时，重点不是教会 API，而是传达那个判断标准：
> **不要相信看起来对的东西，去查。**