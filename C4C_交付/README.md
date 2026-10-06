# C4 技能分享与传播 — 交付包

> **技能**：`citation-truth-auditor`（引用真伪审计器）
> **作者**：Meteorain ｜ **版本**：v1.0
> **一句话**：**输入**一个 `.bib`/`.tex`/`.md` 文件，**输出**每条引用是否真实存在的四档判定 + Markdown 审计报告 + 修正版 `.bib`

---

## 📌 一句话传播语（发群里用）

> 这是我的 C4 技能——**引用真伪审计器**。输入一个 `references.bib`，输出每条引用
> 是否真实存在的判定（VERIFIED / PARTIAL / FABRICATED / UNCHECKED）+ 审计报告
> + 修正版文献库。**专治 AI 编造的参考文献**，零依赖不用装任何东西，欢迎试用和反馈！

---

## 📦 交付物清单（对齐 CHALLENGE.md 第四节）

| # | 必需交付物 | 文件 | 说明 |
|---|---|---|---|
| 1 | Skill 说明文档 | [`Meteorain_C4_skill说明.md`](Meteorain_C4_skill说明.md) | 解决什么问题、场景、IO、四条件对照、真实案例 |
| 2 | 可执行内容 | [`Meteorain_C4_citation-truth-auditor.skill`](Meteorain_C4_citation-truth-auditor.skill) | 可安装的技能包（ZIP，28.2 KB） |
| 3 | Demo | [`demo/Meteorain_C4_demo_终端输出.png`](demo/Meteorain_C4_demo_终端输出.png) | 真实运行截图（非伪造） |
| 4 | 教学说明 | [`Meteorain_C4_教学说明.md`](Meteorain_C4_教学说明.md) | 如何上手、7个常见坑、优化技巧 |
| 5 | ⚡ AI 日志 | [`Meteorain_C4_AI日志.md`](Meteorain_C4_AI日志.md) | 用了什么 AI、6 轮迭代、3 个真实 bug |
| + | AAR 复盘 | [`Meteorain_C4_AAR复盘.md`](Meteorain_C4_AAR复盘.md) | 对应 rubric `reflectionQuality`（20 分） |

**额外附赠**：可读的技能源码目录 [`citation-truth-auditor/`](citation-truth-auditor/)——
不装也能直接看、直接跑。

---

## 🚀 30 秒开始用

```bash
# 1. 解压技能包
unzip Meteorain_C4_citation-truth-auditor.skill -d citation-truth-auditor/

# 2. 审计你的参考文献（零依赖，无需 API key）
python3 citation-truth-auditor/scripts/citation_auditor.py references.bib

# 3. 提交前生成修正版 + JSON
python3 citation-truth-auditor/scripts/citation_auditor.py references.bib --fix --json
```

Windows PowerShell 解压：`Expand-Archive -Path Meteorain_C4_citation-truth-auditor.skill -DestinationPath citation-truth-auditor`

---

## 🔍 它解决什么问题

LLM 会**编造引用**，而且编得毫无破绽。生成一份 20 条的参考文献，肉眼看不出异常，
但其中可能有 3~5 条根本不存在。伤害通常在审稿人检索时才显现——那时已经太晚了。

本技能把"肉眼判断"换成"查询权威数据源"，逐条核实 Crossref / arXiv / OpenAlex：

```
输入 references.bib  →  逐条查权威库  →  VERIFIED / PARTIAL / FABRICATED / UNCHECKED
```

---

## ✅ 真实运行结果（非模拟）

样本 `demo/sample_refs.bib` 构造了 8 条引用（4 真 + 2 元数据有误 + 2 故意编造），
实际联网运行结果：

```
[FABRICATED] doe2021innovative   最佳匹配仅 0.52 < 阈值 0.82 → 编造
[FABRICATED] smith2023deep       最佳匹配仅 0.39 < 阈值 0.82 → 编造（泛义词堆砌）
[PARTIAL]    goodfellow2014…年份不一致（bib=2019 vs 真实=2014）
[PARTIAL]    vaswani2017         疑似版本漂移，标题/作者吻合
[VERIFIED]× 4 arXiv 命中，标题相似度 1.00，年份/作者一致

汇总：VERIFIED 4 (50%) ｜ PARTIAL 2 (25%) ｜ FABRICATED 2 (25%) ｜ UNCHECKED 0 (0%)
退出码：1（CI 门禁可用）
```

**零误报**（4 条真论文未被冤枉）、**零漏报**（2 条假引用全被抓出）。

### 🏆 真实语料交叉验证（更强的证据）

用本仓库 C2 交付里**已经过双API 人工核验**的 17 条 `references.bib` 跑本技能：

```
共审计 17 条引用，用时 7.4s
  [VERIFIED]     16 条  ( 94%)
  [PARTIAL]       0 条  (  0%)
  [FABRICATED]    0 条  (  0%)      ← 误报清零
  [UNCHECKED]     1 条  (  5%)      ← coqmanual（软件手册，三库均不收录）
退出码 0
```

**自建样本只能证明"能抓到假引用"；用别人已核验的真实文献库，
才能证明"不会冤枉好引用"。** 首次运行时它误伤了 3 条，我逐一查出根因并修复
（详见 AI 日志第 7 轮）。

---

## 📁 目录结构

```
C4_技能分享与传播_Meteorain/
├── README.md← 你在这里
├── Meteorain_C4_skill说明.md                ← 交付物 1
├── Meteorain_C4_citation-truth-auditor.skill   ← 交付物 2（可安装包）
├── demo/
│   ├── Meteorain_C4_demo_终端输出.png          ← 交付物 3（真实截图）
│   ├── sample_refs.bib                         ← 测试样本（8 条，含 2 条故意编造）
│   ├── out/                                    ← 脚本真实输出
│   │   ├── terminal_output.txt                     终端完整输出
│   │   ├── sample_refs.audit.md                   Markdown 审计报告
│   │   ├── sample_refs.audit.json                 机器可读结果
│   │   └── sample_refs.fixed.bib                  修正版文献库
│   ├── c2_validation/← 真实语料交叉验证
│   │   ├── C2_references.bib                      C2 已核验的 17 条文献
│   │   └── out/                                   验证输出（0 编造）
│   ├── pack_skill.py                             打包脚本
│   └── make_demo_png.py                          截图生成脚本
├── Meteorain_C4_教学说明.md                    ← 交付物 4
├── Meteorain_C4_AI日志.md                      ← 交付物 5
├── Meteorain_C4_AAR复盘.md                      ← rubric reflectionQuality
└── citation-truth-auditor/                ← 技能源码（可直接读/直接跑）
    ├── SKILL.md                            主指令：4步工作流、判定契约、边界情况
    ├── scripts/citation_auditor.py             零依赖审计器（37.4 KB）
    └── references/
        ├── hallucination_patterns.md          7 类幻觉指纹 + 3 个真实编造样例
        └── data_sources.md                    API 端点、限流、已知坑、扩展指南
```

---

## ✅ C4 四条件自检

| 条件 | 满足方式 | 验证 |
|---|---|---|
| **可复用** | 零依赖（纯标准库）、免 API key、跨平台 | 在 `/tmp` 干净目录解压重跑，输出一致 |
| **可执行** | 完整可运行脚本，非伪代码 | 实测 8 条，用时 7.6s |
| **可验证** | 四档判定 + 原因码 + 证据 URL + 退出码 | 4/2/2/0，退出码 1 |
| **IO 明确** | 输入=文献文件；输出=报告/修正 bib/JSON/退出码 | 见交付物 1 第三节 |

---

## 🚧 已知局限（诚实声明）

| 局限 | 应对 |
|---|---|
| **无法判断引用是否支撑你的论断** | VERIFIED 只代表"存在"；引用后仍需读原文 |
| 中文文献覆盖差 | Crossref/OpenAlex 收录有限，需人工核查 |
| 无 DOI 的会议论文可能漏检 | `UNCHECKED` 需人工确认 |
| OpenAlex 年份可能是重印版本年份 | 已用 bib 年份作先验排序，并标为"版本漂移" |

> ⚠ **`UNCHECKED` ≠ 通过。** "没被证明是假的"和"已证明是真的"是两回事。

---

## 🔄 迭代与反馈

**v1.0 已记录 6 轮迭代**（详见 [`Meteorain_C4_AI日志.md`](Meteorain_C4_AI日志.md)）：

| 轮次 | 内容 |
|---|---|
| 0 | 读题拆解、选题 |
| 1 | 环境探测（发现 arXiv 403 / SS 429） |
| 2 | 写脚本 |
| 3 | 实测 → **3 个真 bug** |
| 4 | 修bug（解析器 / 作者匹配 / 候选排序） |
| 5 | 查"版本漂移"真实现象 |
| 6 | 打包 + 干净目录复现验证 |

**欢迎反馈**：最难的是中文文献场景，如果你有相关场景的实测结果，请告诉我——
`references/hallucination_patterns.md` 和 `data_sources.md` 都是可扩展的。

---

> 📣 **C4 的本质：从"学习" → "能力产品化"。**
> 这个技能是我自己在C2 挑战里真实踩过的坑（AI 生成的参考文献查不到），
> 把它封装成技能，别人拿去就能直接用——这就是能力产品化。