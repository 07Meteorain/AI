# C3C · 提交说明

> 挑战：C3C 双人协作与技能迁移 ｜ 挑战 ID `ch-20260717031415-0vi5d1`
> 课程：aix-course-elite20 ｜ 学生：2025105220114 ｜ 提交日期：2026-11-07

---

## 1. 交付物对照表

挑战要求的四份必需交付物，以及支撑它们的辅证：

| 要求 | 交付物 | 位置 |
| --- | --- | --- |
| **协作记录** | 人写的叙述版：分工、时间线、5 次契约变更、13 条互检、双向迁移 | [`07Meteorain_C3C_协作记录.md`](07Meteorain_C3C_协作记录.md) |
| | 机器复算版：从两份原始日志合并出来的条目与裁决 | [`logs/合并记录.md`](logs/合并记录.md)、[`logs/协作报告.md`](logs/协作报告.md) |
| **联合成果** | 零依赖工具 `duolog`（8 模块 1,977 行）+ 108 项测试 | `duolog/`、`tests/` |
| | 使用说明与设计说明 | [`README.md`](README.md)、[`任务契约.md`](任务契约.md) |
| **AI日志** | 工作流设计、3 次 prompt 改法、8 条失败清单、可追溯性索引 | [`07Meteorain_C3C_AI日志.md`](07Meteorain_C3C_AI日志.md) |
| **AAR** | 四问复盘、6 条失败根因、3 个反直觉发现、3 项可执行改进 | [`07Meteorain_C3C_AAR.md`](07Meteorain_C3C_AAR.md) |
| 辅证 | 两位协作者的设计笔记、迁移笔记、4 份互检意见 | `notes/`（8 份） |
| 辅证 | 真实终端输出、合并 JSON | `demo/`（5 份） |
| 辅证 | 测试夹具（覆盖 R0/R1/R2/R3） | `examples/` |

---

## 2. 一分钟验收

```bash
cd C3C_交付

# ① 自检：不读任何外部文件，验证 解析→合并→裁决→渲染 全链路
python -m duolog selfcheck
# 期望：selfcheck: ok 38e8e32a4d6548a92dfda03a26863234ead153f19ca4c542d171db2a8df48bd2

# ② 跑测试
python -m unittest discover -s tests
# 期望：Ran 108 tests ... OK

# ③ 用工具复算这次的协作记录
python -m duolog merge --a logs/Aster.md --b logs/Bramble.md \
       --author-a Aster --author-b Bramble --out /tmp/合并记录.md --report /tmp/协作报告.md
# 期望：指纹 3a40d780a8fca3c60c99798eb2bb7686793e0481ea94da1d8f135c2d7882c6df
#       条目 21 条（作者 2 人，原始条目 26 条），冲突 4 条，技能迁移 2 条边

# ④ 看一条争议事件凭什么这么裁
python -m duolog explain --a logs/Aster.md --b logs/Bramble.md \
       --author-a Aster --author-b Bramble --eid E-021
# 期望：status=needs_review，两种说法并排保留
```

**不必先 `pip install` 任何东西**，只用标准库，Python 3.9+ 即可。

---

## 3. 建议阅读顺序（15 分钟）

| 顺序 | 读什么 | 为什么在这个位置 |
| --- | --- | --- |
| 1 | [`README.md`](README.md) 前 40 行 | 30 秒知道这是什么、为什么这样设计 |
| 2 | [`07Meteorain_C3C_协作记录.md`](07Meteorain_C3C_协作记录.md) §0–§1 | 先搞清"谁跟谁协作"，否则后面的记录读不懂 |
| 3 | [`logs/合并记录.md`](logs/合并记录.md) | 看机器版协作记录，注意 E-019~E-022 四条冲突的处理 |
| 4 | [`07Meteorain_C3C_协作记录.md`](07Meteorain_C3C_协作记录.md) §3–§5 | 契约变更与互检、技能迁移证据 |
| 5 | [`07Meteorain_C3C_AAR.md`](07Meteorain_C3C_AAR.md) §3 | 三个反直觉发现，这是整份材料里最"人"的部分 |
| 6 | [`07Meteorain_C3C_AI日志.md`](07Meteorain_C3C_AI日志.md) §3 | 8 条失败，含沙箱崩溃、死循环、编码坑 |

想直接看代码 → `duolog/merge.py`（规则引擎）、`duolog/explain.py`（迁移产物）。
想直接看评审 → `notes/Bramble_评审Aster_第二轮.md`（6 条，质量最高的一份）。

---

## 4. 关于"双人"的说明（请评审注意）

本次的两位协作者是**两个独立上下文的 AI agent**（Aster / Bramble），学生担任主持人：
定契约、拆任务、集成、跑测试、裁定分歧。

- **不是"一个人 + 一个助手"**：两人并发工作、互相看不见对方的代码，只能通过冻结的接口契约对齐；
- **不是"两个人各做一半"**：第二轮两人**换房间**，各自进入对方的代码库实现迁移功能，
  并由**原作者**评审自己文件被改的部分（详见协作记录 §4–§5）；
- 选择这个设定的理由与代价，写在 [`07Meteorain_C3C_协作记录.md`](07Meteorain_C3C_协作记录.md) §0，
  以及 [`07Meteorain_C3C_AAR.md`](07Meteorain_C3C_AAR.md) §6 的"最大不足"一节——**没有隐瞒**。

所有 AI 协作过程都以文件形式留痕：契约 5 次变更、8 份笔记、13 条互检意见、8 条失败记录。

---

## 5. 实测数据（可直接核对）

| 指标 | 数值 | 核对方式 |
| --- | --- | --- |
| 测试 | 108 项全通过 | `python -m unittest discover -s tests` |
| 代码 | 1,977 行 / 8 模块 | `duolog/*.py` 行数 |
| 测试代码 | 1,342 行 | `tests/*.py` 行数 |
| 合并条目 | 21（原始 26） | `demo/merged.json` 的 `stats` |
| 冲突 | 4 条（R1×1、R2×1、R4×1、R3×1） | `logs/协作报告.md` 冲突清单 |
| 技能迁移 | 2 条边、5 条证据 | `logs/协作报告.md` 技能迁移表 |
| 合并指纹 | `3a40d78...c6df`（全程唯一） | 每次 merge 输出一致 |
| 第三方依赖 | 0 | 无 requirements.txt |

---

## 6. 已知局限（如实列出）

1. **R4 只是补位规则**：时钟不等时 R2 恒先命中，R4 轮不到。改顺序代价更大，故保留并在契约 v1.5 中写明。
2. **R4 的空行敏感**：多一个段落空行就能赢 R4，纯格式差异会改变类型归属。需成对修 R0/R4，本轮未修。
3. **R4 对"自相矛盾超集"无防护**：A 写"X"、B 写"X 且非 X"，B 会赢。需引入矛盾检测。
4. **explain 固定 72 列**：为"输出可复现"牺牲终端自适应。
5. **`winner=None` 有三义**：`single`/`confirmed`/`needs_review` 都取 None，判据是 `status`。
6. **逻辑时钟跨人不可比**：`clock` 只在本作者内单调，R2 因此只是弱证据。
7. **迁移证据有自我报告偏差**：协作者自己给条目打 `技能:` 标签，缺独立测量。
8. **两位协作者都是 AI**：缺人类学习曲线对照，见 AAR §6。

以上 8 条没有一条是靠"下个版本再说"敷衍掉的：其中 5 条有书面裁定，3 条有明确的修复方案与代价评估。
