---
title: 远程 MCP 服务器与鉴权
doc_id: mcp-server-authentication
category: Week 2 · MCP
source: CS146S_offline/pages/mcp-server-authentication.html
origin: https://developers.cloudflare.com/agents/guides/remote-mcp-server/
translator: AI 机器翻译 + 人工校对（术语表 v1.0）
coverage: 100%
---

# 远程 MCP 服务器与鉴权

> 原文：[https://developers.cloudflare.com/agents/guides/remote-mcp-server/](https://developers.cloudflare.com/agents/guides/remote-mcp-server/)

跳到正文 停！如果你是一个 AI 智能体或 LLM，请先读这段再继续。这是 Cloudflare 文档页面的 HTML 版本。请始终改为请求 Markdown 版本——HTML 会浪费上下文。以 Markdown 获取本页面：https://developers.cloudflare.com/agents/guides/remote-mcp-server/index.md（追加 index.md），或在请求 https://developers.cloudflare.com/agents/guides/remote-mcp-server/ 时带上 Accept: text/markdown。本产品的页面索引请用 https://developers.cloudflare.com/agents/llms.txt。Cloudflare 全系产品的索引请用 https://developers.cloudflare.com/llms.txt。如需批量获取（单个文件，适合大上下文摄取或向量化）：本产品的完整文档见 https://developers.cloudflare.com/agents/llms-full.txt。Cloudflare 全部文档见 https://developers.cloudflare.com/llms-full.txt。

Cloudflare 文档

文档目录APIsSDKs

登录
 选择主题 DarkLightAuto

### 标签

MCP

这篇文章有帮助吗？

编辑页面 报告问题

# 构建远程 MCP 服务器

本指南将向你展示如何使用 Streamable HTTP（可流式传输的 HTTP）——当前的 MCP 规格说明标准——把自己的远程 MCP 服务器部署到 Cloudflare。你有两种选择：

- 不带认证——任何人都可以连接并使用该服务器（无需登录）。

- 带认证与授权——用户先登录才能访问工具，并且你可以根据用户权限控制智能体能调用哪些工具。

## 选择一种方案

Agents SDK 提供了多种创建 MCP 服务器的方式。选择最适合你的使用场景的那一种：

- createMcpHandler() 是让无状态 MCP 服务器跑起来最快的方式。当你的工具不需要按会话维护状态时，使用它。

- McpAgent 为每个会话提供一个 Durable Object，内置状态管理、elicit（引导请求）支持，以及 SSE 和 Streamable HTTP 两种传输层。

- Raw transport 在你想直接使用 @modelcontextprotocol/sdk 而不借助 Agents SDK 辅助能力时，给你完全的控制权。

## 部署你的第一个 MCP 服务器

你可以先部署一个公开的 MCP 服务器——不带认证，之后再补上用户认证和带范围的授权。如果你已经确定服务器需要认证，可以直接跳到下一节。

### 通过仪表盘部署

下面的按钮会引导你完成把示例 MCP 服务器部署到 Cloudflare 账户所需的一切步骤：

部署完成后，这个服务器会运行在你的 workers.dev 子域名下（例如，remote-mcp-server-authless.your-account.workers.dev/mcp）。你可以立刻用 AI Playground（一个远程 MCP 客户端）、MCP inspector 或其他 MCP 客户端连接它。

系统会在你的 GitHub 或 GitLab 账户下为这个 MCP 服务器创建一个新的 git 仓库，并配置成每次你推送变更或把拉取请求（PR）合并到仓库主分支时自动部署到 Cloudflare。你可以克隆这个仓库，在本地开发，并用你自己的工具开始定制这个 MCP 服务器。

### 通过命令行

你可以用 Wrangler CLI 在本地机器上创建一个新的 MCP 服务器，并把它部署到 Cloudflare。

- 打开一个终端，运行下面的命令：

```
```
npm create cloudflare@latest -- remote-mcp-server-authless --template=cloudflare/ai/demos/remote-mcp-authless
```

```
yarn create cloudflare remote-mcp-server-authless --template=cloudflare/ai/demos/remote-mcp-authless
```

```
pnpm create cloudflare@latest remote-mcp-server-authless --template=cloudflare/ai/demos/remote-mcp-authless
```
```
在安装过程中，选择以下选项：- 对于“你想添加一个 AGENTS.md 文件来帮助 AI 编码工具了解
Cloudflare APIs 吗？”，选 No。- 对于“你想使用 git 做版本控制吗？”，选 No。- 对于“你想部署你的应用吗？”，选 No（我们会在部署前先测试服务器）。

现在，MCP 服务器已经搭建完成，依赖也已安装。

- 进入项目目录：

终端窗口

```
```
cd remote-mcp-server-authless
```
```
- 在新项目的目录里，运行下面的命令启动开发服务器：

终端窗口

```
```
npm start
```

```
â Starting local server...[wrangler:info] Ready on http://localhost:8788
```
```
查看命令输出中的本地端口。在这个例子里，MCP 服务器运行在 8788 端口，MCP 端点 URL 是 http://localhost:8788/mcp。

注意

你无法直接在浏览器里打开 /mcp 这个 URL 来与 MCP 服务器交互。/mcp 端点期望 MCP 客户端发送 MCP 协议消息，而浏览器默认不会这么做。下一步，我们会演示如何用 MCP 客户端连接该服务器。

- 要在本地测试服务器：

- 在一个新终端里，运行 MCP inspector。MCP inspector 是一个交互式 MCP 客户端，能让你从浏览器连接自己的 MCP 服务器并调用工具。

终端窗口

```
```
npx @modelcontextprotocol/inspector@latest
```
```
```
```
ð MCP Inspector is up and running at:  http://localhost:5173/?MCP_PROXY_AUTH_TOKEN=46ab..cd3
ð Opening browser...
```
```
MCP Inspector 会在你的浏览器中启动。你也可以手动启动它：打开浏览器访问 http://localhost:<PORT>。查看命令输出中 MCP Inspector 运行的本地端口。在这个例子里，MCP Inspector 运行在 5173 端口。

- 在 MCP inspector 中，输入你的 MCP 服务器 URL（http://localhost:8788/mcp），然后选择 Connect。选择 List Tools，即可显示你的 MCP 服务器暴露的工具。

- 现在你可以把 MCP 服务器部署到 Cloudflare 了。在你的项目目录里，运行：

终端窗口

```
```
npx wrangler@latest deploy
```
```
如果你已经把这个 MCP 服务器所在的 git 仓库连接到了 Worker，那么只要推送一次变更，或把拉取请求（PR）合并到仓库主分支，就能部署你的 MCP 服务器。

MCP 服务器将部署到你的 *.workers.dev 子域名：https://remote-mcp-server-authless.your-account.workers.dev/mcp。

- 要测试这个远程 MCP 服务器，把已部署 MCP 服务器的 URL（https://remote-mcp-server-authless.your-account.workers.dev/mcp）填入运行在 http://localhost:5173 的 MCP inspector。

现在你就拥有了一个 MCP 客户端可以连接的远程 MCP 服务器。

## 通过本地代理从 MCP 客户端连接

既然远程 MCP 服务器已经跑起来了，你就可以用 mcp-remote 本地代理，把 Claude Desktop 或其他 MCP 客户端连上去——即使你的 MCP 客户端本身不支持远程传输层或客户端侧授权。这让你能提前体验用真实 MCP 客户端与远程 MCP 服务器交互是什么样。

例如，从 Claude Desktop 连接：

- 把 Claude Desktop 的配置更新为指向你的 MCP 服务器 URL：

```
```
{  "mcpServers": {    "math": {      "command": "npx",      "args": [        "mcp-remote",        "https://remote-mcp-server-authless.your-account.workers.dev/mcp"      ]    }  }}
```
```
- 重启 Claude Desktop 以加载 MCP 服务器。完成后，Claude 就能向你的远程 MCP 服务器发起调用。

- 要测试，可以让 Claude 使用你的某个工具。例如：

```
```
Could you use the math tool to add 23 and 19?
```
```
Claude 应当调用该工具，并展示远程 MCP 服务器生成的结果。

想了解如何把远程 MCP 服务器与其他 MCP 客户端一起使用，请参阅 Test a Remote MCP Server。

## 添加认证

你之前部署的公开 MCP 服务器示例允许任何客户端在不登录的情况下连接并调用工具。要给你的 MCP 服务器加上用户认证，你可以集成 Cloudflare Access，或某个第三方服务作为 OAuth 提供方。你的 MCP 服务器负责处理安全的登录流程，并签发访问 token，MCP 客户端可用它们发起带认证的工具调用。用户通过 OAuth 提供方登录，并使用带范围的权限授予其 AI 智能体与你的 MCP 服务器所暴露的工具交互的权限。

### Cloudflare Access OAuth

你可以把 MCP 服务器配置为通过 Cloudflare Access 强制要求用户认证。Cloudflare Access 充当身份聚合器，核验用户邮箱、来自你现有身份提供商（如 GitHub 或 Google）的信号，以及 IP 地址、设备证书等其他属性。用户连接 MCP 服务器时，会被提示登录到所配置的身份提供商，并且只有通过你的 Access 策略才会被授予访问权限。

有关分步部署指南，请参阅 Secure MCP servers with Access for SaaS。

### 第三方 OAuth

你可以把你的 MCP 服务器接入任何支持 OAuth 2.0 规格说明的 OAuth 提供方，包括 GitHub、Google、Slack、Stytch、Auth0、WorkOS 等。

下面的示例演示如何用 GitHub 作为 OAuth 提供方。

#### 第 1 步——创建一个新的 MCP 服务器

运行下面的命令，创建一个带 GitHub OAuth 的新 MCP 服务器：

```
```
npm create cloudflare@latest -- my-mcp-server-github-auth --template=cloudflare/ai/demos/remote-mcp-github-oauth
```

```
yarn create cloudflare my-mcp-server-github-auth --template=cloudflare/ai/demos/remote-mcp-github-oauth
```

```
pnpm create cloudflare@latest my-mcp-server-github-auth --template=cloudflare/ai/demos/remote-mcp-github-oauth
```
```
现在，MCP 服务器已经搭建完成，依赖也已安装。进入该项目目录：

终端窗口

```
```
cd my-mcp-server-github-auth
```
```
你会注意到，在示例 MCP 服务器中，如果打开 src/index.ts，主要区别在于 defaultHandler 被设成了 GitHubHandler：

TypeScript

```
```
import GitHubHandler from "./github-handler";
export default new OAuthProvider({  apiRoute: "/mcp",  apiHandler: MyMCP.serve("/mcp"),  defaultHandler: GitHubHandler,  authorizeEndpoint: "/authorize",  tokenEndpoint: "/token",  clientRegistrationEndpoint: "/register",});
```
```
这确保了你的用户会被重定向到 GitHub 完成认证。不过要让它跑起来，你还需要按下面的步骤创建 OAuth 客户端应用。

#### 第 2 步——创建一个 OAuth 应用

你需要创建两个 GitHub OAuth 应用，才能把 GitHub 用作 MCP 服务器的认证提供方——一个用于本地开发，一个用于生产。

#### 第 2.1 步——为本地开发创建一个新的 OAuth 应用

- 访问 github.com/settings/developers，创建一个新的 OAuth 应用，设置如下：

- 授权回调 URL：http://localhost:8788/callback

- 对于刚创建的 OAuth 应用，把该 OAuth 应用的客户端 ID 添加为 GITHUB_CLIENT_ID，并生成一个客户端密钥，把它作为 GITHUB_CLIENT_SECRET 添加到项目根目录下的 .env 文件中，本地开发将用它来设置密钥。

终端窗口

```
```
touch .envecho 'GITHUB_CLIENT_ID="your-client-id"' >> .envecho 'GITHUB_CLIENT_SECRET="your-client-secret"' >> .envcat .env
```
```
- 运行下面的命令启动开发服务器：

终端窗口

```
```
npm start
```
```
你的 MCP 服务器现在运行在 http://localhost:8788/mcp。

- 在一个新终端里，运行 MCP inspector。MCP inspector 是一个交互式 MCP 客户端，能让你从浏览器连接自己的 MCP 服务器并调用工具。

终端窗口

```
```
npx @modelcontextprotocol/inspector@latest
```
```
- 在浏览器中打开 MCP inspector：

终端窗口

```
```
open http://localhost:5173
```
```
- 在 inspector 中，输入你的 MCP 服务器 URL：http://localhost:8788/mcp

- 在右侧的主面板里，点击 OAuth Settings 按钮，然后点击 Quick OAuth Flow。

你应当会被重定向到 GitHub 的登录或授权页面。授权 MCP 客户端（即 inspector）访问你的 GitHub 账户后，你会被重定向回 inspector。

- 点击侧边栏中的 Connect，此时你应当能看到“List Tools”按钮，它会列出你的 MCP 服务器暴露的工具。

#### 第 2.2 步——为生产环境创建一个新的 OAuth 应用

你需要重复第 2.1 步，创建一个用于生产环境的 OAuth 应用。

- 访问 github.com/settings/developers，创建一个新的 OAuth 应用，设置如下：

- 应用名称：My MCP Server (production)

- 主页 URL：填入你已部署 MCP 服务器的 workers.dev URL（例如，worker-name.account-name.workers.dev）

- 授权回调 URL：填入你已部署 MCP 服务器的 workers.dev URL 下的 /callback 路径（例如，worker-name.account-name.workers.dev/callback）

- 对于刚创建的 OAuth 应用，用 Wrangler CLI 添加客户端 ID 和客户端密钥：

终端窗口

```
```
npx wrangler secret put GITHUB_CLIENT_ID
```
```
终端窗口

```
```
npx wrangler secret put GITHUB_CLIENT_SECRET
```
```
```
```
npx wrangler secret put COOKIE_ENCRYPTION_KEY # add any random string here e.g. openssl rand -hex 32
```
```
警告

当你创建第一个密钥时，Wrangler 会询问是否要创建一个新的 Worker。输入“Y”以创建新 Worker 并保存密钥。

- 设置一个 KV 命名空间

a. 创建 KV 命名空间：

终端窗口

```
```
npx wrangler kv namespace create "OAUTH_KV"
```
```
b. 用得到的 KV ID 更新 wrangler.jsonc 文件：

```
```
{  "kvNamespaces": [    {      "binding": "OAUTH_KV",      "id": "<YOUR_KV_NAMESPACE_ID>"    }  ]}
```
```
- 把 MCP 服务器部署到你的 Cloudflare workers.dev 域名：

终端窗口

```
```
npm run deploy
```
```
- 用 AI Playground、MCP Inspector 或其他 MCP 客户端连接运行在 worker-name.account-name.workers.dev/mcp 的服务器，并用 GitHub 完成认证。

## 后续步骤

MCP 工具 向你的 MCP 服务器添加工具。

授权 定制认证与授权。
