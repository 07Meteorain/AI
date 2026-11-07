# C3C · 联合成果（索引入口）

> 挑战：C3C 双人协作与技能迁移 ｜ 挑战 ID `ch-20260717031415-0vi5d1`
> 课程：aix-course-elite20 ｜ 学生：2025105220114
> 本文作用：挑战要求中「联合成果」一项的具名入口。成果实体在 `duolog/` 与 `tests/`，本文只做定位与复算指引，**不含任何新增数据**。

---

## 1. 联合成果是什么

本次协作产出的不是一个文档，而是一个**可独立运行、零第三方依赖**的命令行工具 `duolog`：

- 读两份协作者原始日志（`logs/Aster.md`、`logs/Bramble.md`）；
- 按固定规则 R0→R1→R2→R4→R3 合并成一份带裁决理由的协作记录；
- 从日志中抽取**技能迁移的边**（谁教会了谁哪一段）。

也就是说：**工具的分析对象，就是造它的这场协作本身**。协作记录（另一项交付物）里的人写叙述版，可由本成果复算成机器版，两者可交叉验证。

## 2. 成果清单

| 组成 | 位置 | 规模 |
| --- | --- | --- |
| 工具源码 | `duolog/`（`model.py`、`merge.py`、`analyze.py`、`render.py`、`cli.py`、`explain.py`、`__init__.py`、`__main__.py`） | 8 个模块，1,977 行 |
| 测试 | `tests/`（`test_duolog.py`、`test_merge_round2.py`、`test_explain.py`、`test_analyze_strip.py`） | 108 项，1,342 行，全部通过 |
| 产物：合并记录（机器版协作记录） | `logs/合并记录.md` | 21 条条目（原始 26 条） |
| 产物：协作报告（冲突与迁移） | `logs/协作报告.md` | 冲突 4 条、技能迁移 2 条边 / 5 条证据 |
| 产物：合并结果 JSON | `demo/merged.json` | 含 `stats` 段，可直接核对条目数与冲突数 |
| 接口契约 | `任务契约.md` | v1.5，含 5 次变更的触发原因与影响面 |
| 使用与设计说明 | `README.md` | 目录结构、五条裁决规则、退出码契约 |
| 测试夹具 | `examples/sample_a.md`、`examples/sample_b.md` | 覆盖 R0/R1/R2/R3 |

## 3. 如何独立复算（不装任何依赖）

```bash
cd C3C_交付

# ① 自检：内置样例跑通 解析→合并→裁决→渲染，不读外部文件
python -m duolog selfcheck
# 期望：selfcheck: ok 38e8e32a4d654a92dfda03a26863234ead153f19ca4c542d171db2a8df48bd2

# ② 全量测试
python -m unittest discover -s tests
# 期望：Ran 108 tests ... OK

# ③ 用工具复算这次的协作记录
python -m duolog merge --a logs/Aster.md --b logs/Bramble.md \
       --author-a Aster --author-b Bramble \
       --out logs/合并记录.md --report logs/协作报告.md
# 期望：指纹 3a40d780a8fca3c60c99798eb2bb7686793e0481ea94da1d8f135c2d7882c6df
#       条目 21 条（原始 26 条，作者 2 人），冲突 4 条，技能迁移 2 条边

# ④ 单条争议事件溯源
python -m duolog explain --a logs/Aster.md --b logs/Bramble.md \
       --author-a Aster --author-b Bramble --eid E-021
# 期望：status=needs_review，两种说法并排保留
```

真实终端输出已留档在 `demo/终端_selfcheck.txt`、`demo/终端_tests.txt`、`demo/终端_merge.txt`、`demo/终端_explain_E-021.txt`。

## 4. 双人协作是怎么体现为成果的

| 环节 | 证据位置 |
| --- | --- |
| 两个独立上下文的协作者（Aster / Bramble）并发开发，只靠冻结的接口契约对齐 | `任务契约.md`（v1.0→v1.5，5 次变更）、`notes/` 下两份设计笔记 |
| 双向技能迁移：Aster→Bramble（SEL-1）、Bramble→Aster（SEL-2） | `notes/Aster_迁移笔记_SEL2.md`、`notes/Bramble_迁移笔记_SEL1.md`；`logs/协作报告.md` 技能迁移表 |
| 第二轮「换房间」：各自进入对方代码库实现迁移功能，由原作者评审 | `notes/*_评审*_第二轮.md`（4 份互检意见，共 13 条） + 浏览器外的人工裁定记录见协作记录 §4–§5 |
| 集成侧发现的问题（R4 在 R2 之后轮不到、空行敏感） | `README.md`「五条裁决规则」、`任务契约.md` v1.5、AAR §3 |

## 5. 已知局限

8 条局限与对应的裁定/修复代价，见 `07Meteorain_C3C_提交说明.md` §6 与 `07Meteorain_C3C_AAR.md` §6。
其中最需要评审注意的一条：**两位协作者都是 AI**，缺人类学习曲线对照——本条已在 AAR 中列为「最大不足」，未作回避。
