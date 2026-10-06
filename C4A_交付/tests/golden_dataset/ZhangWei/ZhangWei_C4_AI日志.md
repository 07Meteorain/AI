# AI 使用日志：PR 描述生成器

## 使用的 AI 工具

| 轮次 | 工具 | 用途 |
|---|---|---|
| 1 | Claude Code | 设计 CLI 参数与整体结构 |
| 2 | Claude Code | 实现 git log / diff 解析 |
| 3 | ChatGPT | 评审错误处理分支 |
| 4 | Claude Code | 补齐测试用例 |
| 5 | Claude Code | 修复 Windows 换行符问题 |

## 迭代次数

共 **5 轮**迭代，其中第 3 轮是主动发现 bug 后追加的。

## 关键 prompt 与修正

**第 1 轮 prompt**："写一个 Python 脚本，读取 git commit 生成 PR 描述"
→ 问题：输出太笼统，没有分支对比逻辑。

**第 2 轮 prompt**："增加 --base 参数，用 `git diff base...HEAD --stat` 获取变更统计，
并且要处理仓库为空的情况"
→ 修正后明确了基准分支概念。

**第 3 轮（自查发现）**：我手动测试空仓库场景，发现脚本报了未捕获异常。
→ 要求 AI 补充 `git rev-parse HEAD` 预检。

**第 4 轮 prompt**："为 collect_commits / collect_diff 写 unittest，用临时 git 仓库做 fixture"
→ 产出 3 个测试用例，全部通过。

**第 5 轮**：Windows 上 `subprocess` 文本模式自动转换换行导致 diff 多了空行，
让 AI 改成 `newline=""` 显式处理。

## 我做了什么

- 定义了 CLI 接口（参数命名、默认值）
- 决定了 diff 截断阈值为 2000 行
- 设计了 3 个测试用例的场景
- 发现并定位了 Windows 换行符这个只有实测才会暴露的问题