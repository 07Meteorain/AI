# C5A · GitHub 入门与仓库理解

> 用一个**零依赖分析器** + 两份**真实仓库分析** + 一次**完整 Git 工作流**，回答三个问题：
> 陌生仓库怎么读？改动怎么提交？出问题怎么排？

| 项 | 内容 |
| --- | --- |
| 挑战编号 | C5A |
| 挑战 ID | `ch-20260717031511-x5c6t1` |
| 课程 | `aix-course-elite20` |
| 记录 ID | `recvpB3d1Pgwhn` |
| 交付形态 | 独立目录 `C5A_仓库分析/`，纯文本、零第三方依赖 |
| 运行环境 | Python 3.9+、git 2.x（Windows / macOS / Linux） |

---

## 30 秒验证

```bash
cd C5A_仓库分析/工具
python -m unittest discover -s tests -v        # 15 项，应全部 OK

# 分析当前仓库（或任意本地 Git 仓库），生成 Markdown + JSON
python repo_inspector.py ../.. --out-md /tmp/report.md --out-json /tmp/metrics.json
```

不想跑代码？直接看：

- [`仓库分析/01-httpie-cli-深度分析.md`](仓库分析/01-httpie-cli-深度分析.md) —— 一个 13 年开源项目的结构与协作；
- [`仓库分析/02-本仓库结构自检.md`](仓库分析/02-本仓库结构自检.md) —— 本仓库的五个具体问题与改进清单；
- [`Git实战/01-分支与PR实战.md`](Git实战/01-分支与PR实战.md) —— 本次真实的 branch / commit / PR / merge / tag 记录。

---

## 交付物

| 文件 | 内容 | 对应评分维度 |
| --- | --- | --- |
| [`README.md`](README.md) | 本文件：总览、快速开始、结构、边界 | 产物完整性 |
| [`提交说明.md`](提交说明.md) | 交付物对照、评分维度映射、红旗自查、验收步骤 | 产物完整性 |
| [`仓库分析/01-httpie-cli-深度分析.md`](仓库分析/01-httpie-cli-深度分析.md) | 选样、架构、测试、CI、协作、风险、可借鉴实践 | 基础掌握 / 技术实现 |
| [`仓库分析/02-本仓库结构自检.md`](仓库分析/02-本仓库结构自检.md) | 本仓库量化自检、五个发现、P0/P1/P2 改进 | 基础掌握 / 复盘 |
| [`仓库分析/03-读仓库方法论.md`](仓库分析/03-读仓库方法论.md) | 三层阅读法、六步清单、命令速查、30 分钟练习 | 基础掌握 |
| [`工具/repo_inspector.py`](工具/repo_inspector.py) | 零依赖仓库分析器（Markdown + JSON） | 技术实现 / 产物完整性 |
| [`工具/tests/test_repo_inspector.py`](工具/tests/test_repo_inspector.py) | 15 项 unittest：解析、评分边界、临时仓库、错误路径 | 技术实现 |
| [`Git实战/01-分支与PR实战.md`](Git实战/01-分支与PR实战.md) | 分支策略、分阶段提交、PR 描述、合并、tag | 基础掌握 |
| [`Git实战/02-排错手册.md`](Git实战/02-排错手册.md) | 14 个高频故障：症状/诊断/根因/修复/预防 | 基础掌握 |
| [`AI日志/AI使用日志.md`](AI日志/AI使用日志.md) | 8 轮记录、prompt 迭代、12 条返工、边界声明 | AI 使用质量 |
| [`复盘/AAR复盘.md`](复盘/AAR复盘.md) | 预期 vs 实际、五个为什么、改进方案、自评 | 复盘质量 |
| [`证据/`](证据/) | 量化报告、原始指标、测试输出、冲突演练、提交拓扑 | 可追溯性 |

---

## 分析结果摘要

### httpie/cli（他人仓库）

| 指标 | 数值 |
| --- | ---: |
| 提交 / 贡献者 | 1,797 / 174（署名去重） |
| 跟踪文件 / 文本行 | 265 / 28,276 |
| 测试文件 / 测试行 | 37 / 6,847（测试/源码 LOC = 0.56） |
| 版本标签 | 50（最新 3.2.4） |
| CI 工作流 | 15 条；测试矩阵最多 36 组合 |
| 健康度 | 77/100 |
| 最近提交 | 2024-12-17（分析日距今 692 天） |

**三个判断**：

1. 架构是清晰的四层：`cli → core/client → output → plugins`，插件通过 entry point 扩展；
2. 工程基建成熟：跨 OS 测试矩阵、覆盖率、基准、五渠道发布流水线；
3. 最大风险是可持续性：单人（含署名变体）占 69.3% 提交，10 个远程分支中 9 个过期，项目处于低活跃维护期。

### 本仓库（07Meteorain/AI）

| 指标 | 数值 |
| --- | ---: |
| 提交 / 文件 / 文本行 | 99 / 1,246 / 204,846 |
| 测试/源码 LOC | 0.15 |
| 健康度 | 29/100 |
| 最大文件 | `tectonic.exe` 47.8 MiB |
| 版本标签 | 1（`c5-v1.0.0`） |

**五个发现**：二进制资产偏重（工作区 112.1 MB、`.git` 65 MiB）；根级治理文件缺失；提交信息偏长（34.3% 超 72 字符）；内容归档占比高（`C1_交付` 占 67.4% 文件）；没有分支/PR 痕迹。

> 健康度 29 要用对语境：评分面向产品仓库，对「作业归档」会低估（根目录没有 `tests/`，但子目录有 7 套测试）。详见 [`仓库分析/02`](仓库分析/02-本仓库结构自检.md) 末尾。

---

## 目录结构

```
C5A_仓库分析/
├── README.md                     # 本文件
├── 提交说明.md                    # 评分对照 + 红旗自查 + 验收
├── 仓库分析/
│   ├── 01-httpie-cli-深度分析.md
│   ├── 02-本仓库结构自检.md
│   └── 03-读仓库方法论.md
├── 工具/
│   ├── repo_inspector.py         # 零依赖分析器
│   └── tests/test_repo_inspector.py
├── Git实战/
│   ├── 01-分支与PR实战.md
│   └── 02-排错手册.md
├── AI日志/
│   └── AI使用日志.md
├── 复盘/
│   └── AAR复盘.md
└── 证据/
    ├── httpie-report.md / httpie-metrics.json
    ├── ai-repo-report.md / ai-repo-metrics.json
    ├── test-output.txt
    ├── conflict-drill.txt
    └── git-log-graph.txt
```

---

## 快速开始：分析任意仓库

```bash
cd 工具

# 1) 最简：打印 Markdown 到终端
python repo_inspector.py /path/to/repo

# 2) 同时写 Markdown 与 JSON
python repo_inspector.py /path/to/repo \
  --out-md report.md \
  --out-json metrics.json

# 3) 固定基准时间，保证历史报告可复现
python repo_inspector.py /path/to/repo \
  --now 2026-11-10T23:30:19+08:00 \
  --out-md report.md

# 4) 调整 Top N 与「过期分支」阈值
python repo_inspector.py /path/to/repo --top 20 --stale-days 90
```

**输出包含**：概览、文件/语言构成、顶层目录、最大文件、提交与作者、年份节奏、Conventional Commits 占比、治理清单、churn 热点、健康度评分与发现。

**退出码**：`0` 成功；`2` 不是 Git 仓库或参数错误。

### 复现本交付的两份报告

```bash
# 先克隆两个仓库（固定快照）
git clone https://github.com/httpie/cli.git /tmp/httpie
git -C /tmp/httpie checkout 5b604c37c6c67e18e7c3e9aee6c88a8c22b98345

git clone https://github.com/07Meteorain/AI.git /tmp/AI
git -C /tmp/AI checkout 451f4b6299c81c6cde738782fd6b041592ea6ead

cd 工具
python repo_inspector.py /tmp/httpie --now 2026-11-10T23:30:19+08:00 \
  --out-md ../证据/httpie-report.md --out-json ../证据/httpie-metrics.json
python repo_inspector.py /tmp/AI --now 2026-11-10T23:30:19+08:00 \
  --out-md ../证据/ai-repo-report.md --out-json ../证据/ai-repo-metrics.json
```

> 报告里的每个数字都可用 `git rev-list` / `git tag` / `git shortlog` 等原生命令复核；报告末尾附「指标口径」。

---

## 设计取舍

| 决策 | 选择 | 理由 | 代价 |
| --- | --- | --- | --- |
| 依赖 | 只用标准库 + git | 评审 `git clone` 后即可运行，不装任何包 | 不能做复杂可视化 |
| 输出 | Markdown + JSON 双份 | 人读 / 机读两用，便于二次分析 | 需要维护两套渲染 |
| 时间基准 | `--now` 可注入 | 历史报告可复现，不会「明天跑数字就变」 | 多一个参数 |
| 分析对象 | httpie/cli + 本仓库 | 一个「他人成熟项目」，一个「自己的归档仓库」，形成对照 | 两个仓库都要读 |
| 评分 | 启发式 0–100 | 快速暴露治理缺口，便于横向比较 | 对归档/monorepo 有偏差，已在文档标注 |
| 仓库改造 | 只新增 `C5A_仓库分析/`、根 README 索引、CI | 不破坏现有交付，不重写历史 | 未解决既有二进制资产问题（只给建议） |

---

## 已知限制

1. **作者去重按 name 字符串**：同一人的不同署名会重复计数（httpie 的 Jakub 有三种写法），真实人数少于 174。
2. **LOC 是行数，不是覆盖率**：测试写得多不等于测试有效。
3. **churn 不追踪 rename**：`git mv` 后的旧路径可能单独出现。
4. **健康度是启发式**：面向产品仓库；归档仓库、monorepo 需要人工修正解读。
5. **二进制只统计大小**：不做内容分析；大文件读取会占用内存。
6. **分析是快照**：httpie 固定 `5b604c3`，本仓库固定 `451f4b6`（不含本目录），后续变化不在覆盖范围。

---

## 评分维度自查

| 维度 | 分值 | 证据 | 自评 |
| --- | ---: | --- | ---: |
| 基础掌握 | 25 | Git 实战 + 14 个排错场景 + 冲突演练 + PR 流程 | 22 |
| 产物完整性 | 20 | 三件套 + AAR + 可运行工具 + 15 测试 + 复现命令 | 19 |
| 技术实现 | 15 | 零依赖、单文件、类型注解、清晰口径、固定快照 | 14 |
| AI 使用质量 | 20 | 8 轮日志、12 条返工、prompt 迭代、工作流门禁 | 18 |
| 复盘质量 | 20 | AAR 四问、五个为什么、8 条改进、重做方案 | 15 |
| **合计** | **100** | — | **88** |

> 自评不是要分，是检查「每个维度是否有证据」。最终以评审为准；扣分点写在 [`复盘/AAR复盘.md`](复盘/AAR复盘.md) 第 7 节。

---

## 红旗项自查

| 红旗 | 是否触发 | 反证 |
| --- | --- | --- |
| 核心交付物缺失 | 否 | 仓库分析 3 篇、README、AI 日志、AAR、工具与测试均在 |
| 无 AI 使用记录/AAR | 否 | 8 轮 AI 日志 + AAR 四问 |
| 一句话指令直接提交、无迭代 | 否 | 12 条返工记录 + 指标从 v0 到 v1 的修正 + 真实测试失败 |

---

## 版权与引用

- 课程挑战说明与 `challenge.json` 版权归课程平台/原作者；本目录仅引用其要求，不复制课程正文。
- `httpie/cli` 的分析基于其公开仓库（BSD-3-Clause），文中引用少量文件名/提交主题，用于评论与分析。
- 本目录代码（`工具/`）可自由用于学习；文档中的观点为分析结论，欢迎指出错误。
