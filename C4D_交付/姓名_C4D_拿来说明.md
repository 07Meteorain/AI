# 姓名_C4D_拿来说明.md —— 使用的库/工具与参考来源

> **交付物 7/8** ｜ 完整披露本项目使用的所有库、工具、模型与参考资料，
> 便于评审复核与学习借鉴。

---

## 目录

1. [核心工具链](#1-核心工具链)
2. [模型](#2-模型)
3. [库依赖](#3-库依赖)
4. [地图服务](#4-地图服务)
5. [开发与调试工具](#5-开发与调试工具)
6. [参考资料](#6-参考资料)
7. [地图数据来源](#7-地图数据来源)
8. [合规声明](#8-合规声明)

---

## 1. 核心工具链

### 1.1 Ollama —— 本地大模型运行器

| 项 | 内容 |
|----|------|
| 用途 | 在本机运行 Gemma 4 模型，提供 OpenAI 兼容 API |
| 版本 | **v0.35.1** |
| 安装方式 | 官方安装包 `OllamaSetup.exe`（1.5 GB）|
| 下载地址 | <https://ollama.com/download> |
| 官方文档 | <https://docs.ollama.com> |
| 许可 | MIT |
| 是否使用云端 | ❌ 否。全部推理在`127.0.0.1:11434` 本地回环完成 |

**为什么选它**：挑战文档推荐的技术栈中，Ollama 难度标记为 ★（最低），
且自带 OpenAI 兼容 API，便于对照文档复现。

### 1.2 Gemma 4 —— 本次使用的模型

| 项 | 内容 |
|----|------|
| 模型名 | **`gemma4:e4b`** |
| 参数量 | ~4.5B effective（E2B 变体） |
| 量化方式 | **Q4_K_M**（4-bit GGUF） |
| 占用空间 | ~6.1 GB |
| 上下文长度 | 128K |
| 许可协议 | Apache 2.0 |
| 能力 | 文本+图像多模态、原生function calling、系统提示、结构化 JSON 输出 |

**选型理由**：本机 15.7 GB 内存 + RTX 3050 4GB 显存，
对应挑战文档"16GB 内存笔记本 → E4B"推荐档位。
26B（需~18GB）与 31B（需 ~20GB）在本机无法流畅运行。

官方资源：
- Ollama 模型页：<https://ollama.com/library/gemma4>
- Google 发布博客：<https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/>

---

## 2. 模型

### 2.1 本次使用的

| 模型 | 用途 | 备注 |
|------|------|------|
| `gemma4:e4b` | 主模型，全部任务 | Q4_K_M 量化 |

### 2.2 对比实验用

| 模型 | 用途 | 状态 |
|------|------|------|
| `gemma4:e2b` | Level 4 模型对比实验 | 见验证报告 |

### 2.3 能力使用情况

| 能力 | 是否使用 | 在哪里体现 |
|------|---------|-----------|
| 原生 function calling | ✅ | `agent.py` ReAct 循环，模型自主选工具 |
| 结构化 JSON 输出 | ✅ | `llm.py: structured()` + `format=json` |
| 系统提示 | ✅ | `agent.py: SYSTEM_PROMPT`（含工具文档与坐标禁令） |
| 多模态（图像） | ❌ | 本次未做视觉理解任务 |
| 微调 | ❌ | 挑战未要求 |

---

## 3. 库依赖

### 3.1 运行时依赖：**零**

```toml
dependencies = []
```

**本项目的核心库全部用Python 标准库实现**，这是刻意的工程决策：

| 常规做法 | 本方案 | 标准库模块 |
|---------|--------|-----------|
| `requests` | `urllib.request` |网络请求 |
| `SQLAlchemy` / `peewee` | `sqlite3` | 记忆持久化 |
| `pydantic` | `dataclasses` | 数据结构 |
| `folium` / `leaflet` | 自写 `map_view.py` | 地图渲染 |
| `json-repair` | 自写 `_extract_json()` | JSON 容错解析 |
| `tenacity` | 自写重试逻辑 | 重试 |

**理由**：rubric 的 `artifactCompleteness` 关注
"别人照着你的教学说明能跑通吗"。`git clone` 后不需要 `pip install`
就能运行，是降低复现门槛最有效的方式。

### 3.2 可选依赖

```toml
[project.optional-dependencies]
rich = ["psutil>=5.9"]     # 更详细的设备信息采集
dev  = ["pytest>=7.4"]     # 测试框架（也支持直接运行测试文件）
```

两者都是**可选**的：缺失时自动降级，不影响主流程。
`tests/test_offline.py` 可直接用 `python tests/test_offline.py` 运行，
不需要 pytest。

### 3.3 实际使用的第三方工具

| 工具 | 版本 | 用途 | 是否必需 |
|------|------|------|---------|
| `pypdf` | — | 解析挑战 PDF 文档（一次性准备） | 否 |
| Ollama | v0.35.1 | 本地模型推理 | **是** |

---

## 4. 地图服务

### 4.1 腾讯地图 GL JS

| 项 | 内容 |
|----|------|
| 用途 | 交互式地图底图渲染 |
| SDK | `https://map.qq.com/api/gljs?v=1.exp&libraries=service` |
| 坐标系 | **GCJ-02**（火星坐标系）|
| 密钥模式 | 官方 `_TMapSecurityConfig` 代理模式，前端零密钥 |
| 官方文档 | <https://lbs.qq.com/webApi/javascriptGL/glGuide/glOverview> |
| 密钥申请 | <https://lbs.qq.com/dev/console/key/management> |

### 4.2 为什么选腾讯地图

按国内地图服务合规要求，**禁止使用** Google Maps、Apple Maps、
Bing（境外版）、OpenStreetMap 直接瓦片、Mapbox 等未备案的地图源。
腾讯地图（及高德、百度、天地图）是合规选项中的一种。

本项目选腾讯地图并采用**密钥代理模式**：
SDK 从官方 CDN 加载且不带 `key` 参数，
请求经后端代理转发，密钥不暴露在前端代码中。

单元测试 `test_map_html_contains_required` 中有断言强制检查
生成的 HTML 不含 `openstreetmap` / `mapbox` / `googleapis` 字样，防止回归。

### 4.3 自定义标记图标

用**内联 SVG** 而非引用外部图片：

```javascript
src: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent('<svg ...>')
```

优点：无外部依赖、离线可用、可编程适配分类配色。

---

## 5. 开发与调试工具

### 5.1 编程环境

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.13.12 | 主体语言 |
| Git | 2.55.0 | 版本控制与提交 |
| PowerShell | — | 环境探测（`Get-CimInstance` 采集硬件信息）|

### 5.2 自研辅助脚本（`_meta/`）

这些脚本是解决本机环境问题的产物，一并提交以体现过程：

| 脚本 | 用途 |
|------|------|
| `fetch_ollama.py` | 绕过 curl 的 TLS/代理问题下载安装包 |
| `bench_download.py` / `bench2.py` | **诊断网络限速**：测量单连接 vs 多连接吞吐 |
| `fastdl.py` | 96 线程分段下载器（断点续传 + SHA-256 校验）|

`bench2.py` 的诊断结论直接决定了下载策略——这是关键的转折点。

### 5.3 测试

| 工具 | 用途 |
|------|------|
| 自研断言式测试 | `tests/test_offline.py`，38 项，零依赖可运行 |
| pytest（可选） | `python -m pytest tests/ -v`，更友好的输出 |

---

## 6. 参考资料

### 6.1 挑战相关

| 资料 | 用途 |
|------|------|
| `CHALLENGE.md` | 主任务要求、四级任务体系、交付清单 |
| `rubric.json` | 5 个评分维度与 red flag |
| `challenge.yaml` | 目标定义与交付物模式 |
| `materials/C4D.pdf` | 挑战完整 PDF 版 |
| `materials/C4D 补充说明.pdf` | **非 CS 专业通道**，发现双路径的关键依据 |

### 6.2 模型与运行

| 资料 | 链接 |
|------|------|
| Ollama 官方文档 | <https://docs.ollama.com> |
| Ollama Gemma 4 模型页 | <https://ollama.com/library/gemma4> |
| Gemma 4 发布博客 | <https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/> |
| Unsloth Gemma 4 本地运行指南 | <https://unsloth.ai/docs/models/gemma-4> |
| Gemma 4 硬件选购指南 | <https://www.compute-market.com/blog/gemma-4-local-hardware-guide-2026> |

### 6.3 Agent 设计

| 资料 | 用途 |
|------|------|
| ReAct 论文（Yao et al., 2022） | 推理-行动交替循环的设计来源 |
| OpenAI Function Calling 文档 | 理解 `tools` schema 规范 |
| Ollama 结构化输出文档 | `format=json` 与 JSON Schema 的用法 |

### 6.4 地图

| 资料 | 链接 |
|------|------|
| 腾讯地图 GL JS 文档 | <https://lbs.qq.com/webApi/javascriptGL/glGuide/glOverview> |
| 腾讯位置服务密钥代理配置 | <https://lbs.qq.com/webApi/javascriptGL/glGuide/glKeyDelegate> |

### 6.5 环境排查

| 资料 | 用途 |
|------|------|
| Ollama GPU 文档 | 排查 GPU offload 是否生效 |
| Ollama Windows 安装文档 | 静默安装参数 |

---

## 7. 地图数据来源

### 7.1 地点知识库

`knowledge.py` 中的 14 条地点数据来源：

| 类型 | 来源 | 说明 |
|------|------|------|
| 坐标 | 公开地理信息 | WGS84 坐标系，约 10~50 m 级精度 |
| 中文名 | 官方/通用名称 | 如"郑州西亚斯学院主校区" |
| 英文名 | 官方英文名 | 如 "SIAS University (Main Campus)" |
| 描述 | 基于公开信息整理 | 校园性质、职能、特色 |

### 7.2 使用限制（重要声明）

> ⚠️ 本知识库中的坐标为**近似值**，仅用于教学演示与Agent 流程验证。
>
> - **不用于**导航、测绘、工程设计等需要精确坐标的场景
> - 坐标经过四舍五入处理，精度约 10~50 米
> - 如需精确数据，请以高德/百度/腾讯地图等官方服务的查询结果为准
> - 数据整理自公开信息，可能随时间推移发生变化

### 7.3 隐私合规

- 只收录**公共场所**（校园、公共建筑、公园、车站、商场）
- **不包含**任何个人位置数据、住址、轨迹信息
- 符合《个人信息保护法》对批量点位数据的合规要求
- 未标注任何军事禁区、涉密单位或未公开敏感坐标

### 7.4 地图底图

- 底图瓦片由腾讯地图官方服务提供
- 本项目**不存储、不预下载**任何瓦片数据
- 地图交互完全在浏览器端完成

---

## 8. 合规声明

### 8.1 数据主权

| 项 | 状态 |
|----|------|
| LLM 推理位置 | ✅ 本地（`127.0.0.1:11434`） |
| 是否调用云端 LLM API | ✅ **否** |
| API 费用 | ✅ **0 元** |
| 用户数据是否外传 | ✅ **否** |
| 地点数据来源 | ✅ 随包分发的本地知识库 |

### 8.2 地图服务合规

| 项 | 状态 |
|----|------|
| 地图源 | ✅ 腾讯地图（合规白名单内） |
| 是否使用 Google/Apple/Bing境外版 | ✅ 否 |
| 是否使用 OSM / Mapbox | ✅ 否 |
| 前端是否暴露密钥 | ✅ 否（代理模式） |
| 坐标系 | ✅ GCJ-02 |
| 国界线/台海/南海诸岛 | ✅ 遵循国家标准 |
| 涉密区域标注 | ✅ 无 |
| 个人位置数据 | ✅ 无 |

### 8.3 内容合规

- 全部地点为公共场所，无个人隐私信息
- 地图标注不含任何未公开敏感信息
- 中文/英文描述基于客观事实，不含争议性表述

### 8.4 开源许可

| 组件 | 许可 | 说明 |
|------|------|------|
| Gemma 4 | Apache 2.0 | 模型许可 |
| Ollama | MIT | 运行器许可 |
| 本项目代码 | MIT | 见 `pyproject.toml` |

**注**：本项目为挑战作品，未标注任何非官方模型；
Gemma 4 为 Google 官方发布的 Apache 2.0 开源模型。

---

## 9. 完整交付物清单

对照 `CHALLENGE.md` 的提交要求：

| # | 交付物 | 路径 | 状态 |
|---|--------|------|------|
| 1 | 方案设计 | `姓名_C4D_方案设计.md` | ✅ |
| 2 | Agent 技能代码 | `姓名_C4D_agent-skill/` | ✅ 8 模块 + 38 测试 |
| 3 | 交互式地图 | `姓名_C4D_map.html` | ✅ 含 10+ 标记点 |
| 4 | 运行截图 | `姓名_C4D_output_screenshots/` | ✅ 7 张 |
| 5 | 验证报告 | `姓名_C4D_验证报告.md` | ✅ |
| 6 | 教学说明 | `姓名_C4D_教学说明.md` | ✅ |
| 7 | **AI 日志（必）** | `姓名_C4D_AI日志.md` | ✅ |
| 8 | 拿来说明 | `姓名_C4D_拿来说明.md` | ✅ 本文件 |
| 9 | AAR 复盘 | `姓名_C4D_AAR.md` | ✅ |
| 10 | 总览 | `README.md` | ✅ |

补充说明要求的截图四项证据，全部覆盖：

| 证据 | 截图 |
|------|------|
| ① 模型名称及版本 | `02_模型版本与量化.png` |
| ② 运行工具及版本 | `01_设备与环境.png`（含 Ollama v0.35.1） |
| ③ 设备信息 | `01_设备与环境.png` |
| ④ 推理速度 tok/s | `03_推理速度tok_s.png` |

---

*本文件所列所有工具、库、模型版本均来自实际运行环境，
相关日志见 `姓名_C4D_agent-skill/logs/`。*