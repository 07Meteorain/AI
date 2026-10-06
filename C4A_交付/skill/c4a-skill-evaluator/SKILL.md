---
name: c4a-skill-evaluator
description: >
  Automatically evaluate Elite20 C4 skill submissions in a local folder (typically
  downloaded from a WeChat group): identify each submission's author, check the 5 required
  deliverables, grade skill quality against the C4 four-criteria rubric (Reusable 可复用 /
  Executable 可执行 / Verifiable 可验证 / Clear I/O IO明确), and generate a Markdown report
  + JSON data + Excel detail sheet with rankings, evidence-traceable findings and per-author
  improvement suggestions. Use whenever the user says "evaluate C4 submissions",
  "review skill submissions", "check C4 completeness", "grade the class",
  "评审C4提交", "检查技能提交", "技能评审", "C4评审报告", "给提交打分", or hands you a folder
  of skill submissions and asks to review/grade/score them. Also trigger when the user
  mentions C4/C4A 挑战 together with 评审/阅卷/打分/检查/查漏.
---

# C4A 技能提交自动评审器

## Purpose（这个技能解决什么问题）

给定一个**本地文件夹路径**（内含全班每个人的 C4 技能提交），自动产出：

1. **按作者分组的提交清单**（谁交了什么）
2. **五必须文件完整性检查**（✅ 齐全 / ⚠️ 部分缺失 / ❌ 严重缺失 + 缺什么）
3. **C4 四条件质量评审**（可复用 / 可执行 / 可验证 / IO明确 → ✅⚠️❌ + 评审依据）
4. **班级评审报告**（Markdown + JSON + Excel，含排名与个性化改进建议）

**一句话说明：输入一个装着 C4 提交的文件夹路径，输出一份带排名和证据的可追溯评审报告。**

它替代的是"老师逐个打开 30 份文件、对着 rubric 打勾"这件事。

## 为什么不是纯规则、也不是纯 LLM（架构选型）

| 方案 | 优点 | 缺点 | 是否采用 |
|---|---|---|---|
| 纯规则（关键词/正则） | 确定性强、快、零成本、可单测 | 覆盖率低、易误判 | ✅ **作为默认主路径** |
| 纯 LLM | 理解力强、灵活 | 不确定、慢、贵、不可复现 | ❌ 不作默认 |
| 规则 + LLM 混合 | 规则快筛 + LLM 深审 | 架构复杂 | ⚠️ 部分采用（见下） |

**选择理由**：C4A 要评的是**客观可判定的信号**——"有没有安装说明""有没有硬编码路径"
"代码能不能解析"。这些信号用规则判定能做到**确定性、可复现、可单元测试、可审计**，
而 LLM 的不确定性在这里是纯成本。真正的风险不是"覆盖不全"，而是"结论不可追溯"。

**所以本技能的核心设计目标不是"更聪明的判断"，而是"更可信的判断"**：

- **证据化**：每个 ✅/⚠️/❌ 都附带 `文件:行号 + 原文片段`，评审者可以逐条复核
- **置信度分级**：结构性硬校验（AST/YAML/文件存在性）= `high`；
  单关键词命中 = `low`，并强制标记"需人工复核"，同时综合分打 0.9 折
- **否决机制（veto）**：硬编码绝对路径、凭据泄露这类致命项，命中即否决该检查项，
  而不是"和其他正面信号加权平均掉"——这是控制误判率的核心手段
- **矛盾检测**：完整性 80%+ 但质量 <25%（或反之）时主动报警，提示可能是空壳提交

**LLM 的引入位置**（有意保留但不在默认路径）：规则层给不出判断时
（置信度 `low`、或作者 `Unknown`），此时用 LLM 做一次定向深审，
产出补充说明而非替代规则结论。这样 LLM 的成本只花在真正困难的少数case 上。

## Prerequisites

### Runtime
- Python 3.9+
- `PyYAML`（必需）：`pip install pyyaml`
- `openpyxl`（可选，仅生成 Excel 详表需要）：`pip install openpyxl`
- `pypdf` / `python-docx` / `python-pptx`（可选，用于解析 PDF/Word/PPT 正文）

> 除 PyYAML 外全部使用标准库。**没有 openpyxl 也能跑完**，只是跳过 Excel 输出。

### Input
- 一个本地文件夹路径（含 C4 提交文件，命名建议 `姓名拼音_C4_内容描述.扩展名`）

## Workflow

### Step 0 — 拿到文件夹路径

向用户确认文件夹路径；若未提供则询问。支持绝对路径与 `~` 相对路径。
文件夹怎么来的（手动下载 / WeChat 同步 / 导出工具）**不重要** —— 本技能只接受本地路径。

### Step 1 — 运行评审器

```bash
python scripts/c4a_evaluator.py <FOLDER_PATH> --outdir <OUTPUT_DIR>
```

常用参数：

| 参数 | 作用 |
|---|---|
| `--outdir DIR` | 报告输出目录（默认 `./reports`） |
| `--md NAME` | Markdown 报告文件名 |
| `--json NAME` | JSON 数据文件名（供二次分析） |
| `--xlsx NAME` | Excel 详表文件名 |
| `--strict` | 严格模式：额外解析 pdf/docx/pptx 正文（更准更慢） |
| `--verbose` | 打印扫描诊断信息 |

首次在正式数据上跑，建议加 `--strict`。

### Step 2 — 读结果并解读

报告已按"总览 → 作者详情 → 排名 → 共性问题"组织。**你要做的不是复述表格，而是**：

1. 指出**班级最普遍的问题**（通常是某个必须文件缺失率最高，或某个条件达成度最低）
2. 对**置信度为 `low` 或被标"需人工复核"的作者**，说明这是机器不确定的地方，
   建议你亲自看一眼——不要把不确定的结论当成定论
3. 强调**排名只是参考**：C4 的评分核心是"被使用次数"，不是机器打分

### Step 3 — （可选）二次分析

`evaluation.json` 包含全部原始判定，可用于自定义统计：

```bash
python -c "
import json;d=json.load(open('reports/evaluation.json',encoding='utf-8'))
for a,v in sorted(d['authors'].items(),key=lambda kv:-kv[1]['composite_score']):
    print(a, v['completeness_score'], v['quality_score'], v['confidence'])
"
```

## 评审标准设计（references/c4_rubric.yaml）

标准全部外置到 YAML，**改标准不用改代码**。

### 完整性（五个必须文件）

| 必须文件 | 最强证据（high） | 兜底证据（medium） |
|---|---|---|
| Skill 说明文档 | 文件名含 `skill说明`/`skill_doc`/`技能说明` | 正文命中 ≥3 个结构信号（使用场景/输入/输出…） |
| 可执行内容 | 文件名含 `技能`/`skill`；`.py` 能被 `ast.parse` 解析 | 正文命中 ≥2 个代码信号 |
| Demo | **真实媒体文件存在**（.mp4/.png/.gif…） | 正文含"演示视频/运行截图/输出示例" |
| 教学说明 | 文件名含 `教学`/`tutorial`/`上手指南` | 正文命中 ≥3 个教学信号 |
| AI 日志 | 文件名含 `AI日志`/`AI协作日志` | 正文命中 ≥3 个 AI 信号 |

> 判定优先级刻意设计为 **真实文件 > 文件名 > 正文关键词**。
> 因为人主动命名的文件名可信度高于程序猜测的正文命中。

### 质量（四条件 × 5 个可检测项）

| 条件 | check_items |
|---|---|
| **可复用** | R1 有安装说明｜R2 **无硬编码绝对路径**(veto, w=1.5)｜R3 声明环境依赖｜R4 用相对路径/环境变量｜R5 **无凭据泄露**(veto, w=1.5) |
| **可执行** | E1 含可运行代码块｜E2 含工作流步骤定义｜E3 有 CLI 入口｜E4 **代码/YAML 可解析**(结构硬校验, w=1.5)｜E5 声明依赖安装 |
| **可验证** | V1 有测试用例/示例｜V2 定义预期输出(w=1.2)｜V3 **有真实运行佐证**(结构事实)｜V4 说明边界/异常处理 |
| **IO 明确** | I1 **「输入X，输出Y」同一句式**(w=1.5)｜I2 输入有类型说明｜I3 输出有类型说明｜I4 one-liner 摘要(w=1.2) |

### 打分公式

```
每维度 ratio = Σ(满足项 weight) / Σ(全部项 weight)     # 权重不等，重要项更能决定结论
评级：ratio ≥ 0.70 → ✅ ｜ 0.35 ~ 0.70 → ⚠️ ｜ < 0.35 → ❌
质量总分 = 四维度 ratio 的平均
综合分 = 完整性 × 0.40 + 质量 × 0.60        # 沿用 starter 的 composite 公式
置信度 low → 综合分 × 0.90 + 标记"需人工复核"
```

## Output

| 文件 | 用途 |
|---|---|
| `*_评审报告.md` | 人读：班级总览 / 作者详情（含逐项证据）/ 排名 / 共性问题 |
| `evaluation.json` | 机读：全部原始判定，供二次分析 |
| `*_评审详表.xlsx` | 5 个 sheet：排名总表 / 完整性矩阵 / **逐项评审明细** / 文件清单 / 改进建议 |

Excel 的"逐项评审明细"是最有价值的一张——它把每条判定摊平成可筛选的表格，
老师可以直接按"哪些人 R2 没过"筛选，一键定位硬编码路径问题。

## Edge Cases

| 情况 | 处理 |
|---|---|
| 空文件夹 | 报告"未识别到任何 C4 提交"，明确打印扫描路径与命名规则 |
| 文件名不规范 | 四级回退：命名规范 → 父目录 → PDF/DOCX 元数据 → 文档头"作者："；仍失败标 `Unknown` 且**不参与排名** |
| 超大文件 > 50MB | 跳过正文解析，仅按文件名/扩展名判定 |
| 二进制文件 | 仅文件名匹配，不做内容分析 |
| 非 C4 文件混入 | 过滤后在报告末尾"非 C4 文件"折叠区列出 |
| 同一作者多版本 | 全部计入该作者 bundle，报告中以相对路径区分；`_v2`/`_v3` 不特殊处理 |
| 中文文件名编码 | 全程 UTF-8 + `errors="replace"` 兜底 |
| 损坏的 .skill 包 | `tarfile.is_tarfile` 判false，降级为按普通归档处理，不中断 |
| 作者 `Unknown` | 参与报告展示但不参与排名，并标记需人工确认 |
| 缺 openpyxl | 跳过 Excel，Markdown + JSON 照常输出 |
| **完整性高但质量极低** | 矛盾检测触发 → 报警"可能是占位/空壳提交" |
| **质量高但完整性低** | 矛盾检测触发 → 报警"可能漏交了某些必须文件" |

## What Was Taken From wechat-doc-mapper（拿来主义）

本技能直接派生自 `wechat-doc-mapper.skill`，保留其
`inventory → 作者识别链 → 信号映射 → 缺口分析 → 双格式输出` 主干，
在三个位置做了升级（详见 `Meteorain_C4A_拿来说明.md`）：

| 原技能 | 本技能 |
|---|---|
| 映射"文件 → 哪个挑战" | **评审"提交 → 好不好"**（从分类器变成阅卷器） |
| 缺口分析只比"文件在不在" | 缺口 + **质量四维打分 + 证据行号 + 置信度** |
| 关键词打分（keyword × 2 / ext × 3 / path × 4） | **加权 check_item + veto 否决 + 结构化硬校验** |

## Examples

```bash
# 典型用法
python scripts/c4a_evaluator.py "/path/to/WeChat Files/C4群" --outdir ./reports

# 正式评审（解析 pdf/docx 正文）
python scripts/c4a_evaluator.py "/path/to/C4" --outdir ./reports --strict

# 自测（验证安装是否正常）
python scripts/c4a_evaluator.py tests/golden_dataset --outdir /tmp/selftest --verbose
```