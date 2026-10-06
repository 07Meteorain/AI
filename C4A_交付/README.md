# C4A 技能提交自动评审器

> 挑战 ID：`ch-20260717031432-5jvqje`
> 一句话：**输入一个装着全班 C4 提交的文件夹，输出一份带排名和证据的可追溯评审报告。**

从 `wechat-doc-mapper.skill`（C4 示例技能）升级而来——
原技能是「收发室」（分信），本技能是「阅卷系统」（评卷）。

---

## 一、30 秒上手

```bash
pip install pyyaml                      # 唯一必需依赖

python skill/c4a-skill-evaluator/scripts/c4a_evaluator.py \
       "<你的 C4 提交文件夹>" --outdir ./reports
```

产出：`reports/` 下三个文件

| 文件 | 用途 |
|---|---|
| `*_评审报告.md` | 人读：班级总览 / 作者详情（含逐行证据）/ 排名 / 共性问题 |
| `evaluation.json` | 机读：全部原始判定，供二次分析 |
| `*_评审详表.xlsx` | 5 个 sheet，可筛选「逐项评审明细」 |

可选：`--strict` 额外解析 PDF/Word 正文；装 `openpyxl` 才有 Excel。

---

## 二、它做什么

四阶段流水线，对应 C4A 的 Level 1→4：

```
① 文件采集与作者识别     谁交了？         四级识别链 + 目录传播 + 别名归并
② 提交完整性检查         齐不齐？         五必须文件加权判定 + 判定依据
③ 技能质量评审           合格吗？         四条件 × 20 个加权 check_item
④ 评审报告生成           怎么改？         Markdown + JSON + Excel + HTML
```

### 三档评级，不是打分

| 评级 | 含义 |
|---|---|
| ✅ | 达标 |
| ⚠️ | 部分达标，有明确缺口 |
| ❌ | 不达标 |

### 每条判定都能追溯到行号

```
| 可复用 | ❌ | 57% | 🚫 否决证据：L20「路径是 /Users/lm/Desktop/meeting_summary/summary.py」|
```

评审者可以逐条打开原文件核对，不必相信工具。

---

## 三、核心设计：可信度优先

自动评审最大的风险不是"判错"——任何工具都会偶尔判错——
而是**"判错了还说得很有把握"**。所以本技能把C4A 里权重最高的
「评审准确性 / 误判率低」理解为**结论可追溯、风险主动暴露**。

| 机制 | 作用 |
|---|---|
| **证据化** | 每条判定带 `文件:行号 + 原文片段` |
| **置信度分级** | 结构性硬校验=high；单关键词命中=low，并强制提示人工复核 |
| **一票否决** | 硬编码路径 / 凭据泄露命中即把该维度封顶 ❌ |
| **矛盾检测** | 完整性高但质量极低（或反之）→ 报警"可能是空壳提交" |

### 一票否决为什么必需

朴素加权评分有个致命漏洞：

> 一份提交硬编码了 `/Users/lm/Desktop/summary.py`，
> 但同时有"安装说明"（+1.0）、相对路径写法（+0.8）、无凭据（+1.5）。
> 加权算得`3.3/5.8 = 57%` → ⚠️「部分满足」。

**但 C4 对可复用的检验原话是"让一个陌生人按你的说明操作，能成功吗？"**
答案已经是否定的。加权平均把致命伤稀释成了小瑕疵——
所以 veto 命中即封顶 ❌，不管其他项拿多少分。

---

## 四、实测表现

```bash
python tests/test_evaluator.py --accuracy
```

```
Ran 26 tests in 1.4s
OK

判定总数 : 15      一致数 : 15
人机一致率 : 100.0%    误判率 : 0.0%
```

**对 100% 必须泼冷水**（这点比数字本身更重要）：

1. 样本只有 3 份，**不能外推到任意班级**
2. ground truth 是我自己标的，可能与评审器共同犯错
3. 它证明的是"在已标注样本上结论可信"，不是"规则完美"
4. 剩余风险集中在 `low` 置信度结论上——评审器会**主动标记**让人工复核，
   而不是假装能判

---

## 五、目录结构

```
C4A_交付/
├── README.md                        ← 你在这里
├── 提交说明.md                交付物对照表 + 阅读顺序
├── Meteorain_C4A_方案设计.md          架构、选型理由、缺陷修复记录
├── Meteorain_C4A_评审报告.md          对 3 份提交的真实评审结果
├── Meteorain_C4A_教学说明.md          安装/使用/常见坑/答疑
├── Meteorain_C4A_AI日志.md开发全过程 AI 使用记录
├── Meteorain_C4A_拿来说明.md          从基座技能拿了什么、改了什么、为什么
├── Meteorain_C4A_skill-evaluator.skill  ← 可安装技能包
│
├── skill/c4a-skill-evaluator/     技能源码
│   ├── SKILL.md                    技能入口（触发词 + 工作流）
│   ├── scripts/
│   │   ├── c4a_evaluator.py        核心：四阶段流水线
│   │   └── render_dashboard.py     HTML 仪表板渲染器
│   └── references/
│       └── c4_rubric.yaml          评审标准（改标准不用改代码）
│
├── tests/
│   ├── test_evaluator.py           26 个测试 + 误判率测量
│   ├── render_demo.py              demo 截图生成器
│   └── golden_dataset/             3 份带ground truth 的测试提交
│       ├── ZhangWei/               优秀档
│       ├── LiMing/                 中等档（含硬编码路径）
│       └── WangXiao/               较差档（命名不规范）
│
├── reports/                        评审器真实产出
│   ├── Meteorain_C4A_评审报告.md
│   ├── Meteorain_C4A_评审详表.xlsx
│   ├── Meteorain_C4A_评审仪表板.html
│   ├── evaluation.json
│   ├── run_output.txt              真实运行日志
│   └── test_output.txt             真实测试日志
│
└── demo/                           3 张终端截图（由真实日志渲染）
    ├── demo_evaluator_cli.png
    ├── demo_tests_accuracy.png
    └── ZhangWei 提交内的 demo 截图
```

---

## 六、依赖

| 包 | 必需 | 缺失后果 |
|---|---|---|
| `pyyaml` | ✅ | 无法启动（明确报错） |
| `openpyxl` | ❌ | 跳过 Excel，MD/JSON 照常 |
| `pypdf` / `python-docx` / `python-pptx` | ❌ | 这些格式只按文件名判定 |

```bash
pip install -r requirements.txt    # 一次装全
```

**核心评审器除 PyYAML 外全部使用标准库**——
在没网的机器上也能跑。

---

## 七、常见使用

### 评全班

```bash
python skill/c4a-skill-evaluator/scripts/c4a_evaluator.py "/path/to/微信群文件" \
    --outdir ./reports --strict
```

打开 `*_评审仪表板.html` 看全班分布，
打开 Excel「逐项评审明细」筛`R2 = ❌` 一键找出所有写了硬编码路径的人。

### 提交前自检

```bash
python skill/c4a-skill-evaluator/scripts/c4a_evaluator.py ./我的C4提交 --outdir ./自检
```

重点看五必须文件齐不齐、四条件过没过、有没有写死路径。

### ⚠️ 排名要慎用

**本工具评的是提交材料的完整性，不是技能的实际影响力。**
C4 的评分核心是「被使用次数」。
一份材料齐全但没人用的技能会排在中上——这是工具的局限，不是使用者的错误。

---

## 八、扩展评审标准

判据全在 `skill/c4a-skill-evaluator/references/c4_rubric.yaml`，
**改它不用改代码**。

```yaml
# 加一个检查项
- id: E6
  name: "有 README"
  type: keyword# keyword / regex / structural / io_pattern / veto
  positive: ["README", "readme.md"]
  weight: 0.8

# 加一个否决项
- id: E7
  name: "无未替换的 TODO"
  type: veto
  negative: ["TODO", "FIXME", "待实现"]
  weight: 1.5
```

改完跑一次 `python tests/test_evaluator.py --accuracy` 确认没破坏判据。

**换一个 `c4_rubric.yaml` 就能评别的挑战**——
因为 `required_deliverables`（必交文件）与 `quality_criteria`（质量维度）
是两个独立配置块。

---

## 九、边界情况

| 情况 | 处理 |
|---|---|
| 空文件夹 | 明确报告"未识别到任何 C4 提交" |
| 文件名不规范 | 四级回退链：命名 → 目录 → 元数据 → 文档头 |
| 识别不出作者 | 标记 `Unknown`，**不参与排名** |
| 超大文件 > 50MB | 跳过正文，只按文件名判定 |
| 二进制文件 | 只文件名匹配 |
| 非 C4 文件混入 | 过滤后在报告末尾单列 |
| 损坏的 .skill 包 | 降级处理，不中断全批 |
| 缺 openpyxl |跳过 Excel，MD/JSON 照常 |
| 中文文件名 | UTF-8 + `errors="replace"` 兜底 |
| 中英混排文件夹 | 支持（`我的挑战/C4A_交付/...`） |

---

*评审器：`skill/c4a-skill-evaluator/scripts/c4a_evaluator.py`
判据：`skill/c4a-skill-evaluator/references/c4_rubric.yaml`
测试：`python tests/test_evaluator.py --accuracy`*