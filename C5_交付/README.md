# promptlint

**Static analysis for LLM prompt templates — catch broken placeholders, leaked keys, missing output contracts, and injection surface before the prompt reaches a model.**

[![CI](https://github.com/07Meteorain/AI/actions/workflows/c5-promptlint.yml/badge.svg?branch=master)](https://github.com/07Meteorain/AI/actions/workflows/c5-promptlint.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![Dependencies: 0](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](pyproject.toml)

Prompt templates are code, but they rarely get the checks code gets. A typo in a
variable name ships a literal `{{customer_name}}` to the model; a key pasted for
a quick test ends up in a request log; a missing output format breaks the parser
three services downstream. `promptlint` is a small, deterministic linter that
catches those before the prompt leaves the repository.

- **Zero dependencies.** Python 3.9+ standard library only.
- **Offline and deterministic.** No tokenizer API, no network, same output every run.
- **12 rules**, each with a written rationale, a bad example, and a good example.
- **Text, JSON, and SARIF 2.1.0** output; exits non-zero for CI.
- **Baseline support** so an existing repository can adopt it without a wall of findings.

---

## 30 秒验证

```bash
git clone https://github.com/07Meteorain/AI.git
cd AI/C5_交付

# 好例子：0 个问题，退出码 0
python -m promptlint check examples/good --fail-on info

# 坏例子：12 个问题，退出码 1（输出见下）
python -m promptlint check examples --config examples/promptlint.json
```

不需要 `pip install` 任何东西。也可以用 `pip install -e .` 安装后直接调用
`promptlint` 命令（入口点在 `pyproject.toml`）。

## 输出长什么样

```text
examples/bad/bloated.prompt
  4:1  warning PL010  prompt is ~244 tokens (limit 120)

examples/bad/leaky.prompt
  4:1  warning PL007  no output format is specified (354 characters of instructions)
  6:17  error   PL005  possible OpenAI-style API key: sk-l...2b9d
  7:24  warning PL006  email address in prompt: a***@example.com
  8:25  warning PL006  mobile number in prompt: <redacted:11 chars>
  11:1  warning PL008  instruction repeats line 10: Always answer in English and cite sources.

examples/bad/malformed.prompt
  2:1  warning PL003  variable 'name' is declared but never used
  4:7  error   PL004  unbalanced placeholder delimiter '{{'
  5:13  error   PL004  empty placeholder '{{}}'
  5:23  error   PL004  invalid placeholder name '1st_topic'
  6:26  error   PL004  unbalanced placeholder delimiter '}}'

examples/bad/unsafe_context.prompt
  5:1  warning PL009  untrusted input '{{user_message}}' is not delimited

12 problems in 6 files (5 errors, 7 warnings, 0 info)
```

Secrets and PII are masked in the report; the full value is never echoed back
into a log. Every finding carries a rule id, file, line, and column, so it can be
clicked straight from a CI annotation.

## 12 条规则

| ID | 检查 | 默认 | 一句话理由 |
| --- | --- | --- | --- |
| PL001 | `prompt-empty` | error | 只有 front matter 或空白的文件不会给模型任何指令 |
| PL002 | `placeholder-undeclared` | error | 声明了 `vars` 却用了未声明的变量，通常是拼写错误 |
| PL003 | `placeholder-unused` | warning | 声明了却没用，说明模板在删改中漂移了 |
| PL004 | `placeholder-malformed` | error | `{{name`、`{{}}`、`{{1st}}` 不会渲染，会以字面量发给模型 |
| PL005 | `secret-literal` | error | key 粘进 prompt 后会随日志、issue、供应商面板一起扩散 |
| PL006 | `pii-literal` | warning | 真实邮箱/手机号/身份证号不应出现在模板里 |
| PL007 | `missing-output-contract` | warning | 不写输出格式，下游解析器迟早会崩 |
| PL008 | `duplicate-instruction` | warning | 重复指令通常是一次编辑后留下的旧副本 |
| PL009 | `untrusted-input-boundary` | warning | 用户输入和指令同通道，等于把「指令」交给数据 |
| PL010 | `prompt-too-long` | warning | 超预算的 prompt 更贵、更早撞上下文上限、更容易淹没重点 |
| PL011 | `invisible-character` | warning | 零宽字符可以藏指令，也会让两个「一样」的 prompt 行为不同 |
| PL012 | `front-matter-invalid` | error | front matter 解析失败时变量检查会静默失效 |

完整规则说明（含每个规则的反例、正例与已知误报）见 [`docs/rules.md`](docs/rules.md)；
也可以直接 `python -m promptlint explain PL009`。

## 配置

在项目根放一个 `promptlint.json`（`promptlint init` 生成模板）：

```json
{
  "rules": {
    "PL006": "warning",
    "PL010": "error",
    "PL008": "off"
  },
  "max_tokens": 4000,
  "exclude": [".git", "node_modules", ".venv", "venv", "__pycache__"]
}
```

- 严重级别可改为 `error` / `warning` / `info` / `off`；`off` 是显式关闭，不是静默忽略。
- `max_tokens` 只影响 PL010。
- 配置文件从当前目录向上查找；`--config` 可以指定。

## 基线：在存量仓库里落地

第一次接入一个成熟仓库，几十条历史问题会淹没新问题。基线把「已接受的问题」
记下来，只让新增问题失败：

```bash
python -m promptlint baseline prompts/          # 写入 .promptlint-baseline.json
python -m promptlint check prompts/ --baseline .promptlint-baseline.json
```

指纹由「相对路径 + 规则 id + 消息 + 源码行」计算，**不含行号**，所以挪动代码
不会让所有基线失效。基线文件应当提交到仓库，并在 PR 里人工审阅它的变化。

## CI 集成

```yaml
- name: Lint prompts
  run: python -m promptlint check prompts/ --fail-on error --format sarif --output promptlint.sarif

- name: Upload SARIF
  if: always()
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: promptlint.sarif
```

退出码：`0` 无达到阈值的问题，`1` 有问题，`2` 用法/配置/文件错误。
`--fail-on` 支持 `error`、`warning`、`info`、`none`。

仓库里的真实 CI 定义在
[`.github/workflows/c5-promptlint.yml`](../.github/workflows/c5-promptlint.yml)，
在 Python 3.9 / 3.10 / 3.11 / 3.12 / 3.13 上跑同一套测试。

## Python API

```python
from promptlint import Config, lint_text

findings = lint_text(
    "---\nvars: [topic]\n---\nWrite about {{topik}}.\n",
    config=Config(rules={"PL002": "error"}),
)
for finding in findings:
    print(finding.rule_id, finding.line, finding.message)
```

`lint_files(paths, config)` 返回 `[(SourceFile, [Finding])]`，供编辑器插件或
自定义报告器复用。`Finding` 是 dataclass，`as_dict()` 可直接序列化。

## 设计原则

1. **零依赖**。`git clone` + `python -m` 就能跑，陌生人不需要先解决环境。
2. **确定性**。同样的输入永远得到同样的输出，CI 不会因为模型或网络抖动变红。
3. **只报能解释的问题**。每条规则都有 rationale、反例、正例与已知边界。
4. **不自动改文件**。模板的语义判断留给作者，工具只负责把证据摆出来。
5. **基线优先于关规则**。接受一个问题要留下记录，而不是把规则静音。

## 已知边界（诚实声明）

- 不判断 prompt 的**效果**，只做静态检查；PL007/PL008/PL009 是启发式，存在误报。
- token 数是估算（约 ±30%），用于发现数量级问题，不用于精确计费。
- `PL009` 只识别 XML 标签包裹；用其他分隔符（如 Markdown 标题）需要自行评估。
- front matter 只支持 `key: value` 与 `vars` 列表，不支持完整 YAML。
- 目前不解析 Jinja2 的控制流（`{% if %}` 等），模板变量仍按 `{{name}}` 统计。

## 项目结构

```text
C5_交付/
├── promptlint/            # 包：解析器、规则、引擎、报告器、CLI
│   ├── rules/             # 12 条规则，按 structure / safety / quality / meta 分组
│   ├── parser.py          # front matter、占位符、代码围栏
│   ├── engine.py          # 文件发现、规则调度、基线过滤
│   ├── sarif.py           # SARIF 2.1.0
│   └── cli.py             # check / baseline / rules / explain / init
├── tests/                 # 81 项 unittest（零依赖）
├── examples/              # 可直接 lint 的正例与反例
├── demo/                  # 真实 CLI 输出（文本 / JSON / SARIF）
├── docs/                  # 规则参考、CLI 参考、架构说明
├── .github/               # issue/PR 模板与独立仓库用 CI
├── AI日志.md               # 10 轮 AI 协作记录（含真实故障与返工）
├── AAR复盘.md              # After Action Review
├── 拿来说明.md             # 关键决策：原始 prompt → AI 产出 → 人工调整
├── 提交说明.md             # 交付物对照与评审阅读顺序
└── CHANGELOG.md
```

## 开发

```bash
cd C5_交付
python -m unittest discover -s tests -v     # 81 tests, no dependencies
python -m promptlint check examples/good --fail-on info
```

新增规则见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。CI 会检查测试、干净示例与
SARIF 产物，因此「本地能跑」和「合并后能跑」是同一套命令。

## 版本

当前版本 **1.0.0**（见 [`CHANGELOG.md`](CHANGELOG.md)）。仓库标签 `c5-v1.0.0`
对应本次交付。

## 交付文档

| 文件 | 内容 |
| --- | --- |
| [`提交说明.md`](提交说明.md) | 挑战交付物对照表、评审阅读顺序、一分钟验收 |
| [`AI日志.md`](AI日志.md) | 逐轮 prompt、工具调用、真实报错与返工 |
| [`AAR复盘.md`](AAR复盘.md) | 预期 vs 实际、失败经验、改进方案 |
| [`拿来说明.md`](拿来说明.md) | 5 个关键决策的取舍过程 |

## License

[MIT](LICENSE) © 2026 07Meteorain
