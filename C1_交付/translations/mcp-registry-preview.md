---
title: MCP Registry 预览
doc_id: mcp-registry-preview
category: Week 2 · MCP
source: CS146S_offline/pages/mcp-registry-preview.html
origin: https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/
translator: AI 机器翻译 + 人工校对（术语表 v1.0）
coverage: 100%
---

# MCP Registry 预览

> 原文：[https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/)

跳到正文
首页 » 文章

# MCP 注册表隆重推出

MCP 注册表开启预览：一个用于发现公开可用 MCP 服务器的开放目录与 API。

2025 年 9 月 8 日 · 4 分钟 · David Soria Parra（首席维护者）、Adam Jones（注册表维护者）、Tadas Antanavicius（注册表维护者）、Toby Padilla（注册表维护者）、Theodora Chu（Anthropic 的 MCP 产品经理）

今天，我们正式推出 Model Context Protocol (MCP) 注册表——一个面向公开可用 MCP 服务器的开放目录与 API，旨在提升其可发现性与可实现性。通过标准化服务器的发布与发现方式，我们扩大了它们的触达范围，也让客户端更容易接入。

MCP 注册表现已开放预览。要开始使用：

- 按照《Adding Servers to the MCP Registry》指南添加你的服务器（面向服务器维护者）

- 按照《Accessing MCP Registry Data》指南访问服务器数据（面向客户端维护者）

# MCP 服务器的单一可信来源#

2025 年 3 月，我们曾表示希望为 MCP 生态建立一个中央注册表。今天我们宣布，https://registry.modelcontextprotocol.io 已作为官方 MCP 注册表上线。作为 MCP 项目的一部分，MCP 注册表及其上层 OpenAPI 规格说明均为开源——让所有人都能构建兼容的子注册表。

我们的目标是标准化服务器的发布与发现方式，提供一个主可信来源，供各类子注册表在其基础上继续构建。反过来，这也将扩大服务器的触达范围，并帮助客户端在整个 MCP 生态中更容易地找到服务器。

## 公有与私有子注册表#

在建设中央注册表的过程中，我们非常重要的一点是不去削弱社区和企业已经建成的各类注册表。MCP 注册表充当公开可用 MCP 服务器的主可信来源，而各组织可以按自定义标准创建子注册表。例如：

与每个 MCP 客户端相关联的、有自己主张的“MCP 市场”这类公有子注册表，可以自由扩充和增强它们从上游 MCP 注册表摄取的数据。每一种 MCP 终端用户角色都有不同需求，而如何以自己主张的方式服务好终端用户，取决于各个 MCP 客户端市场。

私有子注册表会存在于那些有严格隐私与安全要求的企业内部，而 MCP 注册表为这些企业提供了一个可供其构建的上游数据来源。至少，我们的目标是与这些私有实现共享 API schema，以便相关的 SDK 和工具能在整个生态中共享。

无论哪种情况，MCP 注册表都是起点——它是那个集中的位置，MCP 服务器维护者在这里发布并维护自己上报的信息，供下游消费者加工后交付给各自的终端用户。

## 由社区驱动的治理机制#

MCP 注册表是 MCP 官方项目，由注册表工作组维护，采用宽松许可。社区成员可以提交 issue，举报违反 MCP 治理准则的服务器——例如含有垃圾内容、恶意代码，或冒充合法服务的服务器。注册表维护者随后可以将这些条目加入拒绝列表，并追溯性地将其从公开访问中移除。

# 快速上手#

要开始使用：

- 按照《Adding Servers to the MCP Registry》指南添加你的服务器（面向服务器维护者）

- 按照《Accessing MCP Registry Data》指南访问服务器数据（面向客户端维护者）

MCP 注册表的这次预览，目的是让我们在正式可用之前改进用户体验，不提供数据持久性保证或其他形式的担保。我们建议 MCP 采用者密切关注开发进展，因为注册表在正式可用之前可能还会出现破坏性变更。

随着我们继续开发注册表，欢迎在 modelcontextprotocol/registry 这个 GitHub 仓库上反馈和贡献：讨论、issue 和拉取请求（PR）都非常欢迎。

# 感谢 MCP 社区#

MCP 注册表从一开始就是协作的成果，我们对更广泛开发者社区的热情与支持深怀感激。

2025 年 2 月，它以草根项目的形式起步：MCP 的创建者 David Soria Parra 和 Justin Spahr-Summers 请 PulseMCP 和 Goose 团队帮忙构建一个集中的社区注册表。来自 PulseMCP 的注册表维护者 Tadas Antanavicius 牵头完成了最初的工作，并与来自 Block 的 Alex Hancock 合作。他们很快又迎来了注册表维护者、GitHub 的 MCP 负责人 Toby Padilla；最近，来自 Anthropic 的 Adam Jones 也加入担任注册表维护者，推动项目走向今天的正式发布。MCP 注册表开发的首发公告列出了来自至少 9 家不同公司的 16 位贡献者。

还有许多人为把这个项目落到实处做出了关键贡献：来自 Stacklok 的 Radoslav Dimitrov、来自 GitHub 的 Avinash Sridhar、来自 VS Code 的 Connor Peet、来自 NuGet 的 Joel Verhagen、来自 Last9 的 Preeti Dewani、来自 Microsoft 的 Avish Porwal、Jonathan Hefner，以及许多提供代码评审与开发支持的 Anthropic 和 GitHub 员工。我们也感谢注册表贡献者日志上的每一个人，以及参与讨论和 issue 的每一个人。

我们由衷感谢每一位在这项基础性开源设施上投入的人。我们正在共同帮助全球的开发者和组织构建更可靠、更具上下文感知能力的 AI 应用。谨代表 MCP 社区，向大家道谢。
