# AI

AI 相关的学习产出与项目沉淀。

## 目录

| 路径 | 内容 |
|---|---|
| [`C1_交付/`](C1_交付/) | **Stanford CS146S 课程资料中文包** — 33 篇课程资料全量翻译 + 可复跑翻译管线 |

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
| [`AI协作日志.md`](C1_交付/AI协作日志.md) | 逐日工具、prompt、踩坑记录 |
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

## 版权声明

课程资料版权归原作者所有，本仓库内容仅供学习参考。
每篇文档的一手来源链接见 `C1_交付/translations/index.md` 及各篇 front-matter。