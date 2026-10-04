---
title: API 不是好的 MCP 工具（APIs Don't Make Good MCP Tools）
doc_id: mcp-food-for-thought
category: Week 2 · MCP
source: CS146S_offline/pages/mcp-food-for-thought.html
origin: https://www.reillywood.com/blog/apis-dont-make-good-mcp-tools/
translator: AI 机器翻译 + 人工校对（术语表 v1.0）
coverage: 100%
---

# API 不是好的 MCP 工具（APIs Don't Make Good MCP Tools）

> 原文：[https://www.reillywood.com/blog/apis-dont-make-good-mcp-tools/](https://www.reillywood.com/blog/apis-dont-make-good-mcp-tools/)

# Reilly Wood

## API 不是好的 MCP 工具

2025 年 8 月 5 日
 
 
 阅读约 4 分钟

Model Context Protocol (MCP) 眼下是个大热门。它已经成为让 LLM 用上别人写的工具的事实标准，而这些工具也正是让它们成为智能体的关键。但为新的 MCP 服务器编写工具并不容易，于是人们常常提议把现有 API 自动转换成 MCP 工具，通常会利用 OpenAPI 元数据（1、2）。

依我的经验，这事能做，但做不好。原因有几个：

## 智能体应付不了大量工具

众所周知，VS Code 有 128 个工具的硬上限——但很多模型远在达到这个数字之前，就已经在准确调用工具上力不从心了。此外，每个工具及其描述都要占用宝贵的上下文窗口空间。

大多数 Web API 在设计时并没有考虑这些约束！如果这些 API 是由代码调用的，那么某个产品领域里有个几十个 API 没什么问题；但如果把其中每个 API 都映射成一个 MCP 工具，效果可能就不太好了。

从零开始设计的 MCP 工具，通常比单个 Web API 灵活得多——一个工具往往能完成好几个独立 API 的工作。

## API 会迅速撑爆上下文窗口

设想一个 API，一次返回 100 条记录，每条记录又很宽（比如 50 个字段）。把这些结果原样发给智能体，会消耗大量 token；即便某个查询只需要少数字段，最终每个字段都会进上下文窗口。

API 通常按记录数分页，但记录的体积差异可能很大。一条记录里也许有个占 100,000 个 token 的大文本字段，另一条却只有 10 个。把这些 API 结果直接塞进智能体的上下文窗口是一场赌博：有时能奏效，有时就会把窗口撑爆。

数据格式同样可能成为问题。如今大多数 Web API 返回 JSON，但 JSON 是个非常浪费 token 的格式。看看这个：

```
```
[
  {
    "firstName": "Alice",
    "lastName": "Johnson",
    "age": 28
  },
  {
    "firstName": "Bob",
    "lastName": "Smith",
    "age": 35
  }
]
```
```
对比一下同样数据用 CSV 格式表示：

```
```
firstName,lastName,age
Alice,Johnson,28
Bob,Smith,35
```
```
CSV 数据要简洁得多——每条记录消耗的 token 只有一半。通常来说，CSV、TSV 或 YAML（用于嵌套数据）比 JSON 更合适。

这些问题没有哪个是无解的。你可以设想自动添加工具参数，让智能体能够投影字段；自动截断或摘要过大的结果；再自动把 JSON 结果转成 CSV（嵌套数据则转成 YAML）。但我见过的服务器大多一件都没做。

## API 无法充分发挥智能体的独特能力

API 返回结构化数据，供程序消费。这往往正是智能体从工具调用中想要的东西……但智能体还能处理其他更自由形式的指令。

比如，一个 ask_question 工具可以对某份文档做一次 RAG（检索增强生成）查询，然后以纯文本返回信息，用来支撑下一次工具调用——完全跳过结构化数据。

又或者，一次 search_cities 工具调用可以返回一份结构化的城市列表，外加下一步该调用什么的建议：

```
```
city_name,population,country,region
Tokyo,37194000,Japan,Asia
Delhi,32941000,India,Asia
Shanghai,28517000,China,Asia

Suggestion: To get more specific information (weather, attractions, demographics), try calling get_city_details with the city_name parameter.
```
```
这种分层与工具链式调用在 MCP 服务器里可以非常有效，而如果你只是把 API 自动转换成工具，就会彻底错过它。

## 如果智能体需要调用 API，它本来就可以直接调

如今像 Claude Code 这样的智能体，在编写并执行代码方面能力惊人，包括调用 Web API 的脚本。有些人甚至据此认为根本不需要 MCP！

我不同意这个结论，但我确实认为我们该顺势而为。智能体的沙箱能力正在快速改进，如果让智能体直接调用 API 既简单又安全，那我们不妨就这么做，去掉中间人。

## 结语

智能体与 API 的典型消费方有着本质区别。从现有 API 自动生成 MCP 工具是可行的，但这样做大概率效果不好。只有当工具是针对智能体独特的能力与局限设计时，智能体才能发挥得最好。

- 土地价值与可负担性

## 城市与代码

### 近期文章

### 💻 2025 年回顾

2025 年 12 月 28 日

### 💻 说到底，MCP 适合做什么？

2025 年 12 月 26 日

### 💻 工具调用既昂贵又有限

2025 年 9 月 18 日

### 💻 API 不是好的 MCP 工具

2025 年 8 月 5 日

### 🏗️ 土地价值与可负担性

2025 年 6 月 26 日

### 📝 我与邪恶 SEO 的遭遇

2025 年 6 月 16 日

查看更多文章

### 热门分类

软件
 
 
 
 
 42
 
 
 
 
 
 
 
 
 城市规划
 
 
 
 
 11
 
 
 
 
 
 
 
 
 近期
 
 
 
 
 10
 
 
 
 
 
 
 
 
 Rust
 
 
 
 
 9
 
 
 
 
 
 
 
 
 Web
 
 
 
 
 9
 
 
 
 
 
 
 
 
 数据库
 
 
 
 
 8
 
 
 
 
 
 
 
 
 LLM
 
 
 
 
 8
 
 
 
 
 
 
 
 
 Nushell
 
 
 
 
 7
 
 
 
 

 查看全部分类

#### 首页

#### 关于

#### 项目

### 近期文章

### 2025 年回顾

2025 年 12 月 28 日

### 说到底，MCP 适合做什么？

2025 年 12 月 26 日

### 工具调用既昂贵又有限

2025 年 9 月 18 日

### API 不是好的 MCP 工具

2025 年 8 月 5 日

### 土地价值与可负担性

2025 年 6 月 26 日

### 我与邪恶 SEO 的遭遇

2025 年 6 月 16 日
 
 
 
 
 
 查看更多文章
