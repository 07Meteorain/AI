# 架构说明

## 目标与非目标

**目标**：在零依赖、离线、确定性的前提下，把 prompt 模板里「机器可以确定判断」的
问题找出来，并给出可点击的位置、可解释的理由、可在 CI 落地的报告。

**非目标**：评估 prompt 的效果、自动改写 prompt、调用模型、替代人工评审。
`promptlint` 是一个 linter，不是 evaluator。

## 数据流

```text
CLI args
   │
   ▼
config.py ──► Config (rules 覆盖 / max_tokens / exclude)
   │
   ▼
engine.collect_files ──► [Path]（扩展名、exclude、去重、排序）
   │
   ▼
parser.parse_prompt ──► ParsedPrompt
   │                     ├─ front matter (vars)
   │                     ├─ placeholders（位置、合法性）
   │                     ├─ fenced / inline-code 掩码
   │                     └─ ParseIssue（PL004 / PL012）
   ▼
rules/*.Rule.check(parsed, source, config) ──► [Finding]
   │
   ▼
engine.lint_source ──► 按 (line, column, rule) 排序 + 严重级别覆盖
   │
   ▼
baseline.apply_baseline ──► 过滤已接受的问题
   │
   ▼
report.text / report.json / sarif.build_sarif
```

## 模块职责

| 模块 | 职责 | 不做什么 |
| --- | --- | --- |
| `parser.py` | 把文本变成带位置的结构 | 不判断对错 |
| `rules/*.py` | 每条规则独立判断一类问题 | 不读文件、不打印 |
| `engine.py` | 文件发现、规则调度、排序、基线过滤 | 不定义规则 |
| `config.py` | 加载/校验/向上查找配置 | 不处理 CLI 参数 |
| `baseline.py` | 指纹、读写基线 | 不决定是否启用（CLI 决定） |
| `report.py` / `sarif.py` | 只负责序列化 | 不改变 Finding |
| `cli.py` | 参数、退出码、组合以上模块 | 不放业务逻辑 |

规则通过 `(ParsedPrompt, SourceFile, Config) -> Iterable[Finding]` 接口接入。它拿到
的是已解析的结构和原始行，因此可以同时做「结构判断」（PL002）和「文本判断」
（PL005 扫描全部行，包括代码围栏）。

## 关键设计决策

### 1. 手写解析器，而不是引入 PyYAML/Markdown 库

项目只需要 front matter 的 `vars` 列表、`{{name}}` 占位符、代码围栏三种结构。
引入库会把「零依赖」变成「三个依赖 + 一个解析器版本兼容问题」，而收益只是处理
我们明确不支持的复杂 YAML。取舍写在 `parser.py` 的注释与 `docs/rules.md` 的边界里。

### 2. 规则无副作用，报告只读

规则不写文件、不发网络请求、不修改 AST。这样：
- 测试可以直接对 `lint_text()` 断言，不需要 mock 文件系统；
- 同一输入永远同一输出，CI 不会因环境变化抖动；
- 未来做 LSP/编辑器插件时，规则可以原样复用。

### 3. 严重级别属于配置，不属于规则

规则只声明 `default_severity`。配置可以把任一条改成 `error`/`warning`/`info`/`off`。
这样团队可以按自己的风险模型收紧 PL007，而不必 fork 规则。

### 4. 指纹不含行号

基线指纹由「相对路径 + 规则 id + 消息 + 源码行」组成。行号是最容易变化的部分：
一次 import 排序就会让所有基线失效。代价是「同一行内容在两个位置出现」会共享指纹，
这对 linter 来说是可接受的（两处都被接受或都被报告）。

### 5. 掩码而不是隐藏

PL005/PL006 在消息里输出掩码后的值（`sk-l...2b9d`）。完全隐藏会让用户无法定位是
哪一条；完整输出会把密钥再复制一份到 CI 日志。掩码是折中，同时 README 明确写了
「发现即代表该值已经进入过工作区」。

## 性能

单文件解析是 O(字符数)；规则各自扫描一次，总计 O(规则数 × 文件大小)。唯一的
超线性操作是 PL009 的标签配对（对每个不可信占位符扫描一次标签区间），prompt 的
典型大小（< 100 KB）下可忽略。目录扫描不进入 `.git`、`node_modules` 等目录。

## 测试策略

`tests/` 有 81 项 `unittest`，分四层：

1. **解析器**：front matter、围栏、行内代码、位置偏移；
2. **规则**：每条规则的触发与不触发，包括掩码与边界；
3. **引擎/基线**：严重级别覆盖、排序、文件发现、指纹稳定性；
4. **CLI/SARIF**：退出码、三种格式、`init`/`baseline` 流程、SARIF 字段。

没有集成测试依赖网络或模型；CI 在 Python 3.9–3.13 上跑同一套命令。

## 扩展点

新增一条规则：

1. 在 `promptlint/rules/` 选一个分组（structure/safety/quality/meta）；
2. 继承 `Rule`，分配下一个未使用的 `PL0xx`；
3. 写 `check()`，用 `make_finding()` 生成带位置的 Finding；
4. 在 `rules/__init__.py` 注册；
5. 补测试与 `docs/rules.md`；
6. 跑 `python -m unittest discover -s tests`。

详细清单见 `CONTRIBUTING.md`。
