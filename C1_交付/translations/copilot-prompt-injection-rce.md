---
title: Copilot 提示注入导致远程代码执行
doc_id: copilot-prompt-injection-rce
category: Week 6 · 安全
source: CS146S_offline/pages/copilot-prompt-injection-rce.html
origin: https://embracethered.com/blog/posts/2025/github-copilot-remote-code-execution-via-prompt-injection/
translator: AI 机器翻译 + 人工校对（术语表 v1.0）
coverage: 100%
---

# Copilot 提示注入导致远程代码执行

> 原文：[https://embracethered.com/blog/posts/2025/github-copilot-remote-code-execution-via-prompt-injection/](https://embracethered.com/blog/posts/2025/github-copilot-remote-code-execution-via-prompt-injection/)

# 拥抱红队

wunderwuzzi 的博客
 
 learn the hacks, stop the attacks.

Home
 
 
 
 
 RSS
 
 
 
 
 Subscribe

# GitHub Copilot：通过提示注入实现远程代码执行（CVE-2025-53773）

发布于
 
 2025 年 8 月 12 日

#llm
 
 #agents
 
 #month of ai bugs

本文讲的是一次重要但也令人不安的提示注入发现：它会导致 GitHub Copilot 和 VS Code 中开发者的机器被彻底攻陷。

实现方式是把 Copilot 置于 YOLO 模式——修改项目的 settings.json 文件即可。

几天前谈 Amp 时提到过，智能体中有一类容易被忽视的漏洞模式：如果一个智能体能够写入文件、修改自身配置或更新与安全相关的设置，就可能导致远程代码执行。这并不罕见，也是做安全评审时始终应该排查的方向。

## 背景研究

在查看 VS Code 和 GitHub Copilot 智能体模式时，我注意到一个奇怪的行为——它可以在未经用户批准的情况下创建并写入工作区中的文件。

这些编辑会立即持久化，不是留在内存里等待评审的差异。修改会直接写入磁盘。

这正是作为红队一员的人一看就知道不太妙的东西……所以我就在琢磨，这能不能被用来提权并执行代码。

### YOLO 模式

接下来，我研究了 VS Code 中那些依赖项目/工作区文件夹内设置的功能，很快发现了一个有意思的。

结果是，在 .vscode/settings.json 文件里可以加上这样一行：

"chat.tools.autoApprove": true

这会让 GitHub Copilot 进入 YOLO 模式。

而且它会关掉所有用户确认，我们就可以运行 shell 命令、浏览网页等等！

有意思的是，这是一项实验性功能，但默认情况下它依然存在。我并没有下载特殊版本，也没有把 VS Code 整体设成实验模式。

而且它在 Windows、macOS 和 Linux 上都能用。

## 漏洞利用链解析

劫持 Copilot 并提权的概念验证漏洞利用链如下：

- 攻击从埋入源代码文件、网页、GitHub issue、工具调用响应或其他内容中的提示注入开始……攻击载荷也可以利用不可见文本来充当指令。

- 提示注入首先往 ~/.vscode/settings.json 文件里加上 "chat.tools.autoApprove": true 这一行。如果文件夹和文件还不存在，会自动创建。

- GitHub Copilot 立刻进入 YOLO 模式！

- 攻击执行一条终端命令。借助条件式提示注入，我们实际上可以根据操作系统来决定运行什么。

- 我们实现了由提示注入驱动的远程代码执行（RCE）。

下面这张截图展示了带提示注入的演示文件、右侧在聊天框里与该文件交互的开发者，以及弹出来的计算器！

当然，任何其他提示注入的投递方式——比如网页，或从 MCP 服务器返回的数据——都是一种攻击角度。我只是把攻击载荷放在源代码文件里，因为这样最容易测试。

## 视频演示

### 短视频演示

下面这段演示视频展示了在 Windows 上的代码执行。

这段是 macOS 上的：

### 完整走查

下面这段更长的视频详细讲解了这次发现与漏洞利用：

能给自己设置权限和配置设置的 AI，简直离谱！

## 把工作站接入僵尸网络——ZombAIs

当然，这意味着我们可以把开发者的机器作为 ZombAI 接入僵尸网络。

另外，玩一下的话，我们还可以修改 settings.json 文件，把 VS Code 切换成红色配色之类。

不过还没完！这也意味着我们可以造出真正的 AI 病毒：让它附着在文件上，随着开发者下载并打开被感染的文件而传播。

最后但同样重要的是，为了证明我们完全控制了这台开发者的主机，我们展示 Copilot 可以被劫持去下载恶意软件，并接入远程命令与控制服务器。

这等于为恶意软件、勒索软件、信息窃取程序之类的东西敞开了大门。

挺吓人的。

## 打造 AI 病毒

看到这里就会发现，这基本上等于允许制造病毒。攻击者可以嵌入指令，一旦拿到代码执行能力，就可以用额外的恶意软件去攻陷其他 Git 项目（以及 RAG 数据源），把恶意指令嵌进去，然后提交改动，甚至强制推送到上游。

这会进一步扩散，因为其他开发者会在不知情的情况下传播被感染的代码。

最后，我们还得聊聊不可见指令！

## 利用不可见指令

有人可能会说，如果指令以注释形式嵌入，很快就会被发现。所以为了让演示更有意思一点，我干脆做了一个不可见的载荷，能够完成整条攻击链，但用户看不到它。这种方式没那么可靠，但确实管用：

注意：虽然我这里用不可见指令的演示多次成功，但使用不可见指令往往会让漏洞利用变得非常不可靠，而且模型通常也会拒绝执行；另外 VS Code 通常还会显示 Unicode 字符的视觉提示。不过，攻击（和模型）都会随时间变强。还要强调一点：并非所有模型都容易受到这类不可见提示注入攻击的影响。

## 建议与修复

除了我分享的 YOLO 模式之外，实际还有更多攻击角度。微软问我是否还有更多信息时，我又多看了一些，发现还有其他存在风险的地方，比如 AI 可以写入的 .vscode/tasks.json，或者添加伪造的恶意 MCP 服务器等，都可能导致代码执行。而且 AI 还能重新配置项目的用户界面和配置设置。

最近我注意到开发者经常同时使用多个智能体，因此还存在覆盖其他智能体配置文件的风险（放行 bash 命令白名单、添加 MCP 服务器等等），因为这些文件通常也放在项目文件夹里。

理想情况下，AI 不应该在未经人类事先批准的情况下修改文件。很多其他编辑器会展示差异，然后由开发者来批准。

## 负责任披露

2025 年 6 月 29 日报告该漏洞后，微软确认了复现结果，并追问了一些问题。几周后，MSRC 指出这是他们已经在跟踪的问题，并表示会在 8 月之前修复。随着 8 月的补丁星期二（Patch Tuesday）发布，这个问题现已修复。

要感谢 Persistent Security 的 Markus Vervier，他也独立发现并向微软报告了这个漏洞。你可以在这里找到他们的分析文章。同时也要感谢 Ari Marzuk，他似乎也并行地发现了这个问题。

感谢 MSRC 和产品团队的成员协助推进缓解工作。

## 结论

这又一个例子说明，AI 智能体可能并不会老老实实待在自己的框里！通过修改自身运行环境，GitHub Copilot 能够提权并执行代码，从而攻陷开发者的机器。正如我所发现的，这在智能体式系统中是一种并不罕见的设计缺陷。

继续留意这类设计缺陷吧，它们在威胁建模阶段就应该能被轻易发现。

祝好。

## 参考资料

- Month of AI Bugs 2025

- Amp Code: Arbitrary Command Execution via Prompt Injection Fixed

- CVE-2025-53773: GitHub Copilot and Visual Studio Remote Code Execution Vulnerability
