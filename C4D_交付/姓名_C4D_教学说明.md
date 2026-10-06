# 姓名_C4D_教学说明.md —— 安装与复现指南

> **交付物 6/8** ｜ 面向**零基础同学**，照着做就能跑通
> 目标读者：没有编程经验的非计算机专业同学也能完成

---

## 你会得到什么

跑完这份教程，你会：

1. 在自己的电脑上装好 Ollama（本地大模型运行器）
2. 用Gemma 4 在本地跑通一次真实推理，亲眼看到 tok/s 速度
3. 跑出一个**交互式地图**（自己电脑生成，零API 费用）
4. 用一个**有记忆的 Agent** 和本地模型多轮对话

全程不需要注册任何 API 账号，不需要付费，数据不离开你的电脑。

---

## 第0 步：确认你的电脑能跑什么

打开 PowerShell（Windows 按 `Win + X` → "终端"），输入：

```powershell
systeminfo | findstr "Total Physical Memory"
```

对照下表选择模型：

| 你的内存 | 推荐模型 | 大小 | 运行速度 |
|---------|---------|------|---------|
| 8 GB | `gemma4:e2b` | ~3 GB | 慢但能用 |
| **16 GB** | **`gemma4:e4b`** | ~6.1 GB | **流畅（推荐）** |
| 24 GB+ 显存 | `gemma4:26b` | ~18 GB | 快 |

> 本次运行的机器是 **15.7 GB 内存 + RTX 3050**，所以选了 **E4B**。

---

## 第 1 步：安装 Ollama

### Windows

1. 打开 <https://ollama.com/download>
2. 下载 `OllamaSetup.exe`（约 1.5 GB，下载可能需要几分钟）
3. 双击安装，一路点"继续"即可

### macOS

```bash
brew install ollama
# 或从 https://ollama.com/download 下载 dmg 包
```

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 验证安装

```powershell
ollama --version
# 应输出：ollama version is 0.35.1 （版本号可能不同）
```

---

## 第 2 步：下载 Gemma 4 模型

```powershell
ollama pull gemma4:e4b
```

**会下载约 6.1 GB**，耐心等待。进度条走完后验证：

```powershell
ollama list
```

应看到类似输出：

```
NAME           ID              SIZE      MODIFIED
gemma4:e4b     xxxxxxxx        6.1 GB    现在
```

### 启动 Ollama 服务

Windows 上如果 Ollama 没在后台运行，手动启动：

```powershell
ollama serve
```

> **提示**：看到这个输出就说明服务正常，保持窗口不要关闭：
> ```
> Listening on 127.0.0.1:11434 (version 0.35.1)
> ```
>
> 另开一个窗口做下面的验证。

**验证服务**（另开窗口）：

```powershell
curl http://localhost:11434/api/tags
# 应返回：{"models":[{"name":"gemma4:e4b",...}]}
```

---

## 第 3 步：第一次本地推理（亲眼看到 tok/s）

### 方法 A：命令行对话

```powershell
ollama run gemma4:e4b
```

输入：

```
用一段话介绍郑州西亚斯学院
```

结束后输入 `/bye` 退出。**注意看右下角的 `tok/s` 显示**——
这就是你电脑的本地推理速度，也是挑战要求记录的证据。

### 方法 B：API 调用

```powershell
$body = @{
  model = "gemma4:e4b"
  messages = @(@{ role = "user"; content = "用一段话介绍郑州西亚斯学院" })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:11434/api/chat" `
  -Method Post -Body $body -ContentType "application/json"
```

返回的 JSON 里看这两个字段：
- `eval_count`：生成了多少 token
- `eval_duration_ns`：推理耗时（纳秒）
- **tok/s = eval_count / (eval_duration_ns / 1e9)**

---

## 第 4 步：跑通本项目的 Agent 技能

### 4.1 获取代码

```powershell
git clone https://github.com/07Meteorain/AI.git
cd AI
```

或直接下载 ZIP 解压。

### 4.2 进入技能目录

```powershell
cd 姓名_C4D_agent-skill
```

### 4.3 环境自检（推荐先做这步）

```powershell
python -m sias_local_agent.cli doctor
```

**期望输出**：

```
==============================================================
C4D 本地大模型 Agent —— 环境自检
==============================================================
时间: 2026-10-06 15:00:00
--- 设备信息 ---
  cpu: 11th Gen Intel(R) Core(TM) i5-11400H @ 2.70GHz
  ram_gb: 15.7
  gpu: ['NVIDIA GeForce RTX 3050 Laptop GPU', ...]
--- Ollama 服务 ---
  endpoint: http://localhost:11434
  ✓ 服务可用，已安装模型: gemma4:e4b
  当前使用: gemma4:e4b
--- 推理基准 ---
  模型: gemma4:e4b
  tokens: 87
  速度: 24.31 tok/s
  耗时: 3578.5 ms
✓ 自检通过
```

> **看到 `✓ 自检通过` 就说明环境完全就绪。**

### 4.4 先跑不需要模型的测试（验证代码完整性）

```powershell
python tests/test_offline.py
```

**期望输出**：`38/38 passed`

这一步不需要模型，能验证 JSON 解析、记忆、工具、地图渲染等全部核心逻辑。

### 4.5 生成交互式地图（核心任务）

```powershell
python -m sias_local_agent.cli run --task map --count 10
```

**会发生什么**：
1. Agent 把你的指令 + 14 条本地地点数据（含真实坐标）交给本地模型
2. 模型自主决定调用哪些工具（如 `get_reference` 查坐标）
3. 工具结果回灌给模型，模型据此生成中英文描述和JSON
4. 程序把 JSON 渲染成交互式地图 HTML

**期望输出**：

```
[step 1] tool=get_reference args={"name": "图书馆"} (24.3 tok/s)
[step 2] final (23.8 tok/s)
归一化后地点数: 10
坐标校验: 10/10 位于合理区域
✓ 地图已生成: output/sias_map.html
```

### 4.6 打开地图

双击 `output/sias_map.html`，或拖到浏览器。

你应该能看到：
- 腾讯地图底图，以西亚斯学院为中心的 10 个标记点
- 不同颜色代表不同类别（校园蓝、交通绿、文化紫、商业橙、自然青）
- **点击标记** →弹出气泡显示中英文名称、双语描述、精确坐标
- **点击左侧清单** → 地图自动居中到该点
- **地图顶部证据条** → 显示模型名、设备、tok/s、工具调用次数

### 4.7 试试多轮对话（体验"记忆"）

```powershell
python -m sias_local_agent.cli chat
```

试试这样交互：

```
你> 我叫小明，我不喜欢太吵的地方
AI> 好的，我记住了。

你> :remember 预算=100元
  ✓ 已记住: 预算 = 100元

你> 我叫什么名字？
AI> 你叫小明。            ← 模型调用了 recall 工具，从长期记忆中取回

你> 我的预算是多少？
AI> 100元。               ← 记忆在多轮之间保持

你> quit
```

查看记忆内容：

```powershell
python -m sias_local_agent.cli memory
```

**重启终端后再执行一次 `memory`，你会发现记忆还在**——
因为它存在 SQLite 数据库文件里。

### 4.8 规划一条行程（多工具调用演示）

```powershell
python -m sias_local_agent.cli run --task plan --count 6
```

这次模型会依次调用 `get_reference` 查坐标、`plan_route` 排顺序，
输出结构化行程。结果在 `output/itinerary.json`。

### 4.9 性能基准

```powershell
python -m sias_local_agent.cli bench --rounds 3
```

输出每轮 tok/s 与平均值，数据存到 `logs/bench.json`。

### 4.10 模型对比（Level 4 加分项）

需要先拉另一个模型：

```powershell
ollama pull gemma4:e2b
python -m sias_local_agent.cli compare --models gemma4:e2b gemma4:e4b
```

---

## 第 5 步：生成交付用的证据截图

```powershell
python -m sias_local_agent.screenshots
```

会在 `姓名_C4D_output_screenshots/` 生成 7 张终端风格证据图，
涵盖挑战要求的四项必需信息：

| 截图 | 包含的必需信息 |
|------|--------------|
| `01_设备与环境.png` | ③ 设备信息（CPU/GPU/内存/OS）+ ② 运行工具版本 |
| `02_模型版本与量化.png` | ① 模型名称与量化方式 |
| `03_推理速度tok_s.png` | ④ 实际推理速度 |
| `04_Agent工具调用.png` | Agent 能力证据（工具调用+结构化输出） |
| `05_记忆能力.png` | 记忆能力（补充证据） |
| `06_模型对比.png` | Level 4 加分项 |
| `07_离线测试.png` | 代码质量证据 |

---

## 常见问题排查

### Q1: `ollama` 命令找不到

**原因**：PATH 没刷新。
**解决**：关掉终端重新打开；或手动添加环境变量：
```
C:\Users\你的用户名\AppData\Local\Programs\Ollama
```

### Q2: `无法连接localhost:11434`

**原因**：Ollama 服务没启动。
**解决**：另开一个终端运行 `ollama serve`。

### Q3: 拉模型特别慢或中断

**原因**：网络问题。
**解决**：
```powershell
# 断点续传，重新 pull 会继续下载未完成部分
ollama pull gemma4:e4b
```
如果单连接被限速严重，可以用本项目的多线程下载思路
（见 `_meta/fastdl.py`）。

### Q4: `python` 命令找不到

**解决**：安装 Python 3.10+ 并勾选 "Add to PATH"。
或用 `py` 代替 `python`。

### Q5: 推理很慢（低于 5 tok/s）

**可能原因与对策**：

| 原因 | 对策 |
|------|------|
| 模型部分加载到了 CPU | 确认 Ollama 检测到 GPU：`ollama ps` |
| 内存不足在用 swap | 关掉一些占内存的程序 |
| 选了太大的模型 | 换`gemma4:e2b` |
| 上下文设得过大 | CLI 加 `--ctx 4096` |

查看 GPU 是否被使用：

```powershell
ollama ps
# 看 PROCESSOR 列，显示 100% GPU 才算用上独显
```

### Q6: 地图打开是空白/灰色

**原因**：腾讯地图 SDK 未加载（网络受限）。
**说明**：
- 标记数据不受影响，左侧清单仍会显示
- 在 WorkBuddy 预览面板中打开会自动启用密钥代理
- 若需在自己的环境使用，配置自有密钥：
  编辑 `sias_local_agent/map_view.py` 中的 `KEY_PLACEHOLDER`，
  填入你在 <https://lbs.qq.com/dev/console/key/management> 申请的密钥
  （个人使用建议配置 Referer 白名单）

### Q7: 模型输出的 JSON 解析失败

**原因**：小模型偶尔不遵守格式。
**解决**：本项目已内置三层防御（见下节）。若仍失败，
可降低温度增加确定性：

```powershell
python -m sias_local_agent.cli --temperature 0.1 run --task map
```

---

## 本项目用了哪些"防错"设计

即使你换了别的模型，这些设计也会生效：

| 问题 | 对策 |
|------|------|
| 模型输出带 ```json 围栏 | 自动剥离 |
| 模型在JSON 前后加解释文字 | 扫描配平的括号提取 |
| 字段名写成 `lat` 而不是 `latitude` | 归一化层兼容多种变体 |
| 模型编造坐标 | 知识库注入 + `validate_coords` 校验 |
| 对话历史超长撑爆上下文 | 按预算自动裁剪最旧消息 |
| 工具执行报错导致整体崩溃 | 异常捕获后把错误回灌给模型 |

---

## 完全复现：一条命令跑全部流程

```powershell
# 从零到出地图（假设已装好 Ollama 和模型）
cd 姓名_C4D_agent-skill
python -m pytest tests/ -v                        # 1. 验证代码
python -m sias_local_agent.cli doctor              # 2. 环境自检
python -m sias_local_agent.cli run --task map --count 10   # 3. 生成地图
python -m sias_local_agent.cli bench --rounds 3   # 4. 性能基准
python -m sias_local_agent.screenshots             # 5. 生成证据截图
```

---

## 目录速查

```
姓名_C4D_agent-skill/
├── output/sias_map.html      ← 生成的地图在这里
├── logs/                     ← 所有运行日志（真实记录）
│   ├── doctor.log            环境自检
│   ├── bench.json            性能数据
│   ├── run_map_*.json        地图任务完整轨迹
│   ├── locations.json        模型生成的地点数据
│   └── chat_transcript.json  对话记录
├── data/memory.db            记忆数据库（SQLite）
└── sias_local_agent/         源码
```

---

## 环境要求小结

| 项 | 最低 | 推荐 |
|----|------|------|
| 内存 | 8 GB |16 GB |
| 磁盘 | 6 GB 可用 | 10 GB |
| Python | 3.10 | 3.11+ |
| 系统 | Windows 10 / macOS 12+ / Linux | Windows 11 |
| GPU | 可选 | 4GB+ 显存 NVIDIA |

---

*遇到问题可以先跑 `python -m sias_local_agent.cli doctor`，
它会明确告诉你哪一环出了问题。*