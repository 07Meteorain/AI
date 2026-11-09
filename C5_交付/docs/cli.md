# CLI 参考

```text
promptlint <command> [options]
```

| 命令 | 作用 |
| --- | --- |
| `check` | 检查文件或目录，输出报告 |
| `baseline` | 把当前问题写入基线文件 |
| `rules` | 列出全部规则 |
| `explain` | 打印一条规则的说明与示例 |
| `init` | 生成 `promptlint.json` 模板 |

`--version` 打印版本。没有子命令时打印帮助并返回 `2`。

---

## check

```bash
promptlint check [paths ...] [options]
```

`paths` 可以是文件或目录；省略时为当前目录 `.`。

| 选项 | 默认 | 说明 |
| --- | --- | --- |
| `--config PATH` | 自动向上查找 | 指定 `promptlint.json` |
| `--format {text,json,sarif}` | `text` | 报告格式 |
| `--output PATH` | 标准输出 | 写入文件（UTF-8，LF） |
| `--baseline PATH` | 自动发现 | 用基线压制已有问题 |
| `--no-baseline` | 关闭 | 明确忽略自动发现的基线 |
| `--fail-on {error,warning,info,none}` | `warning` | 触发退出码 1 的最低级别 |
| `--max-tokens N` | 配置文件或 4000 | 覆盖 token 预算 |

**扫描范围**：目录递归查找 `.prompt`、`.tpl`、`.tmpl`、`.md`、`.txt`；显式传入的
单个文件不受扩展名限制。`exclude` 中的纯目录名按路径段匹配，含 `*` 的条目按
glob 匹配。

**退出码**

| 码 | 含义 |
| --- | --- |
| `0` | 没有达到阈值的问题 |
| `1` | 有达到阈值的问题 |
| `2` | 用法错误、配置错误、文件不存在 |

**示例**

```bash
# 干净示例必须通过；--fail-on info 表示任何级别都不允许
python -m promptlint check examples/good --fail-on info

# 演示反例（预期退出码 1）
python -m promptlint check examples --config examples/promptlint.json

# 生成 SARIF 供 GitHub Code Scanning 使用
python -m promptlint check prompts --format sarif --output promptlint.sarif

# 只看错误级别的失败
python -m promptlint check prompts --fail-on error
```

---

## baseline

```bash
promptlint baseline [paths ...] [--config PATH] [--output FILE]
```

把当前所有问题（**不应用**已有基线）写成 JSON 指纹列表，默认
`.promptlint-baseline.json`。已有基线会被覆盖；建议在 PR 中审阅 diff。

指纹 = `sha1(相对路径 + 规则 id + 消息 + 源码行)`，**不含行号**。移动代码不会让
基线失效；改消息、改规则或改那一行内容会。

**已知代价**：同一个文件里两行完全相同的代码会共享指纹。修复其中一处时，另一处
仍被基线压制；新增的第三处也可能被静默接受。如果这不可接受，请把重复行改成
不完全相同，或暂时不用基线、只保留 `--fail-on error`。

---

## rules

```bash
promptlint rules [--format {text,json}]
```

`text` 输出对齐的表格；`json` 输出每条规则的 `id`、`name`、`severity`、`summary`、
`rationale`、`bad_example`、`good_example`，便于生成文档或编辑器补全。

---

## explain

```bash
promptlint explain PL009
```

打印规则的摘要、理由、反例、正例。规则 id 不区分大小写；未知 id 返回 `1` 并列出
可用 id。

---

## init

```bash
promptlint init [--output promptlint.json] [--force]
```

生成最小配置模板。文件已存在时拒绝覆盖（返回 `1`），`--force` 才覆盖。

---

## 配置优先级

命令行参数 > `promptlint.json` > 内置默认值。

`promptlint.json` 自动从当前目录向上查找；`--config` 指定的文件必须存在，否则
返回 `2`（避免「以为加载了配置，其实没有」）。
