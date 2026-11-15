# Demo：让 Hermes 真干活

这里不是截图拼贴，而是**可复跑的原始记录**：每条 demo 都是真实的 `hermes chat` 调用，输出保留为 `stream-json`（一行一个事件），并用 `tools/render_transcript.py` 转成可读 Markdown。

## 前置条件

| 项 | 要求 |
| --- | --- |
| Hermes | `E:\hermes\bin\hermes.exe`（本仓库的安装位置），`HERMES_HOME=E:\hermes` |
| 模型 | Ollama + `gemma4-e2b-64k`（num_ctx=65536），监听 `127.0.0.1:11434` |
| 网关 | `hermes gateway run` 正在运行（CLI 会话通过本地网关执行） |
| Python | 3.11+（只用标准库，用于渲染 transcript） |

一键检查：

```powershell
$env:HERMES_HOME='E:\hermes'
E:\hermes\bin\hermes.exe doctor
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list
```

## 场景

| # | 目标 | prompt | 结果文件 |
| --- | --- | --- | --- |
| 01 | 读文件 + 写文件 + 回读验证 | `prompts/01_summary.md` | `workspace/out/summary.md` |
| 02 | 真实写入跨会话记忆 | `prompts/02_memory_write.md` | `E:\hermes\memories\USER.md` |
| 03 | 新会话读取记忆 | `prompts/03_memory_read.md` | 对话回复 |
| 04 | 用 `skill_manage` 创建技能 | `prompts/04_skill.md` | `E:\hermes\skills\...\SKILL.md` |

## 复跑

```powershell
# 1) 起网关（另开一个窗口，保持运行）
$env:HERMES_HOME='E:\hermes'
E:\hermes\bin\hermes.exe gateway run

# 2) 在 demo 目录执行
cd demo
.\run_demo.ps1 -Scenario 01
```

`run_demo.ps1` 会把原始 JSONL 写到 `transcripts/`，并调用渲染器生成同名 `.md`。

## 阅读顺序

先看 `transcripts/01_summary.md`：能清楚看到 `read_file ×2 → write_file → read_file(验证)` 四个工具调用，以及最终 `exit_code=0`。再看 `02`、`03` 两次会话，理解「记忆写入」与「新会话读取」为什么必须分开。

## 已知边界

- 本机只有 4 GB 显存，4.6B 模型每轮 prefill 约 1–3 分钟；这是硬件限制，不是 Hermes 卡死。
- 单查询模式（`-q`/`--oneshot`）默认禁止 `execute_code`，这是 Hermes 的安全设计；demo 里显式改用 `file`/`terminal` 工具。
- 小模型会出现「口头声称已写入」的幻觉，见 `../证据/失败-01-幻觉写入.jsonl`；prompt 里因此加入了强制回读验证。
