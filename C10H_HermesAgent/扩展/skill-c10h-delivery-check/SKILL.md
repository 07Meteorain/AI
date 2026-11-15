---
name: c10h-delivery-check
description: C10H 交付前检查清单：逐项核对 README、安装记录、配置说明、demo、AI日志与 AAR，避免红旗项。
version: 1.1.0
author: Meteorain (agent-assisted)
license: MIT
metadata:
  hermes:
    tags: [challenge, delivery, checklist, c10h]
    category: workflow
    related_skills: [hermes-agent, github]
---

# C10H 交付前检查清单

## When to Use

在提交 C10H（安装并驾驭 Hermes Agent）之前使用；也适用于任何「文档 + demo + 复盘」型挑战的最终自检。

触发词：`交付前`、`最后一轮检查`、`提交前`、`review 我的 C10H`。

## Procedure

按顺序检查，任何一项不通过就先修复再继续：

1. **README**
   - [ ] 30 秒内能说清「这是什么、怎么跑、产物在哪」
   - [ ] 有交付物地图（文件 → 内容 → 评分维度）
   - [ ] 所有相对链接都能打开

2. **安装记录**
   - [ ] 有时间线，包含失败与修复，而不是只写「安装成功」
   - [ ] 记录了版本、commit、安装路径、数据目录
   - [ ] 每条修复都有验证命令或输出

3. **配置说明**
   - [ ] `config.yaml` 每个非默认键都有「为什么」
   - [ ] 密钥只出现在 `.env`，仓库里只有 `.env.example`
   - [ ] 模型、上下文、网关、bash 路径这些本机特有配置有解释
   - [ ] 给出换云端模型的最小改法

4. **demo**
   - [ ] 至少 3 个场景，覆盖「工具调用 / 记忆 / 技能」中的两类以上
   - [ ] 保留原始 JSONL 轨迹，而不是只放截图
   - [ ] 每个场景有可复跑的 prompt 文件
   - [ ] 至少记录一次失败（幻觉、工具被拒、格式错误）

5. **AI日志**
   - [ ] 逐轮记录：目标 → prompt → 结果 → 判断 → 下一轮改法
   - [ ] 有 prompt 迭代对比（v1 哪里不够，v2 加了什么约束）
   - [ ] 标注哪些是 AI 做的、哪些是人判断的

6. **AAR 复盘**
   - [ ] 预期 vs 实际，用数据说话
   - [ ] 至少 3 个「为什么」追到根因
   - [ ] 改进方案可执行（下次具体做什么）
   - [ ] 含失败经验，不写成表扬稿

## Pitfalls

- **只放截图不放轨迹**：评审无法复现，也无法判断是不是模型幻觉。
- **把「已保存」当成保存**：小模型经常口头声称写入；必须 `read_file` / `cat` 回读。
- **忽略红旗项**：核心交付物缺失、无 AI 日志、一句话指令，任意一项都会把对应维度压到 5 分。
- **密钥进仓库**：`.env`、`auth.json`、日志里的 token 都要在提交前扫一遍。
- **demo 不设边界**：agent 在 `local` 后端拥有全部文件权限，demo 必须限定工作目录。

## Verification

```powershell
# 1) 红旗扫描：密钥、空文件、断链
Select-String -Path .\**\*.md -Pattern 'sk-|gho_|api[_-]?key\s*[:=]\s*[A-Za-z0-9]' -ErrorAction SilentlyContinue

# 2) 交付物齐全
$required = @('README.md','提交说明.md','安装记录\安装记录.md','配置说明\配置说明.md',
              'demo\README.md','AI日志\AI使用日志.md','复盘\AAR复盘.md')
$required | ForEach-Object { "{0} -> {1}" -f $_, (Test-Path $_) }

# 3) demo 轨迹可解析
python demo\tools\render_transcript.py demo\transcripts\01_summary.jsonl | Select-Object -First 5
```

全部通过后，在 `提交说明.md` 的验收表里逐项打勾，再提交。
