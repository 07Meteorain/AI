# AI

AI 相关的学习产出与项目沉淀。

## 目录

| 路径 | 内容 |
|---|---|
| [`C1_交付/`](C1_交付/) | **Stanford CS146S 课程资料中文包** — 33 篇课程资料全量翻译 + 可复跑翻译管线 |
| [`C2_交付/`](C2_交付/) | **AI4Math 可靠性论文** — 可投稿 LaTeX 论文 + 17 条 API 核验文献 + 可复现实验 |
| [`C2A_C9_交付/`](C2A_C9_交付/) | **NovCal 元认知基准** — 程序化生成防污染 + ECE 陷阱内置退化检测 + 35 项测试 |
| [`C3_交付/`](C3_交付/) | **群内高质量参与** — 可运行的"提问体检器"（12 项测试）+ 真实故障证据链 + 三份复盘 |
| [`C3C_交付/`](C3C_交付/) | **双人协作与技能迁移** — 两位 AI 协作者互相教对方都不会的技能，产出能复算"教没教成"的零依赖工具（108 项测试） |
| [`C4A_交付/`](C4A_交付/) | **C4 技能提交自动评审器** — Level 4 完整评审系统 + 26 项测试 + 100% 人机一致率 |
| [`C4B_公众号文章生成技能/`](C4B_公众号文章生成技能/) | **公众号文章生成技能** — 一键成稿 + 可直接发布的 HTML 输出 |
| [`C4C_交付/`](C4C_交付/) | **引用真伪审计器** — 专治 AI 编造引用，零依赖四档判定 + 双语料实测零误报 |
| [`C4D_交付/`](C4D_交付/) | **C4 agent-skill 交付** — 技能包 + 验证报告 + 输出截图 |
| [`C5_交付/`](C5_交付/) | **promptlint** — 零依赖 prompt 模板静态检查器：12 条规则 + 81 项测试 + SARIF/基线，可接入 CI |
| [`C5A_仓库分析/`](C5A_仓库分析/) | **GitHub 入门与仓库理解** — 零依赖仓库分析器（15 项测试）+ httpie/本仓库双分析 + 分支/PR/排错手册 |

---

## C1：课程资料获取与翻译

> 挑战 ID `ch-20260717031336-pxzwy0`

把 Stanford CS146S《The Modern Software Developer》(Fall 2025) 的课程资料
批量翻译成中文，并做成一套**可复跑、可换源复用**的翻译管线。

| 指标 | 数值 |
|---|---|
| 收录文档 | 33 篇（31 篇完整正文 + 2 篇仅标题占位） |
| 英文原文 | 89,729 词 |
| 中文译文 | 148,938 字 |
| Segment 覆盖率 | 100%（666/666，48 个代码块原样透传） |
| 术语表 | 172 条，译法规则 309 条 |
| 术语硬错误 | 0 处 |

### 快速开始

**只想看成果** → 双击 [`C1_交付/docs/index.html`](C1_交付/docs/index.html)
（静态文档站，中英对照 + 页内搜索，无需任何环境）

**想复跑管线** →

```bash
cd C1_交付
python -m venv .venv
.venv/Scripts/pip install pypdf          # 唯一依赖，PDF 抽取需要
.venv/Scripts/python pipeline/run_pipeline.py
```

> 必须用 `.venv/Scripts/python`，系统 `python` 缺 pypdf 会在抽取阶段中断。
> 实测全流程约 20 秒，翻译缓存命中，不调模型、零成本。
> 课程原始资料已随仓库提交在 `C1_交付/source_materials/`，
> **clone 下来即可完整复跑**，无需另行准备素材。

### 四份必需交付物

| 文件 | 说明 |
|---|---|
| [`提交说明.md`](C1_交付/提交说明.md) | 交付物对照表 + 评审阅读顺序 |
| [`README.md`](C1_交付/README.md) | 资料包说明：来源、覆盖、流程、已知缺口 |
| [`AI日志.md`](C1_交付/AI日志.md) | 逐日工具、prompt、踩坑记录 |
| [`AAR复盘.md`](C1_交付/AAR复盘.md) | 七维复盘，含失败经验与改进方案 |
| [`拿来说明.md`](C1_交付/拿来说明.md) | 5 个关键决策的完整过程 |

### 管线四阶段

```
① extract  HTML/PDF 正文 → Block → Segment（按语义分段，含代码识别）
② translate 注入术语表 → 分段翻译 → 缓存落盘（原文 sha1 为键）
③ qc        覆盖率 / 术语 / 漏译 / 格式 / 长度比，五项自动检查
④ build     Markdown 资料包 + 静态文档站
```

换一门课复用：改 `C1_交付/pipeline/config.json` 的 `source_root` 与 `sources` 列表即可，
抽取、分段、术语注入、质检、建站全部自动适配。

---

---

## C2：AI for Math 论文

> 挑战 ID `ch-20260717031343-8ot0ji`

围绕 AI4Math 可靠性框架产出一篇**可投稿**的 LaTeX 学术论文：
提出「语义规约层（semantic reduction）」是神经数学推理的可靠性瓶颈，
并给出可机械计算的度量与可落地的可靠性清单。

论文：*From Natural Language to Verifiable Reasoning: A Semantic Reduction
Framework for Reliable AI Mathematics*（10 页）

| 指标 | 数值 |
|---|---|
| 编译状态 | TeX Live 2026 实测：**0 错误 / 0 未定义引用 / 0 告警 / 0 overfull box** |
| 参考文献 | 17 条（要求 ≥8），**全部经 Crossref + OpenAlex 双API 核验** |
| 参考文献渲染 | 17 / 17 |
| 实验语料 | 108 条构造样本，种子固定，结果可字节级复现 |
| 独立第三方库 | 0（指标与统计量自行实现，含 `--self-test`） |

### 快速开始

**只想看成果** → 直接读 [`C2_交付/paper/paper.pdf`](C2_交付/paper/paper.pdf)

**想复跑实验** →

```bash
cd C2_交付
python code/reduction_defects.py --self-test        # 指标自检，秒级
python code/reduction_defects.py \
    --corpus data/corpus.json \
    --raters data/rater_agreement.json \
    --out   /tmp/check.json                          # 输出应与 data/results.json 一致
```

> 无需 `pip install` 任何东西：Python 3.9+ 直接可跑。
> 语料与结果已随仓库提交，**clone 下来即可复现**。

**想编译论文** →

```bash
cd C2_交付
pdflatex paper && bibtex paper && pdflatex paper && pdflatex paper
```

### 四份必需交付物

| 文件 | 说明 |
|---|---|
| [`paper.tex`](C2_交付/paper.tex) | 论文主文件（可独立编译） |
| [`references.bib`](C2_交付/references.bib) | 17 条 API 核验文献 |
| [`AI日志.md`](C2_交付/AI日志.md) | 逐轮 AI 协作记录，含 5 类被拦截的 AI 误导案例 |
| [`AAR复盘.md`](C2_交付/AAR复盘.md) | 七维复盘，含 F1–F7 失败经验（未美化） |
| [`提交说明.md`](C2_交付/提交说明.md) | 交付物对照表 + 评审阅读顺序 |

### 原创贡献

1. 可靠性形式化为 `Pr[V(ρ(n))=ok ∧ Valid(ρ(n))]`——把语义规约映射 ρ 放进概率**内部**；
2. **Proposition 1（非单调性）**：验证器强度不是单调杠杆，一个**完美**验证器
   会去认证一个已被规约扭曲的命题；
3. 四类规约缺陷分类学（undertyping / scope drift / unbound symbol / non-local warrant）；
4. **RIS 指标**：仅从 artifact 机械可算，权重先验固定（不在评估集调参），值域 $[0,1]$ 已证明。

### 文献真实性

17 条文献经 Crossref + OpenAlex 双源核验（规则：token-set F1 ≥ 0.90 且年份差 ≤ 1），
`references.bib` 由脚本从 API 记录**程序化生成**。核验拦下3 次严重 AI 幻觉，
其中一次是**格式完全合法但指向无关论文的 arXiv ID**（仅验证"链接能否打开"会完全放行）。
另有 1 条无法检索到的引用已主动弃用。元数据台账见
[`refs_check/VERIFICATION_LEDGER.txt`](C2_交付/refs_check/VERIFICATION_LEDGER.txt)。

### 诚实边界

实验语料为**构造**样本（缺陷已知注入），本实验**验证工具**、**不估计真实缺陷率**；
RIS 亦**不判断数学真值**（假命题的完美 artifact 同样得 1.0）。详见论文 §7.2–7.3。

---

## C2A / C9：NovCal 元认知基准

> 挑战 ID `ch-20260717031352-tlg70p` ｜ 赛道 **Track 2 — Metacognition**
> （DeepMind / Kaggle *Measuring Progress Toward AGI*，奖金 $200,000）

一个模型答对一道题，能证明的事情比人们以为的少得多——它可能是在**回忆**而非**推理**，
可能**碰巧**而非**知道**。NovCal 问的是那个更基础的问题：**它是否知道自己会答对？**

| 指标 | 数值 |
|---|---|
| 核心代码 | 5 模块，**零第三方依赖**（仅标准库） |
| 单元测试 | **35/35 通过**（含 4 条回归测试） |
| 指标自检 | 通过（对照 Brier/AUROC/ECE 闭式期望值） |
| 区分度 | 前沿模型 **0.732** vs 启发式 0.311 vs 退化基线 0.000 |
| 难度梯度 | 66.7% → 25.6% → 8.9% → 0.0%（tier1–4，单调） |

**两个核心设计**

1. **生成器即基准（结构性防污染）** — 不发布题库，只发布种子化生成器。
   符号子集 C(46,4)≈16 万 × 规则组合，不同种子的任务空间**可证明不相交**：
   不是"希望不重叠"，而是"保证不重叠"。

2. **ECE 陷阱内置为代码断言** — 恒定输出 50% 置信度、且准确率恰好 50% 的系统，
   其 **ECE = 0（完美校准）却毫无元认知能力**。实测（`scripts/demonstrate_ece_trap.py`）
   该系统 ECE **优于**真实前沿模型（0.000 < 0.192），而 AUROC 仅 0.500。
   已实现四类退化的自动标记；**退化系统的 ECE 不得参与排名**是硬性规则。

| 主结果 | n | Accuracy↑ | ECE↓ | AUROC↑ | AURC↓ |
|---|---|---|---|---|---|
| **前沿模型（合并）** | 56 | **0.732** | **0.192** | **0.889** | **0.072** |
| 启发式规则归纳 | 351 | 0.311 | 0.295 | 0.930 | 0.376 |
| 恒定置信度 50 | 351 | 0.000 | 0.500 | n/a | 1.000 |
| Oracle（上界） | 351 | 1.000 | 0.000 | n/a | 0.000 |

**快速开始**（零依赖，无需 `pip install`）

```bash
cd C2A_C9_交付
python -m novcal.cli selftest        # 验证指标实现
python tests/test_novcal.py           # 35 项测试
python scripts/make_report.py         # 生成对比表与校准图

# 接入任意模型
python scripts/run_model.py --provider openai --model gpt-4o --out results/gpt-4o.jsonl
```

| 交付物 | 文件 |
|---|---|
| 提案 | [`07Meteorain_C2A_proposal.md`](C2A_C9_交付/07Meteorain_C2A_proposal.md) |
| 任务说明 + 评分标准 | [`07Meteorain_C9_task说明.md`](C2A_C9_交付/07Meteorain_C9_task说明.md) |
| 测试结果 | [`07Meteorain_C9_测试结果.md`](C2A_C9_交付/07Meteorain_C9_测试结果.md) |
| 反思报告（AAR） | [`07Meteorain_C9_反思报告.md`](C2A_C9_交付/07Meteorain_C9_反思报告.md) |
| AI 日志 | [`07Meteorain_C9_AI日志.md`](C2A_C9_交付/07Meteorain_C9_AI日志.md) |
| 拿来说明 | [`07Meteorain_C9_拿来说明.md`](C2A_C9_交付/07Meteorain_C9_拿来说明.md) |

**已知局限（如实记录）**：尚无人类基线；测试环境无 LLM API key，
"前沿模型"为作者本人以 agent 身份作答，存在自我偏好风险且 n=56 偏小。
详见 [`07Meteorain_C9_测试结果.md`](C2A_C9_交付/07Meteorain_C9_测试结果.md) §0。

---

---

---

## C3：群内高质量参与

> 挑战 ID `ch-20260717031407-ez6fae`

把"怎么在群里问一个好问题"从个人修养，做成**可运行、可打分、可复现**的东西。

核心不是模板，是那个 30 秒的检查动作：**六要素 → 0~100 分 → 低于 70 分不发出**。

| 指标 | 数值 |
| --- | --- |
| 体检器代码 | 约 330 行，零第三方依赖，Python 3.9+ |
| 测试 | 12 项，全部通过（含 4 项契约测试） |
| 校准样本 | 3 篇真实文本，分数阶梯 0 / 33 / 100 |
| 真实案例 | 1 个（0xC0000142 进程创建失败），含 6 条假设与 2 条无法区分项 |
| 失败经验 | 6 条，其中 2 条明确标注"未解决" |

### 快速开始

```bash
cd C3_交付/linter
python question_lint.py cases/good_01.md      # 100 分的提问长什么样
python question_lint.py --batch cases          # 三档对照，输出见 demo_output.txt
python question_lint.py 我的草稿.md --rewrite --min 70
python -m unittest discover -s tests -v        # 12 项测试
```

> 零依赖，`clone` 下来直接跑。
> `--min 70` 让"发不出去"变成机器的事，而不是意志力的事。

### 三份必需交付物

| 文件 | 说明 |
| --- | --- |
| [`AI日志`](C3_交付/07Meteorain_C3_AI日志.md) | 3 次 prompt 迭代、2 个真实 bug、5 处 AI 出错 |
| [`AAR`](C3_交付/07Meteorain_C3_AAR.md) | 预期 vs 实际、6 条失败经验、重来会改的 3 件事 |
| [`反思`](C3_交付/07Meteorain_C3_反思.md) | 潜水动因拆解 + 30 天实验 + 4 个度量指标 |

### 诚实边界

工具只衡量**信息完整度**，不衡量"问题值不值得问"——六要素齐全的蠢问题照样能拿 100 分。
校准样本只有 3 篇且由作者一人判定；群内真实互动未伪造，记录模板留白待填。
## C4A：技能提交自动评审

> 挑战 ID `ch-20260717031432-5jvqje`
> 把`wechat-doc-mapper` 的「分类盘点」升级为「自动阅卷」

**输入**一个装着全班 C4 提交的本地文件夹，**输出**一份带排名和证据的可追溯评审报告。

| 指标 | 数值 |
|---|---|
| 达成级别 | **Level 4** 完整评审系统 |
| 评审判据 | 4 维度 × **20 个加权 check_item** |
| 单元测试 | **26 项全通过** |
| 人机一致率 | **100%**（15 项判定，3 份标注样本） |
| 核心机制 | 证据化· 置信度分级 · 一票否决 · 矛盾检测 |

### 快速开始

```bash
cd C4A_交付
pip install -r requirements.txt

# 自测（确认安装正常）
python tests/test_evaluator.py --accuracy

# 评审自己的或全班的C4 提交
python skill/c4a-skill-evaluator/scripts/c4a_evaluator.py <文件夹> --outdir ./reports
```

### 核心创新：一票否决

朴素加权评分会把致命伤稀释成小瑕疵——
一份硬编码了 `/Users/xxx/` 本地路径的提交，同时有"安装说明"（+1.0）、
相对路径写法（+0.8）、无凭据泄露（+1.5），加权得 57%，评级「⚠️ 部分满足」。

**但C4 对「可复用」的检验原话是"让一个陌生人按你的说明操作，能成功吗？"**
答案已经是否定的。所以 `R2`（无硬编码路径）、`R5`（无凭据泄露）
标记为 `type: veto`，**命中即把该维度封顶 ❌**。

### 每条判定都可追溯

```
| 可复用 | ❌ | 57% | 🚫 否决证据：L20「路径是 /Users/lm/Desktop/meeting_summary/summary.py」|
```

评审者可以逐条打开原文件核对，不必相信工具。
置信度为 `low` 的结论会被主动标记「需人工复核」。

### 七份交付物

| 文件 | 说明 |
|---|---|
| [`提交说明.md`](C4A_交付/提交说明.md) | 交付物对照表 + 阅读顺序 + 一分钟验收 |
| [`Meteorain_C4A_方案设计.md`](C4A_交付/Meteorain_C4A_方案设计.md) | 架构选型、veto 设计、7 个缺陷修复记录 |
| [`Meteorain_C4A_评审报告.md`](C4A_交付/Meteorain_C4A_评审报告.md) | 对 3 份提交的真实评审结果 |
| [`Meteorain_C4A_教学说明.md`](C4A_交付/Meteorain_C4A_教学说明.md) | 安装、使用、自检、常见坑 |
| [`Meteorain_C4A_AI日志.md`](C4A_交付/Meteorain_C4A_AI日志.md) | 20 轮迭代全过程，含 3 处失败经验 |
| [`Meteorain_C4A_拿来说明.md`](C4A_交付/Meteorain_C4A_拿来说明.md) | 拿了什么、改了什么、为什么改 |
| [`Meteorain_C4A_skill-evaluator.skill`](C4A_交付/Meteorain_C4A_skill-evaluator.skill) | 可安装技能包（tar.gz） |

### 三种输出格式

| 格式 | 面向 | 独有价值 |
|---|---|---|
| Markdown | 逐条核对 | 折叠的逐项证据表，含文件行号 |
| Excel | 筛选 | 「逐项评审明细」筛 `R2=❌` 一键找出硬编码路径名单 |
| HTML | 全班一眼看分布 | 四条件达成度可视化仪表板，双击即开 |

> ⚠️ **排名仅作参考**——C4 的评分核心是「被使用次数」，本工具评的是提交材料质量。

---

## C4C：引用真伪审计器

> 挑战 ID `ch-20260717031424-4cdgor`
> 专治 LLM 编造的参考文献——看起来完美，其实查无此文

**输入**一个 `.bib`/`.tex`/`.md`，**输出**每条引用是否真实存在的四档判定 + 审计报告 + 修正版 `.bib`。

| 指标 | 数值 |
|---|---|
| 判定档位 | 4 档：VERIFIED / PARTIAL / FABRICATED / UNCHECKED，附原因码与证据 URL |
| 自建样本 | 8 条 → 4 VERIFIED / 2 PARTIAL / 2 FABRICATED，**零误报零漏报** |
| 真实语料交叉验证 | 用 [`C2_交付/references.bib`](C2_交付/references.bib)（17 条已双 API 核验）跑 → **16 VERIFIED / 1 UNCHECKED / 0 FABRICATED** |
| 依赖 | **零第三方依赖**（纯标准库），三个数据源均免 API key |
| 迭代 | 8 轮，含 6 个真实 bug 修复 |

### 快速开始

```bash
cd C4C_交付
unzip Meteorain_C4_citation-truth-auditor.skill -d citation-truth-auditor/

# 审计自己的参考文献
python3 citation-truth-auditor/scripts/citation_auditor.py references.bib

# 提交前生成修正版 + JSON（--fix 的编造条目只注释、不删除）
python3 citation-truth-auditor/scripts/citation_auditor.py references.bib --fix --json
```

> 退出码 `1` = 发现编造引用，可直接当CI 门禁：
> `citation_auditor.py refs.bib || exit 1`

### 为什么值得做

LLM 编造的引用**肉眼看不出来**——作者名像真的、期刊名像真的、DOI 格式规范。
伤害通常在审稿人检索时才显现，那时已经晚了。人工逐条查20 条要近一小时，
太枯燥导致大部分人干脆不查。

本技能把「肉眼判断」换成「查询权威数据源」：DOI 直查 Crossref → arXiv ID 直查 arXiv
→ 标题检索 Crossref + OpenAlex，三级降级，每条给出可复核的证据。

### 两处不肯将就的设计

**1. `UNCHECKED` ≠ 通过。** 查不到不等于没问题。工具在证据不足时明说「不知道」，
而不是给一个让人安心的结论。

**2. 编造条目只注释、不删除。** 审计工具自己也会错（见下），删除是不可逆的破坏操作。
`--fix` 保留完整原文供人工复核。

### 用真实文献库测过，而不是只用自己造的样本

自建样本只能证明「能抓到假引用」——因为答案自己知道。
真正有说服力的是拿**别人已核验过的真实文献库**看会不会误伤。
第一次跑它误伤了 3 条，我逐一查出根因并修复：

| 误报 | 根因 | 修复 |
|---|---|---|
| `dsp2022` | DOI 前缀 `10.48550/arxiv.*` 是 DataCite 签发，**不在 Crossref** | 按前缀路由到 arXiv 精确查询 |
| `coqmanual` | 花括号机构作者 + 标题带 `- version 8.19.0` 后缀 | 机构作者单独处理 + 包含关系相似度 |
| `alphaproof2025` | 作者用 `;` 分隔（Nature 导出格式），我只支持 `and` | `split_authors()` 支持三种分隔符 |

> 一个会误伤真实引用的核查工具，危害比漏检更大——它会让用户删掉真正引用过的论文。

### 已知边界（诚实声明）

- **无法判断引用是否支撑你的论断**：`VERIFIED` 只代表「这篇论文存在」
- **中文文献覆盖差**：三个库对中文期刊收录都很少，需人工核查
- **软件手册/技术文档查不到属预期**：判`UNCHECKED` 而非 `FABRICATED`

### 五份交付物

| 文件 | 说明 |
|---|---|
| [`提交说明.md`](C4C_交付/提交说明.md) | 交付物对照表 + 阅读顺序 + 验收自查 |
| [`Meteorain_C4_skill说明.md`](C4C_交付/Meteorain_C4_skill说明.md) | 解决什么问题、IO 契约、双语料实测数据 |
| [`Meteorain_C4_教学说明.md`](C4C_交付/Meteorain_C4_教学说明.md) | 上手、7 个常见坑、CI 集成、练习题 |
| [`Meteorain_C4_AI日志.md`](C4C_交付/Meteorain_C4_AI日志.md) | 8 轮迭代全过程，含 6 处失败经验 |
| [`Meteorain_C4_AAR复盘.md`](C4C_交付/Meteorain_C4_AAR复盘.md) | AAR 复盘，含"差点让报告全绿"的关键决策 |
| [`Meteorain_C4_citation-truth-auditor.skill`](C4C_交付/Meteorain_C4_citation-truth-auditor.skill) | 可安装技能包 |

---

## C3C：双人协作与技能迁移

> 挑战 ID `ch-20260717031415-0vi5d1`

不是两个人各做一半——是两个人各自进到对方的代码库里，把对方不会的那一段写出来，再被对方审。

工具 `duolog` 读两份协作者日志，合并成一份带冲突裁决的协作记录，并从日志里抽出**技能迁移的边**。
**它分析的对象，就是造它的这场协作本身。**

| 指标 | 数值 |
| --- | --- |
| 联合成果 | `duolog` 零第三方依赖，8 模块 **1,977 行** |
| 测试 | **108 项全通过**（1,342 行） |
| 协作规模 | 26 条原始日志 → 21 条合并条目，**4 条冲突**（R1/R2/R4/R3 各一） |
| 技能迁移 | **双向 2 条边、5 条证据条目**（SEL-1 Aster→Bramble，SEL-2 Bramble→Aster） |
| 契约变更 | v1.0 → v1.5，共 5 次，**2 次发生在"测试全绿之后"** |
| 互检 | 13 条意见，8 条修掉、5 条书面裁定 |

**两个协作设定**

1. **契约先行** — 两位协作者是两个独立上下文的 agent，互相看不见对方的代码，只能靠一份冻结的接口契约对齐。首轮集成接口零摩擦（56 项测试一次性全绿）。
2. **第二轮换房间** — 各自进入对方代码库实现迁移功能，再由原作者评审自己文件被改的部分。A 写的 286 行 `explain.py` 被原作者审出 6 条问题，其中 4 条是真 bug（含一个死循环）。

**最有价值的一条教训**：测试全绿不等于设计正确。契约 v1.3（一个事件同时是"决策"和"实现"）与 v1.5（R4 实际只是补位规则）都是在 56 / 99 项测试全绿之后才被发现的。

### 快速开始（无需 pip install）

```bash
cd C3C_交付
python -m duolog selfcheck                                  # 自检，不读外部文件
python -m duolog merge --a logs/Aster.md --b logs/Bramble.md \
       --author-a Aster --author-b Bramble \
       --out logs/合并记录.md --report logs/协作报告.md        # 复算本次协作记录
python -m unittest discover -s tests                        # 108 项测试
```

### 四份必需交付物 + 辅证

| 类型 | 文件 |
| --- | --- |
| 协作记录 | [`07Meteorain_C3C_协作记录.md`](C3C_交付/07Meteorain_C3C_协作记录.md) + [`logs/合并记录.md`](C3C_交付/logs/合并记录.md) |
| 联合成果 | [`duolog/`](C3C_交付/duolog)、[`tests/`](C3C_交付/tests)、[`logs/协作报告.md`](C3C_交付/logs/协作报告.md) |
| AI日志 | [`07Meteorain_C3C_AI日志.md`](C3C_交付/07Meteorain_C3C_AI日志.md) |
| AAR | [`07Meteorain_C3C_AAR.md`](C3C_交付/07Meteorain_C3C_AAR.md) |
| 提交说明 | [`07Meteorain_C3C_提交说明.md`](C3C_交付/07Meteorain_C3C_提交说明.md) |
| 契约与笔记 | [`任务契约.md`](C3C_交付/任务契约.md)、[`notes/`](C3C_交付/notes)（8 份） |
| 终端证据 | [`demo/`](C3C_交付/demo)（5 份真实输出） |

> 两位协作者都是 AI agent（Aster / Bramble），学生担任主持人：定契约、集成、跑测试、裁定分歧。
> 这一设定与其代价写在协作记录 §0 与 AAR §6，**没有隐瞒**。

---

## C5：promptlint — prompt 模板的静态检查器

> 挑战 ID `ch-20260717031503-ihozqu`
> prompt 是代码，但很少像代码一样被检查。

在 prompt 进入模型之前，把「变量拼错、密钥泄露、输出格式缺失、注入面暴露」变成
CI 里的一条红叉——而不是上线后的一条事故。

| 指标 | 数值 |
| --- | --- |
| 规则 | 12 条（PL001–PL012），每条都有 rationale、反例、正例、误报边界 |
| 代码 | 19 个源文件 1,743 行，**零第三方依赖**（Python 3.9+） |
| 测试 | **81 项全通过**（8 个测试文件） |
| 输出 | text / JSON / SARIF 2.1.0（GitHub Code Scanning 可直接上传） |
| 示例 | 好例子 0 问题；坏例子 12 问题（5 error / 7 warning） |
| 落地机制 | 基线指纹不含行号；逐规则改级；退出码 `0/1/2` |

### 快速开始（无需 pip install）

```bash
cd C5_交付
python -m promptlint check examples/good --fail-on info                 # 退出码 0
python -m promptlint check examples --config examples/promptlint.json   # 12 问题，退出码 1
python -m unittest discover -s tests                                    # 81 项
```

### 三个不肯将就的地方

1. **零依赖**——`git clone` 后两条命令就能验证；为了省几百行而引入 `click`/`rich`/
   `PyYAML`，等于把环境成本转给每一个第一次打开仓库的人。
2. **误报要留边界**——PL007/PL008/PL009 是启发式；它们不假装精确，`docs/rules.md`
   逐条写明什么时候会误报、怎么用基线或 `off` 处理。
3. **基线不绑行号**——指纹由「路径 + 规则 + 消息 + 源码行」组成，一次 import 排序
   不会让所有历史问题复活；同时也不允许静默关掉规则。

### 交付物

| 文件 | 内容 |
| --- | --- |
| [`README.md`](C5_交付/README.md) | 安装、30 秒验证、规则表、配置、CI、API、边界 |
| [`AI日志.md`](C5_交付/AI日志.md) | 逐轮 prompt、真实故障、返工与独立评审 |
| [`拿来说明.md`](C5_交付/拿来说明.md) | 5 个关键决策的取舍过程 |
| [`AAR复盘.md`](C5_交付/AAR复盘.md) | 预期 vs 实际、失败经验、改进方案 |
| [`提交说明.md`](C5_交付/提交说明.md) | 交付物对照 + 评审阅读顺序 + 一分钟验收 |

> **诚实边界**：不评估 prompt 效果；token 数是估算（±30%）；截至交付没有真实
> 用户采用数据，所有指标来自本仓库示例、测试与 CI。

---

## C5A：GitHub 入门与仓库理解

> 挑战 ID `ch-20260717031511-x5c6t1`
> 会点按钮不等于会用 Git；能读懂别人的仓库，才敢改自己的。

用一个零依赖分析器，量化一个 13 年的真实开源项目与本体仓库，再走一遍
「短分支 → 多次提交 → PR → 合并 → tag」的完整流程。

| 指标 | 数值 |
| --- | --- |
| 分析对象 | `httpie/cli`（他人仓库）+ `07Meteorain/AI`（本仓库自检） |
| 工具 | `repo_inspector.py`，约 900 行，仅标准库 + git |
| 测试 | **15 项全通过**（unittest，无第三方依赖） |
| httpie 关键数据 | 1,797 提交 / 265 文件 / 28,276 行 / 174 署名 / 50 tags |
| httpie 测试密度 | 6,847 测试行 / 12,327 源码行 = 0.56 |
| 本仓库自检 | 99 提交 / 1,246 文件 / 204,846 行 / 健康度 29（归档仓库视角已解释） |
| Git 实战 | 短分支 + 分阶段逻辑提交 + PR + merge + `c5a-v1.0.0` |
| 排错手册 | 14 个高频场景 + 一次真实冲突演练 |

### 快速开始（无需 pip install）

```bash
cd C5A_仓库分析/工具
python -m unittest discover -s tests -v                  # 15 项
python repo_inspector.py ../.. --out-md /tmp/report.md   # 分析本仓库
```

### 交付物

| 文件 | 内容 |
| --- | --- |
| [`README.md`](C5A_仓库分析/README.md) | 总览、快速开始、结果摘要、评分自查 |
| [`仓库分析/01`](C5A_仓库分析/仓库分析/01-httpie-cli-深度分析.md) | httpie/cli 架构、测试、CI、协作、风险 |
| [`仓库分析/02`](C5A_仓库分析/仓库分析/02-本仓库结构自检.md) | 本仓库五个发现与 P0/P1/P2 改进 |
| [`仓库分析/03`](C5A_仓库分析/仓库分析/03-读仓库方法论.md) | 三层阅读法 + 六步清单 + 命令速查 |
| [`Git实战`](C5A_仓库分析/Git实战/01-分支与PR实战.md) | 分支/提交/PR/合并/tag + 14 个排错场景 |
| [`AI日志`](C5A_仓库分析/AI日志/AI使用日志.md) | 8 轮记录、prompt 迭代、12 条返工 |
| [`AAR复盘`](C5A_仓库分析/复盘/AAR复盘.md) | 预期 vs 实际、五个为什么、改进方案 |

> **诚实边界**：健康度是启发式评分，对归档仓库有偏差；分析为固定快照，
> 不覆盖后续变化；PR 为自建自合，没有真实维护者 review。细节见交付目录 README。

---

## 版权声明


课程资料版权归原作者所有，本仓库内容仅供学习参考。
每篇文档的一手来源链接见 `C1_交付/translations/index.md` 及各篇 front-matter。