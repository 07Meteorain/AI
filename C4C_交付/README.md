# C4C 交付

C4C 挑战的交付物。

## 交付物一览

| 交付物 | 目录 / 文件 | 内容 |
|--------|------------|------|
| **作业自动求解与排版** | [`homework-solver/`](./homework-solver/)<br>（[技能包 .skill](./Meteorain_C4C_homework-solver.skill)） | 作业文件 → 自动求解 → 验证 → 排版 → PDF |
| 引用真伪审计器 | [`citation-truth-auditor/`](./citation-truth-auditor/)<br>（[技能包 .skill](./Meteorain_C4_citation-truth-auditor.skill)） | 学术写作中的引用核查 |

---

## 作业自动求解与排版

**一条命令把作业转成可提交的 PDF 答案：**

```
md / pdf / docx / tex / 图片
  → 摄入 → 解析 → 求解（SymPy + 国产 LLM）→ 四层验证 → LaTeX → PDF
```

### 成果

| 测试集 | 本项目 | starter kit 基线 |
|--------|--------|-----------------|
| Berkeley Math 1A WS3 | **8/8** = 100% | 8/8 |
| Berkeley Math 1A WS4 | **10/10** = 100% | 9/10 |
| **核心域合计** | **18/18 = 100%** | 17/18 = 94.4% ✅ |
| 线性代数（新增） | **12/12** = 100% | 域外 |
| 物理 + ODE（新增） | **14/14** = 100% | 域外 |
| **总计** | **44/44 = 100%** | — |

**答案自带验证标签** —— PDF 里标注`✓ 已验证` / `⚠ 验证存疑`。

### 快速开始

```bash
cd homework-solver
pip install -r requirements.txt
python scripts/pipeline.py examples/homework_linear_algebra.md output/ --compile
```

无需安装 LaTeX（自带 `tools/tectonic.exe`），无需 API Key（自动降级到 SymPy）。

### 文档

| 文档 | 内容 |
|------|------|
| [方案设计](./Meteorain_C4C_方案设计.md) | 求解流程、排版规则、验收方式 |
| [验证报告](./homework-solver/Meteorain_C4C_验证报告.md) | 逐题核对 + 基线对比 |
| [教学说明](./homework-solver/Meteorain_C4C_教学说明.md) | 安装、使用、扩展 |
| [拿来说明](./homework-solver/Meteorain_C4C_拿来说明.md) | 拿了什么、库选型 |
| [AI 日志](./Meteorain_C4C_AI日志.md) | 开发过程与踩坑记录 |
| [AAR 复盘](./homework-solver/Meteorain_C4C_AAR复盘.md) | 做成了什么、没做成什么 |
| [SKILL.md](./homework-solver/SKILL.md) | Agent 调用说明 |

### 真实产物

[`homework-solver/output/`](./homework-solver/output/)：
- `linear_algebra/homework.pdf` —— 12 题线代作业答案（7 页）
- `physics_ode/homework.pdf` —— 14 题物理 + ODE 作业答案（8 页）
- `benchmark.json` —— 基准测试报告

---

## 引用真伪审计器

针对学术写作场景，检查参考文献真伪（编造的 DOI、幽灵期刊等）。

**一句话**：输入 `references.bib`，输出每条引用的判定
（VERIFIED / PARTIAL / FABRICATED / UNCHECKED）+ 审计报告 + 修正版文献库。
**零依赖，不用装任何东西，不用 API key。**

```bash
# 1. 解压技能包
unzip Meteorain_C4_citation-truth-auditor.skill -d citation-truth-auditor/

# 2. 审计你的参考文献
python3 citation-truth-auditor/scripts/citation_auditor.py references.bib
```

- 技能说明：[`Meteorain_C4_skill说明.md`](./Meteorain_C4_skill说明.md)
- 演示产物：[`demo/Meteorain_C4_demo_终端输出.png`](./demo/Meteorain_C4_demo_终端输出.png)
- 文档：[`Meteorain_C4_教学说明.md`](./Meteorain_C4_教学说明.md)｜[`Meteorain_C4_AAR复盘.md`](./Meteorain_C4_AAR复盘.md)｜[`Meteorain_C4_AI日志.md`](./Meteorain_C4_AI日志.md)

---

## 快速索引

| 我想找… | 去这里 |
|---------|--------|
| 作业求解技术方案 | [方案设计](./Meteorain_C4C_方案设计.md) |
| 怎么装怎么用 | [教学说明](./homework-solver/Meteorain_C4C_教学说明.md) |
| 求解率有没有水分 | [验证报告](./homework-solver/Meteorain_C4C_验证报告.md) |
| AI 做了什么、踩了什么坑 | [AI 日志](./Meteorain_C4C_AI日志.md) |
| 真实 PDF 长什么样 | [output](./homework-solver/output/) |
| Agent 怎么调用技能 | [SKILL.md](./homework-solver/SKILL.md) |