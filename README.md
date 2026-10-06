# AI

AI 相关的学习产出与项目沉淀。

## 目录

| 路径 | 内容 |
|---|---|
| [`C1_交付/`](C1_交付/) | **Stanford CS146S 课程资料中文包** — 33 篇课程资料全量翻译 + 可复跑翻译管线 |
| [`C2_交付/`](C2_交付/) | **AI4Math 可靠性论文** — 可投稿 LaTeX 论文 + 17 条 API 核验文献 + 可复现实验 |
| [`C4A_交付/`](C4A_交付/) | **C4 技能提交自动评审器** — Level 4 完整评审系统 + 26 项测试 + 100% 人机一致率 |
| [`C4B_公众号文章生成技能/`](C4B_公众号文章生成技能/) | **公众号文章生成技能** — 一键成稿 + 可直接发布的 HTML 输出 |
| [`C4C_交付/`](C4C_交付/) | **引用真伪审计器** — 专治 AI 编造引用，零依赖四档判定 + 双语料实测零误报 |
| [`C4D_交付/`](C4D_交付/) | **C4 agent-skill 交付** — 技能包 + 验证报告 + 输出截图 |

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

---

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

## 版权声明


课程资料版权归原作者所有，本仓库内容仅供学习参考。
每篇文档的一手来源链接见 `C1_交付/translations/index.md` 及各篇 front-matter。