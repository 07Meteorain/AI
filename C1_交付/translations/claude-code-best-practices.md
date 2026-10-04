---
title: Claude Code 最佳实践
doc_id: claude-code-best-practices
category: Week 4 · Claude Code
source: CS146S_offline/pages/claude-code-best-practices.html
origin: https://www.anthropic.com/engineering/claude-code-best-practices
translator: AI 机器翻译 + 人工校对（术语表 v1.0）
coverage: 100%
---

# Claude Code 最佳实践

> 原文：[https://www.anthropic.com/engineering/claude-code-best-practices](https://www.anthropic.com/engineering/claude-code-best-practices)

Claude Code 文档首页

入门

用 Claude Code 构建

部署

管理

配置

参考

资源

##### 入门

- 概览

##### 核心概念

##### 使用 Claude Code

##### 平台与集成

- 下一步

入门

# Claude Code 概览

Claude Code 是一款智能体式的编码工具，它能读取你的代码库、编辑文件、运行命令，并与你的开发工具集成。可在终端、IDE、桌面应用和浏览器中使用。

Claude Code 是一个由 AI 驱动的编码助手，能帮你构建功能、修复缺陷、自动化开发任务。它理解你整个代码库，能跨多个文件和工具把事情做完。

开始使用

选择你的环境开始上手。大多数形态需要 Claude 订阅或 Anthropic Console 账号。终端 CLI 和 VS Code 也支持第三方提供商。

- 终端

- VS Code

- 桌面应用

功能完备的 CLI，直接在你的终端里使用 Claude Code。从命令行编辑文件、运行命令、管理整个项目。安装 Claude Code 有以下几种方式：

- 原生安装（推荐）

- Homebrew

- WinGet

macOS、Linux、WSL：

```
```
curl -fsSL https://claude.ai/install.sh | bash
```
```
Windows PowerShell：

```
```
irm https://claude.ai/install.ps1 | iex
```
```
Windows CMD：

```
```
curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd
```
```
如果你看到 The token '&&' is not a valid statement separator，说明你在 PowerShell 里而不是 CMD 里。请改用上面的 PowerShell 命令。在 PowerShell 中，命令行提示符显示为 PS C:\。Windows 需要 Git for Windows，如果你还没有安装，请先装上。

原生安装会在后台自动更新，让你的版本保持最新。

```
```
brew install --cask claude-code
```
```
Homebrew 安装不会自动更新。请定期运行 brew upgrade claude-code，以获取最新功能和安全修复。

```
```
winget install Anthropic.ClaudeCode
```
```
WinGet 安装不会自动更新。请定期运行 winget upgrade Anthropic.ClaudeCode，以获取最新功能和安全修复。

然后在任何项目中启动 Claude Code：

```
```
cd your-project
claude
```
```
首次使用时你会看到登录提示。就这样！继续阅读快速上手 →

有关其他安装方式、手动更新或卸载说明，请查看高级安装设置。如遇问题，请查阅故障排查。

VS Code 扩展直接在编辑器内提供内联差异对比、@ 提及、计划评审和对话历史。

- 安装到 VS Code

- 安装到 Cursor

也可以在扩展视图（Mac 上是 Cmd+Shift+X，Windows/Linux 上是 Ctrl+Shift+X）中搜索「Claude Code」。安装后，打开命令面板（Cmd+Shift+P / Ctrl+Shift+P），输入「Claude Code」，并选择 Open in New Tab。开始使用 VS Code →

一款独立应用，让你在 IDE 或终端之外也能运行 Claude Code。直观地查看差异、并行运行多个会话、安排周期性任务，以及启动云端会话。下载并安装：

- macOS（Intel 和 Apple Silicon）

- Windows (x64)

- Windows ARM64（仅远程会话）

安装后，启动 Claude、登录，然后点击 Code 标签页开始写代码。需要付费订阅。了解更多桌面应用 →

在浏览器里运行 Claude Code，无需任何本地设置。启动长时间运行的任务，完成后再回来看，操作你本地没有的仓库，或者并行运行多个任务。可在桌面浏览器和 Claude iOS 应用中使用。在 claude.ai/code 开始写代码。开始使用网页版 →

一款面向 IntelliJ IDEA、PyCharm、WebStorm 等 JetBrains IDE 的插件，支持交互式查看差异和共享选中内容的上下文。从 JetBrains Marketplace 安装 Claude Code 插件，然后重启你的 IDE。开始使用 JetBrains →

你可以做什么

以下是一些使用 Claude Code 的方式：

把一直拖着没做的事自动化

Claude Code 会处理那些占用你整天的枯燥任务：为没有测试的代码补写测试、修复整个项目里的 lint 错误、解决合并冲突、更新依赖、撰写发布说明。

```
```
claude "write tests for the auth module, run them, and fix any failures"
```
```
构建功能、修复缺陷

用日常语言描述你想要什么。Claude Code 会规划做法、跨多个文件编写代码，并验证是否可行。如果是缺陷，粘贴报错信息或描述症状即可。Claude Code 会在你的代码库中追踪问题、定位根因并实现修复。更多例子见常见工作流。

创建提交和拉取请求

Claude Code 直接与 git 协作。它能暂存改动、编写提交信息、创建分支并开启拉取请求。

```
```
claude "commit my changes with a descriptive message"
```
```
在 CI 中，你可以用 GitHub Actions 或 GitLab CI/CD 自动化代码评审和问题分类。

用 MCP 连接你的工具

Model Context Protocol（MCP）是一个把 AI 工具连接到外部数据源的开放标准。借助 MCP，Claude Code 可以读取 Google Drive 中的设计文档、更新 Jira 中的工单、从 Slack 拉取数据，或者使用你自己的自定义工具。

用指令、skills 和 hooks 定制

CLAUDE.md 是一个 markdown 文件，你把它放在项目根目录，Claude Code 会在每次会话开始时读取它。用它来设定编码规范、架构决策、常用库和评审清单。Claude 还会一边工作一边自动建立记忆，把构建命令、调试心得这类经验跨会话保存下来，你什么都不用写。创建自定义命令，把团队可以共享的可复用工作流打包进去，比如 /review-pr 或 /deploy-staging。Hooks 让你在 Claude Code 的操作前后运行 shell 命令，比如每次编辑文件后自动格式化，或在提交前先跑一遍 lint。

运行智能体团队并构建自定义智能体

派生多个 Claude Code 智能体，让它们同时处理任务的不同部分。由一个主智能体负责协调工作、分配子任务并合并结果。若要实现完全定制的工作流，Agent SDK 让你构建自己的智能体，由 Claude Code 的工具与能力驱动，并对编排、工具访问和权限拥有完全控制权。

用 CLI 串联、编写脚本并自动化

Claude Code 可组合，遵循 Unix 理念。把日志经由输入流传给它、在 CI 中运行它，或者与其他工具串联起来：

```
```
# Analyze recent log output
tail -200 app.log | claude -p "Slack me if you see any anomalies"

# Automate translations in CI
claude -p "translate new strings into French and raise a PR for review"

# Bulk operations across files
git diff main --name-only | claude -p "review these changed files for security issues"
```
```
完整的命令和选项集合见 CLI 参考。

安排周期性任务

按计划运行 Claude，把重复性的工作自动化：早上评审 PR、隔夜分析 CI 失败、每周做依赖审计，或在 PR 合并后同步文档。

- 云端定时任务运行在 Anthropic 托管的基础设施上，因此即使你的电脑关机也能继续运行。可以在网页、桌面应用或 CLI 中运行 /schedule 来创建。

- 桌面定时任务在你的机器上运行，可直接访问本地文件和工具

- /loop 在一个 CLI 会话内重复某条提示词，用于快速轮询

随处工作

会话并不绑定在单一形态上。你可以随着场景变化在不同环境之间迁移工作：

- 离开工位，用手机或任何开启了 Remote Control 的浏览器继续工作

- 用 Message Dispatch 从手机上派发任务，并打开它创建的桌面会话

- 在网页或 iOS 应用上启动一个长时间运行的任务，然后用 claude --teleport 把它拉回终端

- 用 /desktop 把终端会话交给桌面应用，直观地查看差异

- 从团队聊天中路由任务：在 Slack 上发一份缺陷报告并 @Claude，拿到一个拉取请求

随处使用 Claude Code
每种形态都连接到同一个底层 Claude Code 引擎，因此你的 CLAUDE.md 文件、设置和 MCP 服务器在各形态下都能正常工作。

除了上面提到的终端、VS Code、JetBrains、桌面和网页环境，Claude Code 还能与 CI/CD、聊天和浏览器工作流集成：

下一步

装好 Claude Code 之后，这些指南能帮你走得更深。

- 快速上手：带你走完第一个真实任务，从探索代码库到提交修复

- 存储指令与记忆：用 CLAUDE.md 文件和自动记忆为 Claude 提供持久指令

- 常见工作流与最佳实践：充分发挥 Claude Code 效能的实用范式

- 设置：按你的工作流定制 Claude Code

- 故障排查：常见问题的解决方案

- code.claude.com：演示、定价和产品详情

这个页面对你有帮助吗？

快速上手

⌘I

助手

回复由 AI 生成，可能存在错误。
