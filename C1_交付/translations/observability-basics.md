---
title: 可观测性基础
doc_id: observability-basics
category: Week 9 · SRE 与可观测性
source: CS146S_offline/pages/observability-basics.html
origin: https://last9.io/blog/traces-spans-observability-basics/
translator: AI 机器翻译 + 人工校对（术语表 v1.0）
coverage: 100%
---

# 可观测性基础

> 原文：[https://last9.io/blog/traces-spans-observability-basics/](https://last9.io/blog/traces-spans-observability-basics/)

我们使用 Cookie 来定制您的 Last9 使用体验。
 您的偏好是什么？

Last9
预约演示
 打开菜单

Last9
预约演示
 关闭菜单

产品　发现　探索

日志　追踪　指标　控制平面　AI　RUM　告警

资源　指南　博客　活动　更新日志

更多　客户　文档　定价

Last9

2025 年 4 月 23 日

# 追踪与跨度：你应该掌握的可观测性基础

了解追踪和跨度如何让你看清分布式系统的内部——从而更快排查问题，构建更可靠的软件。

Anjali Udasi

#### 目录

在现代软件架构中，应用不只是变得更大——它们也变得更分布式。随着微服务、无服务器函数和容器横跨多种环境运行，弄清系统内部发生了什么，就像要在暴风雨中追踪一滴雨。

追踪和跨度正是在这里派上用场。这些可观测性工具不只是流行词——它们是帮你理清复杂分布式系统的秘密武器。下面我们讲清楚追踪和跨度是什么、为什么重要，以及你如何用它们更快排查问题、构建更可靠的系统。

## 理解追踪与跨度：核心概念

追踪捕获一个请求在你分布式系统中穿行的旅程。把一条追踪想成一个请求从头到尾的完整故事——从用户点击按钮，到用户看到结果。

跨度（span）是追踪的基本组成单元。每个跨度代表这段旅程中的一项工作——比如一次数据库查询、一次 API 调用或一次函数执行。跨度之间可以嵌套，用来展示操作之间的父子关系。

用简单的话说，它们的关系是：

- 一条追踪包含多个跨度

- 每个跨度代表一个操作

- 跨度带有时间数据和元数据

- 跨度可以嵌套，以展示操作之间如何相互关联

```
```
Trace
├── Span (API Gateway)
│   ├── Span (Auth Service)
│   └── Span (User Service)
│       └── Span (Database Query)
└── Span (Response Formatting)
```
```
💡

如果你好奇追踪和跨度与指标、日志、事件之间的关系，这篇文章对这四者做了完整梳理。

## 追踪和跨度给 DevOps 从业者带来的好处

你正在运行一个包含几十个微服务的复杂系统。突然，用户反馈结账流程很慢。没有追踪，你就得逐个检查每个服务，浪费宝贵的时间。

有了追踪和跨度，你可以：

- 立刻找到瓶颈：准确看清是哪个服务或哪个函数耗时过长

- 跨服务边界调试：跟随请求在服务之间跳转

- 理解依赖关系：可视化你的服务之间如何连接和相互依赖

- 提升性能：精准定位并修复慢操作

- 缩短平均恢复时间（MTTR）：问题出现时更快触达根因

## 追踪和跨度的技术实现

下面我们进入正题，看看追踪在分布式系统中具体是怎么工作的。

### 追踪上下文与传播

要让追踪能够跨服务边界工作，每个服务都需要知道自己处理的是同一个请求的一部分。这靠的是上下文传播——在服务之间传递追踪 ID 和跨度 ID。

当一个请求首次进入你的系统时，它会被分配一个唯一的追踪 ID。当请求在服务之间流转时，这个 ID 会随之传递（通常放在 HTTP 头里）。随后每个服务创建自己的跨度，但把它们都关联到同一条追踪上。

### 跨度属性与事件

跨度不只是时间戳——它们还承载着丰富的数据：

- 名称（Name）：这个跨度代表什么操作

- 属性（Attributes）：自定义的键值对（比如 user_id 或 cart_size）

- 事件（Events）：跨度内值得注意的偶发事件

### 采样策略

对所有内容都做追踪会产生巨量数据。因此大多数系统会使用采样——只采集一定比例的追踪。比较聪明的采样策略包括：

- 头部采样（Head-based sampling）：在请求开始时决定是否采样

- 尾部采样（Tail-based sampling）：在请求结束后再决定（更适合捕捉错误）

- 优先级采样：始终追踪重要操作，日常操作则采样

💡

如果你想弄清可观测性、遥测和监控之间的区别，看看这篇有用的文章：Observability vs Telemetry vs Monitoring。

## 追踪实施指南：工具与框架

准备给你的系统加上追踪了？下面是你需要的东西：

### OpenTelemetry：行业标准

OpenTelemetry 已经成为实现追踪和跨度的首选框架。它提供：

- 覆盖所有主流编程语言的库

- 针对流行框架的自动埋点

- 一致的采集与导出数据的方式

### 追踪工具箱

有几个工具可以帮助你采集、存储和可视化追踪数据：

如果你在找一款符合预算的可观测性方案，Last9 值得看看。它按摄入的事件量计费，费用可预测。而且我们的平台可以大规模处理高基数数据，并与 OpenTelemetry 和 Prometheus 集成，把你的指标、日志和追踪汇聚到一处。

### 在代码中实现追踪

下面是一个简化示例，展示如何在 Node.js 应用中使用 OpenTelemetry 创建跨度：

```
```
// Initialize the OpenTelemetry SDK (once in your app)
const { NodeTracerProvider } = require('@opentelemetry/sdk-trace-node');
const { SimpleSpanProcessor } = require('@opentelemetry/sdk-trace-base');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');

const provider = new NodeTracerProvider();
const exporter = new OTLPTraceExporter({
  url: 'http://localhost:4318/v1/traces',
});
provider.addSpanProcessor(new SimpleSpanProcessor(exporter));
provider.register();

// Get a tracer
const { trace } = require('@opentelemetry/api');
const tracer = trace.getTracer('my-service');

// Create spans in your code
async function processOrder(orderId) {
  const span = tracer.startSpan('process-order');
  
  // Add attributes to the span
  span.setAttribute('order.id', orderId);
  span.setAttribute('customer.type', 'premium');
  
  try {
    // Do work...
    
    // Create a child span
    const dbSpan = tracer.startSpan('database-query', {
      parent: span,
    });
    
    try {
      // Run database query...
      dbSpan.end();
    } catch (error) {
      dbSpan.setStatus({ code: SpanStatusCode.ERROR });
      dbSpan.recordException(error);
      dbSpan.end();
      throw error;
    }
    
    span.end();
  } catch (error) {
    span.setStatus({ code: SpanStatusCode.ERROR });
    span.recordException(error);
    span.end();
    throw error;
  }
}
```
```
💡

想知道 OpenTelemetry 与传统 APM 工具相比表现如何？这篇文章梳理了关键差异：OpenTelemetry vs Traditional APM Tools。

## 进阶追踪技巧

基础追踪落地之后，下面这些进阶技巧能让你的可观测性再上一个台阶。

### 分布式上下文管理

在复杂系统中，你需要管理的不只是追踪 ID。W3C Trace Context 规范为以下内容提供了标准：

- traceparent：包含追踪 ID 和父跨度 ID

- tracestate：允许厂商添加自定义上下文数据

使用这些头可以确保你的追踪在不同服务和厂商之间都能正常工作。

### 追踪、指标与日志之间的关联

可观测性的真正力量来自把不同的信号连接起来：

- 示例追踪（Exemplar traces）：把指标与产生它们的追踪关联起来

- 日志中的追踪 ID：在日志消息中加入追踪 ID 以便交叉引用

- 自定义属性：在所有遥测类型中使用一致的属性

### 错误处理与异常追踪

发生异常时，跨度可以提供关键的上下文：

- 记录带堆栈信息的异常

- 给跨度添加事件，展示错误的演进过程

- 创建 baggage 项，把错误上下文带过服务边界

💡

想更深入地了解如何提前发现问题、提升系统可靠性，看看这篇关于主动监控的文章：Proactive Monitoring。

## 真实场景中的追踪模式与反模式

### 有效的追踪模式

有意义的跨度名称：采用一致的命名约定，比如 service_name/operation
合适的粒度：为重要操作创建跨度，而不是每次函数调用都创建
正确的上下文传播：确保追踪上下文在所有通信渠道中都能流通
有用的属性：添加有助于排查的属性，比如用户 ID 或功能开关
性能意识：注意过度创建跨度带来的开销

### 应避免的追踪反模式

过度埋点：创建过多跨度会引发性能问题
上下文缺失：上下文传播失败会让追踪在服务边界处断裂
命名不一致：使用不同的命名标准会让追踪难以解读
数据过多：把大段负载放进跨度会让追踪后端不堪重负
忽略第三方服务：外部调用缺失跨度会造成盲区

💡

深入了解可观测性在 LLM 性能与可靠性方面如何发挥关键作用：LLM Observability。

## 追踪和跨度的业务价值：超越技术收益

追踪不只是用来排查问题的——它们同样能带来业务洞察：

- 端到端跟踪关键用户旅程

- 度量关键业务操作的性能

- 基于追踪数据设定 SLO（服务等级目标）

- 以真实用户视角量化性能问题的成本

- 通过给跨度添加相关属性来构建业务上下文

当你能够展示技术改进如何影响用户体验和业务指标时，你就打通了 DevOps 与业务相关方之间的隔阂。

## 结论

追踪和跨度给了你对分布式系统的 X 光视野。它们揭示服务之间隐藏的关联，精准定位性能瓶颈，并大幅加快调试速度。

随着系统愈发复杂，这类可观测性不是奢侈品——而是必需品。

💡

如果你想继续深入讨论分布式追踪和可观测性，欢迎加入我们的 Discord 社区，DevOps 从业者在那里分享经验和最佳实践！

## 常见问题

### 追踪和日志有什么区别？

日志捕获离散的单个事件，而追踪展示跨服务的操作之间的关系。日志告诉你发生了什么；追踪告诉你它是怎么发生的。

### 加入追踪会让我的应用变慢吗？

现代追踪库带来的开销极小——配置得当时通常对性能的影响低于 3%。配合采样，你还能进一步降低这一影响。

### 我需要修改所有代码才能加入追踪吗？

不一定。许多框架都提供自动埋点，只需很少的代码改动就能加入追踪。OpenTelemetry 为大多数语言的主流框架提供了自动埋点。

### 分布式追踪会产生多少数据？

差异极大，取决于流量、采样率和跨度细节。对繁忙的系统，要做好每天从几 GB 到几 TB 的准备。正因如此，选对可观测性平台对成本控制很重要。

### 追踪对安全与合规有帮助吗？

有！追踪为请求在系统中的流转建立了审计轨迹。加上合适的属性，你就能追踪哪些用户或服务在何时访问了哪些数据。

### 追踪和跨度与其他可观测性信号是什么关系？

追踪是指标和日志的补充。指标从宏观层面展示系统健康状况，日志提供详细事件，追踪则把点连接起来，展示跨服务的请求流向。

主题

可观测性　监控

关于作者

Anjali Udasi

致力于让技术不那么吓人。I

#### 目录

## 免费开始观测。无锁定。

预约演示

OPENTELEMETRY • PROMETHEUS 只需更新你的配置。几秒钟内就能在 Last9 上看到数据。

DATADOG • NEW RELIC • OTHERS 我们都覆盖到了。一键迁移你的仪表盘和告警。

基于开放标准构建 100+ 集成项。原生支持 OTel，与你现有的技术栈协同工作。

4.8/5

G2 用户评价

Gartner Cool Vendor 2025

高绩效

最佳易用性

最高用户采用率
