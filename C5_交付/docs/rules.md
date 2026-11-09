# 规则参考

每条规则都回答四个问题：抓什么、为什么值得抓、反例与正例、什么时候会误报。
规则 id 与文件名无关，稳定不变；CI 配置、基线、SARIF 都依赖它。

| ID | 名称 | 默认级别 |
| --- | --- | --- |
| [PL001](#pl001) | prompt-empty | error |
| [PL002](#pl002) | placeholder-undeclared | error |
| [PL003](#pl003) | placeholder-unused | warning |
| [PL004](#pl004) | placeholder-malformed | error |
| [PL005](#pl005) | secret-literal | error |
| [PL006](#pl006) | pii-literal | warning |
| [PL007](#pl007) | missing-output-contract | warning |
| [PL008](#pl008) | duplicate-instruction | warning |
| [PL009](#pl009) | untrusted-input-boundary | warning |
| [PL010](#pl010) | prompt-too-long | warning |
| [PL011](#pl011) | invisible-character | warning |
| [PL012](#pl012) | front-matter-invalid | error |

---

<a id="pl001"></a>
## PL001 · prompt-empty

**抓什么**：去掉 front matter 后正文为空（只有空白也算）。

**为什么**：模板渲染失败、路径写错、把变量块当成了正文，都会得到「空 prompt」
而不报错。模型收到空输入时的回答通常是废话，排查却从下游开始。

**反例**

```text
---
vars: [topic]
---
```

**正例**

```text
---
vars: [topic]
---
Explain {{topic}} in one paragraph.
```

**边界**：只有 front matter 的文件一定触发；如果 front matter 本身就是模板，请把它
改成正文内容。

---

<a id="pl002"></a>
## PL002 · placeholder-undeclared

**抓什么**：文件声明了 `vars`，但 `{{name}}` 不在列表里。

**为什么**：声明了变量清单就等于声明了契约。多余的占位符要么是拼写错误，要么是
忘了更新声明；两者都会让渲染器报错，或把字面量发给模型。

**反例**

```text
---
vars: [topic]
---
Write about {{topik}}.
```

**正例**

```text
---
vars: [topic]
---
Write about {{topic}}.
```

**边界**：文件没有 `vars` 时不会检查（旧模板不需要一次性补声明）。想启用这组检查，
先写 `vars: []` 或列出变量。

---

<a id="pl003"></a>
## PL003 · placeholder-unused

**抓什么**：`vars` 里声明了，但正文没用到。

**为什么**：通常是删了一段指令却忘了删输入，或本来该插入变量却写成了常量。
声明越多，渲染器要求调用方提供的参数越多，成本是真实的。

**反例**

```text
---
vars: [tone, topic]
---
Explain {{topic}}.
```

**正例**

```text
---
vars: [tone, topic]
---
In a {{tone}} tone, explain {{topic}}.
```

**边界**：有意保留的变量（灰度、复用模板）可以用 `PL003: "off"` 或写进基线。
注意：`{{name}` 这类语法错误会让 `name` 同时触发 PL004 与 PL003，这不是重复告警，
而是两个独立事实（语法坏了 + 声明的变量确实没被正确使用）。

---

<a id="pl004"></a>
## PL004 · placeholder-malformed

**抓什么**：`{{name`（未闭合）、`{{}}`（空名）、`{{1st}}`（非法标识符）、
孤立的 `}}`。

**为什么**：这些写法不会渲染。它们会以字面量进入模型上下文，让模型「看到了变量名
但没看到值」；表现出来像模型不听话，实际是模板坏了。

**反例**

```text
Hello {{name
Empty {{ }} and {{1st}}
```

**正例**

```text
Hello {{name}}
```

**边界**：占位符允许内部空格（`{{ name }}` 会规范化为 `name`）。反引号包起来的
行内代码与 ``` 围栏内的 `{{...}}` 会被忽略，因为那里通常是示例而不是模板。

---

<a id="pl005"></a>
## PL005 · secret-literal

**抓什么**：OpenAI 风格 `sk-...`、GitHub token、AWS access key id、Slack token、
私钥块，以及 `api_key: ...` / `password: ...` 形式的硬编码凭据。

**为什么**：prompt 会被复制进日志、issue、截图、供应商后台。一旦提交，密钥就
已经泄露；正确的动作是轮换密钥并把值移到环境变量。

**反例**

```text
Call the API with sk-live-7f3a9c2e1b4d8f6a0c5e2b9d
```

**正例**

```text
Read OPENAI_API_KEY from the environment.
```

**边界**：规则只做形状匹配，可能漏掉自定义前缀的密钥；报告中的值会被掩码
（`sk-l...2b9d`），但**发现即代表该值已经进入过工作区**，仍应按泄露处理。

---

<a id="pl006"></a>
## PL006 · pii-literal

**抓什么**：邮箱、中国大陆手机号、18 位身份证号。

**为什么**：模板里的真实联系方式会随 prompt 进入日志与第三方服务；用真实数据
做例子还会让后续测试无法脱敏。

**反例**

```text
Contact alice.wong@example.com or 13800138000.
```

**正例**

```text
Contact {{email}} or {{phone}}.
```

**边界**：邮箱在报告中保留首字母（`a***@example.com`）；手机号只有 11 位，
部分掩码会暴露大半，因此只报告长度（`<redacted:11 chars>`）。测试用
`example.com` 也会被标记，因为它同样是「真实形状」；如果示例必须保留，请写进基线。

---

<a id="pl007"></a>
## PL007 · missing-output-contract

**抓什么**：正文 ≥ 200 字符，且没有任何输出格式线索（JSON/YAML/Markdown/表格/
schema/返回/输出/格式等）。

**为什么**：没有格式约定时，同一 prompt 两次运行的结构会漂移；下游解析器第一次
就崩在「模型今天用了另一种写法」上。

**反例**

```text
Summarise the article carefully and completely. （重复到 200 字符以上）
```

**正例**

```text
Summarise the article. Return JSON: {"summary": string}
```

**边界**：短 prompt 豁免（一句话问题通常格式自明）。这是启发式，关键词出现不代表
格式真的被约束；反过来，用罕见词描述格式也会漏报。

---

<a id="pl008"></a>
## PL008 · duplicate-instruction

**抓什么**：两行非空、非标题、长度 ≥ 20 的指令在规范化（小写、压缩空白、去尾
标点）后完全相同。

**为什么**：替换句子时留下旧副本，是 prompt 编辑中最常见的残留；重复内容浪费预算，
还可能和新版本互相矛盾。

**反例**

```text
Always answer in English and cite sources.
Always answer in English and cite sources.
```

**正例**

```text
Always answer in English and cite sources.
```

**边界**：只比较「整行完全相同」；同一意思的两种写法不会触发。围栏代码与标题不
参与比较。

---

<a id="pl009"></a>
## PL009 · untrusted-input-boundary

**抓什么**：`{{user_message}}`、`{{context}}`、`{{document}}` 等不可信输入占位符
没有被 XML 标签包裹。

**为什么**：用户输入和系统指令在同一个文本通道里时，数据里的一句「忽略以上指令」
就是一条指令。用 `<user_message>...</user_message>` 给出结构边界，是成本最低的
缓解措施之一。

**反例**

```text
Summarise this: {{user_message}}
```

**正例**

```text
<user_message>
{{user_message}}
</user_message>
```

**边界**：只识别 XML 标签；Markdown 标题、分隔线等自定义边界不会被认可。它降低
而非消除注入风险——边界内的内容仍可能被模型当作指令。

---

<a id="pl010"></a>
## PL010 · prompt-too-long

**抓什么**：按内置估算超过 `max_tokens`（默认 4000）。

**为什么**：超长 prompt 更贵、更早撞上下文窗口，也更容易把关键指令埋在中段。

**正例**

```text
把参考资料移进检索，只把命中的片段放进 prompt。
```

**边界**：这是估算，不是精确 BPE 计数，误差约 ±30%；用于发现数量级问题，不用于
计费。默认 4000 是经验值，按模型和任务调整。

---

<a id="pl011"></a>
## PL011 · invisible-character

**抓什么**：零宽空格/连接符、方向控制符、word joiner、BOM、不换行空格。

**为什么**：这些字符肉眼不可见，可以藏指令，也会破坏精确匹配；从聊天窗口或 PDF
复制文本时经常带进来。

**反例**

```text
Ignore previous instructions.\u200b
```

**正例**

```text
Ignore previous instructions.
```

**边界**：每行只报第一个不可见字符，避免刷屏；`\u00a0` 在部分排版文本中是正常
用法，可按需关闭此规则。

---

<a id="pl012"></a>
## PL012 · front-matter-invalid

**抓什么**：`---` 未闭合、行不是 `key: value`、`vars` 不是列表、变量名非法。

**为什么**：front matter 坏了以后，PL002/PL003 会静默失效——报告看起来干净，
实际什么都没检查。这比报错更危险。

**反例**

```text
---
vars: topic
---
Hello {{topic}}
```

**正例**

```text
---
vars: [topic]
---
Hello {{topic}}
```

**边界**：只支持最小子集（`key: value` 与 `vars` 列表），不是完整 YAML；复杂结构
请在 CI 之外用真正的 YAML 解析器校验。
