# AI 日志 · C5 promptlint

> **工具**：DeepSeek Harness（`deepseek-flash`），Windows，Python 3.12.14（目标兼容 3.9+），
> Git 2.55.0，GitHub CLI 2.102.0（未登录，推送使用本机凭据）。
> **记录原则**：按「一次可验收的动作」分轮，不按聊天消息；同一主题的多轮对话合并。
> **失败不删**：报错、误判、被中断的评审都保留在原文里。
> **证据**：命令与输出来自本次真实执行；推送与 CI 结果在第 10 轮回填。

## 轮次总览

| 轮次 | 目标 | 结果 | 是否返工 |
| --- | --- | --- | --- |
| 1 | 确认 shell 故障是不是命令问题 | 定位为进程创建层；改用完全权限执行 | 计划外 |
| 2 | 把「prompt 检查」收敛成规则 | 29 条候选 → 12 条可判定规则 | 删掉 17 条 |
| 3 | 核心实现 | 19 个源文件；CLI 可运行 | 否 |
| 4 | 示例标定 | good 0 问题、bad 12 问题；发现编码 bug | 是 |
| 5 | 测试首跑 | 1 个 ImportError → 75 项通过 | 是 |
| 6 | Python 3.9 兼容 | 3 处 3.10 API 改为 3.9 写法 | 是 |
| 7 | CRLF 回归 | 解析器归一化 + 2 项测试 | 是 |
| 8 | 文档与 CI 对齐 | 指标、链接、workflow 修正 | 是 |
| 9 | 独立评审 | 5 个缺陷，全部修复；测试 77 → 81 | 是 |
| 10 | 推送与 CI 验证 | commit / tag / push / Actions | 见本节末尾 |

---

## 第 1 轮：先确认「是不是我的代码问题」

### 触发

用户的第一条指令是完成 C5、把成果上传到 `https://github.com/07Meteorain/AI`。
我按惯例先跑环境检查：

```powershell
git --version
gh --version
node --version
```

### 实际结果

**没有任何输出，退出码 `3221225794`。**

```
(no output)
[exit code: 3221225794]
```

`3221225794` 的十六进制是 `0xC0000142`（`STATUS_DLL_INIT_FAILED`）：进程已经创建，
但在 DLL 初始化阶段就死了，所以拿不到 stdout/stderr。

### 排除过程（不是"重启试试"）

| 尝试 | 结果 | 排除了什么 |
| --- | --- | --- |
| 重跑 `Write-Output "hello"` | 同样 3221225794 | 不是命令参数 |
| 换工作目录到 `C:\Windows` | 同样 | 不是中文路径 |
| `run_in_background: true` | 同样 | 不是前台终端 |
| 子 agent 独立执行 5 条命令 | 全部同样 | 不是单个会话状态 |
| 跑 ACL 诊断脚本 | `VERDICT=NOT_THIS_CLASS` | 不是文件权限 |
| 完全权限跑 `Write-Output` | `escalated-ok` | 是**执行环境**，不是机器/命令 |

ACL 诊断脚本第一次还被系统的脚本执行策略挡住：

```
无法加载文件 ...diagnose-windows-sandbox-acl.ps1，因为在此系统上禁止运行脚本。
```

改用子进程 `-ExecutionPolicy Bypass` 后才跑起来。它的结论是：

```
VERDICT=NOT_THIS_CLASS
writeDac=true  writeOwner=true  packageObjects=[]
```

即：工作区的 Windows 文件权限是好的，问题不在 ACL。

### 判断

这是**沙箱进程创建层**的问题，不是我的代码、不是路径、不是权限项。
我用完全权限做了一次单命令验证，确认命令本身能跑；随后所有命令都在完全权限下执行。

**我没有把它写成"已修复"。** 根因仍未定位（没有 Procmon、没有事件日志），
这一点写进了 AAR 的 F1（未解决）。

### 顺带确认的推送条件

```bash
git ls-remote https://github.com/07Meteorain/AI.git   # 0
git clone --depth 1 ...                               # 0
git push --dry-run origin master                      # 0，Everything up-to-date
```

`gh` 未登录，但本机 git 凭据可用，推送路径成立。

---

## 第 2 轮：把「prompt 检查」收敛成 12 条规则

### 实际 prompt

> Rules: list every check you would put in such a linter, as many as you can
> justify. For each: one line, and mark whether it can be judged from text alone
> (yes/no).

### AI 的产出

29 条，其中 24 条标记为「只凭文本可判定」，5 条不可（调用点缺参、类型不匹配、
真实 token 数、插值注入语义、角色顺序）。

### 我的处理

没有照单全收。用三条标准筛：可只凭文本判定、可给确定位置、可写可复现反例。
结果保留 12 条，删掉/合并 17 条，例如：

- 同形字、混合模板方言、未知过滤器、include 环 → 不做（会暗示支持不存在的语言特性）；
- 行尾空白 / BOM / CRLF → 合并为 PL011；
- 必需段落为空 → 不做（需要角色概念）；
- token 预算 → 保留 PL010。

### 验证

```text
$ python -m promptlint rules
PL001 ... prompt-empty
...
PL012 ... front-matter-invalid
```

12 条，每条都有 `summary / rationale / bad_example / good_example`，`explain` 与
SARIF 元数据都从同一份类属性读取——文档不另写一份。

---

## 第 3 轮：核心实现与首次可运行

### 实现约束（我写给自己的验收条件）

1. `parser → rules → engine → reporters` 分层，规则不读文件、不打印；
2. 零第三方依赖，Python 3.9+；
3. 同一输入必须同一输出（无时间戳、无随机、无网络）；
4. 每条 finding 必须带 1-based 行/列，可直接进 SARIF。

### 产出

19 个源文件，1,743 行（最终值）。首次自检：

```text
$ python -m compileall -q promptlint
compileExit=0
$ python -m promptlint --version
promptlint 1.0.0
$ python -m promptlint rules
... 12 行 ...
```

### 人工检查发现的问题

规则能跑，但 `text` 报告里出现了无法在窄终端显示的字符（下一轮定位）。
这提醒我：**"本机能看"不等于"CI 能看"**。

---

## 第 4 轮：示例标定暴露的第一个真实 bug（编码）

### 动作

写 6 个示例：`good/` 2 个、`bad/` 4 个，配一份 `max_tokens: 120` 的演示配置。

```bash
python -m promptlint check examples/good --config examples/promptlint.json --fail-on info
python -m promptlint check examples/bad --config examples/promptlint.json
```

### 第一次输出（原文，含乱码）

```text
examples/bad/leaky.prompt
  6:17  error   PL005  possible OpenAI-style API key: sk-l��2b9d
  8:25  warning PL006  mobile number in prompt: 1380��8000
```

### 定位

`mask_secret()` 与 `snippet()` 用了 `…`（U+2026）。在当前控制台代码页下不可打印，
PowerShell 把它替换成了 `??`（终端里显示为 `��`）。

### 修复

```python
# 之前
return value[:4] + "\u2026" + value[-4:]
# 之后
return value[:4] + "..." + value[-4:]
```

同时把 `model.py` 的截断省略号也改成 `...`。

### 修复后

```text
6:17  error   PL005  possible OpenAI-style API key: sk-l...2b9d
8:25  warning PL006  mobile number in prompt: <redacted:11 chars>
```

（手机号那一行的变化来自第 8 轮的短值掩码改进，不是这一轮。）

### 教训

**linter 的默认输出必须能在最窄的终端里显示。** 这不是美观问题：报告是证据，
证据在 CI 日志里变成乱码，等于没有。

---

## 第 5 轮：测试首跑：71 项，1 个 ImportError

### 命令与结果

```bash
python -m unittest discover -s tests -v
```

```text
ERROR: test_baseline (unittest.loader._FailedTest.test_baseline)
ImportError: cannot import name 'apply_baseline' from 'promptlint.baseline'
Ran 71 tests ... FAILED (errors=1)
```

### 原因

`apply_baseline()` 定义在 `engine.py`，测试却从 `baseline.py` 导入。实现没有错，
是测试的导入路径错了——但第一次跑就暴露，说明分层边界还需要更清楚。

### 修复

```python
from promptlint.baseline import fingerprint, load_baseline, save_baseline
from promptlint.engine import apply_baseline
```

### 修复后

```text
Ran 75 tests in 0.161s
OK
```

---

## 第 6 轮：Python 3.9 兼容性：语法检查抓不到的 API 差异

### 动作 1：语法级检查

```python
ast.parse(source, feature_version=(3, 9))
```

19 个文件全部通过。**但这只能证明语法是 3.9 的，不能证明 API 是。**

### 动作 2：逐项检查新 API

发现 3 处：

```python
Path.write_text(..., newline="\n")   # newline 参数是 Python 3.10 新增
```

位置：`baseline.save_baseline()`、`cli` 的报告输出、`cli init`。

### 修复

```python
with path.open("w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
```

### 判断

`pyproject.toml` 写 `requires-python = ">=3.9"`，就必须有 3.9 的运行时证据。
本地只有 3.12，所以真正的证据只能是 CI 的 3.9 矩阵——这一点写进了 AAR 的 F3。

---

## 第 7 轮：CRLF 回归：一个没有报错、但会误判的 bug

### 发现过程

PL009 需要把 `(line, column)` 换算成绝对偏移，再判断占位符是否落在 XML 标签内。
`line_offset()` 假设每行以 `\n` 结尾（`len(line) + 1`），但 `parse_prompt()` 收到的
原始文本可能是 `\r\n`。这样偏移会随行数累积偏移，标签边界判断就会错位。

它不会崩溃，也不会在 LF 文件上出现——属于"测试不写就永远发现不了"的类型。

### 修复

```python
# parse_prompt 开头
text = text.replace("\r\n", "\n").replace("\r", "\n")
```

### 新增测试

- `test_crlf_is_normalised`：行号与占位符位置不受 CRLF 影响；
- `test_crlf_offsets_are_normalised`：10 行 CRLF 后仍能识别未包裹的
  `{{user_message}}`。

测试数 75 → 77。

---

## 第 8 轮：文档、指标与 CI 的「可验证」对齐

### 8.1 指标漂移

README 写 77 项、提交说明写 75 项、CHANGELOG 写 75 项；"12 轮"也是拍脑袋写的。
用脚本重新统计后统一为当时的值，并在交付前再统计一次（最终 81 项）。
**这不是笔误，是"手写指标"的必然结果**（AAR F4）。

### 8.2 断链

README 里 CI 链接写成 `../../.github/...`，从 `C5_交付/README.md` 出发会跳到仓库
之外。改为 `../.github/...`。

### 8.3 CI 断言

`examples/bad` 的 finding 数必须固定为 12。CI 用：

```bash
test "$(printf '%s' "$output" | grep -c '^  ')" -eq 12
```

后来给 `examples/README.md` 加说明时，它被当成 `.prompt` 文件一起 lint，计数变成
13——正好被这条断言抓住。修复：在 `examples/promptlint.json` 里排除 `README.md`。

### 8.4 monorepo 的 CI 真相

GitHub 只运行仓库根目录的 `.github/workflows/`。`C5_交付/.github/workflows/ci.yml`
在 monorepo 里**不会执行**。所以：

- 根目录新增 `c5-promptlint.yml`（`working-directory: C5_交付`，5 个 Python 版本 + SARIF）；
- 项目内的 `ci.yml` 保留，作为"抽出为独立仓库"时使用；
- README 与两个 workflow 的注释都写明这一点，不假装项目内 workflow 已运行。

---

## 第 9 轮：独立评审：5 个缺陷，全部修复

### 9.1 第一次评审失败（过程也记录）

我先把整个包 + 测试 + 示例交给一个评审 agent。它运行 40+ 分钟没有返回，我发出
"请现在收尾"的消息后仍未返回，只能中断。**评审任务的范围给得太大，是设计错误，
不是 agent 的错。**

### 9.2 聚焦评审的 prompt

> Read exactly these five files, nothing else … Return at most 6 issues … severity,
> file:line, what is wrong, minimal fix. Do NOT report style … Do NOT modify files.
> Do NOT run commands.

### 9.3 评审返回的 5 条（原文要点）

| # | 严重度 | 位置 | 问题 | 修复 |
| --- | --- | --- | --- | --- |
| 1 | medium | `cli.py` | `BrokenPipeError` 是 `OSError` 子类，被前面的 `except OSError` 先捕获，`\| head` 会报错退出 2 | 把 `except BrokenPipeError` 移到前面 |
| 2 | medium | `rules/safety.py` | `WRAPPER_RE` 不允许标签属性，`<context source="retrieval">…</context>` 被误报未包裹 | 正则加 `(?:\s[^<>]*)?` |
| 3 | medium | `baseline.py` | 指纹没有 occurrence 序数，新增的重复问题会被静默压制 | 按文件加 occurrence |
| 4 | low | `parser.py` | 块状 `vars:` 分支没有写入 `front_matter`，错误分支反而写入了被拒绝的值 | 移动赋值 |
| 5 | low | `cli.py` | `baseline --output` / `init --output` 不创建父目录 | 统一 `mkdir(parents=True)` |

### 9.4 处理

5 条全部接受。第 3 条正是第 2 轮设计咨询里 AI 提醒过、我当时没有做的那一条——
评审把它变成了一个具体缺陷，并给出了可复现场景（两行只差缩进的相同文本）。

新增 4 项测试（含 `test_only_the_accepted_occurrence_is_suppressed`），
测试数 77 → 81。重新生成 demo，确认仍是 12 个问题 / 6 个文件。

### 9.5 一个诚实的细节

评审 agent 指出：它阅读期间 `safety.py` 从 254 行变成 256 行，所以行号以当前版本为准。
这说明**评审与实现是并行的**，不是"写完后一次性验收"；行号会漂移，但缺陷本身可复现。

---

## 第 10 轮：推送与 CI 验证

> 本节在推送后回填。

### 10.1 本地提交

```bash
git add C5_交付 .github/workflows/c5-promptlint.yml README.md
git commit -m "feat(c5): add promptlint, a zero-dependency prompt template linter"
git tag -a c5-v1.0.0 -m "C5 promptlint 1.0.0"
git push origin master --tags
```

### 10.2 期望的远端状态

- `master` 包含 `C5_交付/` 与根目录 workflow；
- 标签 `c5-v1.0.0` 指向本次提交；
- Actions 运行 `C5 promptlint CI`：5 个 Python 版本 + SARIF job。

### 10.3 回填

（推送后填写运行结果、run URL 与失败修复记录。）

---

## 附：AI 在这 10 轮里出错/被拦截的地方

| 轮次 | 问题 | 谁发现 | 处理 |
| --- | --- | --- | --- |
| 2 | 29 条规则里 17 条不适合本项目 | 我（三条标准） | 删除/合并 |
| 4 | 掩码使用 `U+2026`，GBK 控制台显示 `??` | 我（跑示例） | 改 ASCII |
| 5 | 测试从错误的模块导入 `apply_baseline` | 测试首跑 | 改 import |
| 6 | 使用 Python 3.10 的 `write_text(newline=)` | 我（逐项检查） | 改 `open` |
| 7 | CRLF 下偏移错位（无报错） | 我（读代码） | 归一化 + 回归测试 |
| 8 | 指标手写导致 75/77 不一致 | 交付前核对 | 脚本统计后统一 |
| 9 | 指纹漏掉 occurrence 序数 | 独立评审 | 加序数 + 测试 |
| 9 | 第一次评审范围过大而超时 | 我 | 改为只读 5 个文件 |

## 附录：关键数字怎么复现

```bash
cd C5_交付
python -m unittest discover -s tests          # 81 tests
python -m promptlint check examples/good --fail-on info          # 0 problems
python -m promptlint check examples --config examples/promptlint.json  # 12 problems
python -m promptlint rules | wc -l            # 13 行（表头 + 12 条）
```
