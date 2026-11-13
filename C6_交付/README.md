# PromptGate · prompt 上线前的静态体检

> **C6 Web Application** ｜ 挑战 ID `ch-20260717031519-qqqx60`
>
> | 交付物 | 位置 |
> | --- | --- |
> | **app 链接** | <https://07meteorain.github.io/AI/> |
> | **repo 链接** | <https://github.com/07Meteorain/AI/tree/master/C6_交付> |
> | **demo** | [演示脚本.md](demo/演示脚本.md) ＋ [7 张真实截图](demo/截图/) |
> | **AI 日志** | [AI日志.md](AI日志.md)（另见 [AAR复盘.md](AAR复盘.md)、[拿来说明.md](拿来说明.md)） |

**一句话**：把「这个 prompt 能不能上线」从一次口头 review，变成一条可复现、可导出、可接进 CI 的结论。

它做四件具体的事：

1. **静态检查** —— 15 条规则，拦住硬编码凭据、注入面、自相矛盾的指令、未隔离的用户输入；
2. **变量契约** —— 把 `{{占位符}}` 变成一份可渲染、可预览的接口，而不是散落在正文里的字符串；
3. **成本预算** —— 同一个 prompt 换 8 个模型，月度成本差 24 倍，这个数字应该在写 prompt 时就知道；
4. **版本对比** —— 存快照、看 diff，让「我觉得改好了」变成「改了 6 行，error 从 5 降到 0」。

全部在浏览器本地完成：**没有后端、没有网络请求、没有账号，文本不出本机**。

---

## 为什么值得做

prompt 已经在生产环境里跑，但它享受的工程待遇比代码差一个时代：

- 代码有 linter、有 CI、有 code review；prompt 通常只有「跑一遍看看」。
- 代码里的密钥会被 secret scanner 拦住；prompt 里的 `api_key = sk-live-…` 会被贴进工单、聊天记录和向量库。
- 代码有类型检查保证接口一致；prompt 里的 `{{user_name}}` 和 `{{userName}}` 会安静地渲染成空串。

这个仓库里已经有过两次真实教训：C2 的参考文献有 3 条是 AI 编造的、格式完全合法；C4C 的引用审计器第一版误伤了 3 条真文献。**「看起来没问题」和「检查过没问题」差着一整套工具。**

PromptGate 是这套工具里最靠前的一环：在调用发生之前，把能静态发现的问题先发现掉。

---

## 30 秒验收（不用装任何东西）

打开 <https://07meteorain.github.io/AI/>，或直接双击仓库里的 `app/index.html`（`file://` 也能跑）。

| 步骤 | 你会看到 |
| --- | --- |
| 1. 首屏 | 自动载入一份合格样例，右上角绿色 **✓ PASS**、健康分 **100/100** |
| 2. 点「模板」→ 选「反面教材」 | 立刻变红 **✗ FAIL**，右侧列出 17 条问题，左侧行号槽出现红/黄标记点 |
| 3. 点任一问题右上角「第 3 行 ↑」 | 编辑器光标跳到对应行并选中，滚动位置对齐 |
| 4. 点「导出 → Markdown 报告」 | 下载一份含结论、命中表、变量契约、成本预算的报告 |
| 5. 点「预算」页 | 8 个模型的单次/月度成本对比，最省的一行标绿 |
| 6. 点「规则」页 → 关掉 PG004 | 顶部立刻回到 PASS（但「已忽略」里能看到它被排除，不是凭空消失） |

---

## 功能

| 功能 | 说明 | 亮点 |
| --- | --- | --- |
| 15 条静态规则 | PG001–PG015，分「安全 / 稳定性 / 可维护 / 成本」四类 | 每条都有 rationale、正反例、明确的误报边界，[docs/rules.md](docs/rules.md) 由代码生成 |
| 变量契约 | 解析 `{{x}}`，统计出现次数与行号，检查命名与拼写 | 「渲染预览」：填上值看到 prompt 真实长什么样 |
| 门禁判定 | error/warning/none 三档阈值 | 门禁只看级别，健康分只做阅读参考 —— 一条 error 不会被 30 条 info 稀释 |
| 基线忽略 | 按「规则 + 消息」指纹记录，**不含行号** | 调格式不会让历史问题复活；忽略项可 review、可清空 |
| 成本预算 | 8 个模型 × 输入/输出单价 × 调用量假设 | 价格可在线编辑；写明价格快照日期与 ±20% 的估算误差 |
| 版本快照 | 最多 20 版，存 localStorage | 行级 LCS diff，只显示改动附近的上下文 |
| 三种导出 | Markdown / JSON / SARIF 2.1.0 | SARIF 可直接上传 GitHub Code Scanning |
| CLI | `node tools/promptgate-cli.js prompt.md` | 退出码 `0/1/2`，可当 pre-commit 或 CI 门禁 |
| 深链 | `?sample=bad&tab=budget&theme=dark` | 截图脚本与问题复现都用同一套参数 |
| 离线 | Service Worker 预缓存 + `manifest.webmanifest` | 装成 PWA，断网可用 |
| 可访问性 | `aria-live` 结果区、skip link、键盘快捷键、`prefers-reduced-motion` | 快捷键：`Ctrl/⌘+S` 存版本、`Ctrl/⌘+K` 回编辑器、`T` 模板、`D` 换主题 |

---

## 快速开始

### 方式 A：直接打开（零安装）

双击 `app/index.html`。所有脚本都是普通 `<script>`（不是 ES module），因此 `file://` 下也能正常运行 —— 这是刻意的选择，见 [拿来说明.md](拿来说明.md)。

### 方式 B：本地起一个静态服务

```bash
python -m http.server 8000 --directory app
# 或者：npx serve app
```

用 http 打开时还会注册 Service Worker，第二次访问完全离线可用。

### 方式 C：命令行（同一套引擎）

```bash
node tools/promptgate-cli.js app/js/core/samples.js       # 直接体检任意文本文件
echo "总结这份会议记录。" | node tools/promptgate-cli.js -  # 从 stdin 读

node tools/promptgate-cli.js prompt.md --fail-on warning --format sarif --out report.sarif
node tools/promptgate-cli.js prompt.md --disable PG013 --quiet
node tools/promptgate-cli.js --list-rules
```

| 退出码 | 含义 |
| --- | --- |
| `0` | 通过门禁 |
| `1` | 被门禁拦下 |
| `2` | 用法/IO 错误（与「不合格」区分开，CI 里不会误判） |

### 方式 D：接进 CI / pre-commit

```yaml
# .github/workflows/prompt-check.yml
- name: PromptGate
  run: node tools/promptgate-cli.js prompts/system.md --fail-on error --format sarif --out promptgate.sarif
- uses: github/codeql-action/upload-sarif@v3
  if: always()
  with: { sarif_file: promptgate.sarif }
```

本地 pre-commit 就一行：

```bash
node tools/promptgate-cli.js prompts/*.md --fail-on error
```

### 开发与自检

```bash
node --test                 # 130 项测试，零依赖，Node ≥ 18
node tools/gen_rules_doc.js # 规则改了之后重新生成 docs/rules.md
node tools/gen_rules_doc.js --check   # 文档漂移检测（CI 会跑）
```

截图（Windows）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\shots.ps1
```

---

## 测试

`node --test` → **130 项，全部通过**。零测试框架依赖（只用 `node:test` + `node:assert`）。

| 文件 | 覆盖点 | 项数 |
| --- | --- | --- |
| `tests/parser.test.js` | 围栏/小节/占位符/CRLF/渲染替换 | 14 |
| `tests/tokenizer.test.js` | 估算单调性、区间、成本公式 | 12 |
| `tests/rules.test.js` | 15 条规则正反例、覆盖率、异常隔离、排序 | 16 |
| `tests/gate.test.js` | 阈值、健康分、基线、指纹 | 12 |
| `tests/diff.test.js` | LCS 行号映射、上下文裁剪、超大文本降级 | 10 |
| `tests/exporter.test.js` | 报告结构、Markdown 转义、SARIF 2.1.0 合法性 | 13 |
| `tests/storage.test.js` | 前缀隔离、隐私模式、配额写满的内存兜底 | 7 |
| `tests/ui.test.js` | 渲染转义（XSS 回归）、筛选、空态、搜索 | 16 |
| `tests/samples.test.js` | 样本完整性、合格样本零命中、demo 同步 | 8 |
| `tests/cli.test.js` | 退出码、四种格式、基线、stdin、错误路径 | 16 |
| `tests/docs.test.js` | 文档漂移、脚本/资源存在性、SW 清单、语法检查 | 6 |

几条刻意的设计：

- **「合格样例零命中」是最重要的回归测试**。任何人加规则时误伤了合格 prompt，这一条会立刻红。
- **XSS 回归**：把 `<script>`/`<img onerror>` 塞进问题消息里，断言输出里没有可执行标签。用户能把任意文本贴进编辑器，转义漏一处就是一个 XSS。
- **文档漂移检测**：`docs/rules.md` 由 `rules.js` 生成，CI 里跑 `--check`，改了规则忘了改文档会直接失败。
- **资源存在性**：解析 `index.html` 的 `<script src>` 与 `sw.js` 的预缓存清单，断言文件都在 —— 线上 404 是最难在本地复现的故障。

---

## 架构

```
                  ┌──────────────┐
   用户输入 ──────▶│  parser      │ 行 / 围栏 / 小节 / 占位符 / 其他风格
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │  rules × 15  │ 纯函数：model → finding[]
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │  gate        │ 阈值 + 基线 → PASS/FAIL + 健康分
                  └──────┬───────┘
                         ▼
        ┌────────────────┴────────────────┐
        ▼                ▼                ▼
   ┌─────────┐     ┌──────────┐     ┌──────────┐
   │ report  │────▶│ exporter │     │  ui.js   │  纯函数：数据 → HTML 字符串
   └────┬────┘     └────┬─────┘     └────┬─────┘
        │               │                │
        ▼               ▼                ▼
    CLI 入口      MD/JSON/SARIF      app.js（唯一持有状态的一层）
```

三个刻意的取舍：

1. **零第三方依赖**。不用 React、不用构建工具、不用测试框架。`git clone` 之后双击就能跑，`node --test` 就能验证 —— 为了省几百行而引入一整棵依赖树，等于把环境成本转给每一个第一次打开仓库的人。
2. **UMD 而不是 ES module**。浏览器里挂到 `window.PG`，Node 里 `module.exports`，**同一份文件**同时被 app 和测试加载。代价是没有 bundler 的按需加载，收益是「测的就是跑的」。
3. **单一入口 `report.buildReport()`**。UI、CLI、导出、测试都从这里拿结论，避免出现「页面上显示 5 个 error、导出报告里写 6 个」这种经典事故。

---

## 规则表

| 规则 | 级别 | 分类 | 拦什么 |
| --- | --- | --- | --- |
| PG001 | error | 稳定性 | 空 prompt 或少于 20 字符 |
| PG002 | warning | 稳定性 | 没有可识别的任务动词/角色声明 |
| PG003 | warning | 稳定性 | 没有输出格式约束 |
| PG004 | error | 安全 | 硬编码凭据（sk-/ghp_/AKIA/JWT/私钥/赋值式） |
| PG005 | warning | 可维护 | 硬编码本机路径 |
| PG006 | warning | 可维护 | `{{x}}` `{x}` `${x}` `[X]` 混用 |
| PG007 | warning | 可维护 | 变量名不符合 snake_case |
| PG008 | warning | 可维护 | 变量名疑似拼写不一致（`user_name` vs `userName`） |
| PG009 | error | 稳定性 | 互斥指令（简洁↔详细、只输出↔解释推理、中英混要） |
| PG010 | error | 安全 | 注入短语出现在正文 / 变量裸嵌无分隔符 |
| PG011 | warning | 可维护 | 代码围栏未闭合 |
| PG012 | info | 稳定性 | 模糊量词（尽量/差不多/适当） |
| PG013 | info | 稳定性 | 没有 few-shot 示例 |
| PG014 | info | 稳定性 | 没有「信息不足怎么办」的边界 |
| PG015 | info | 成本 | 单行 > 400 字符或全文 > 3000 token |

完整说明（判定条件、为什么是问题、怎么改、正反例、误报边界）见 **[docs/rules.md](docs/rules.md)** —— 该文件由 `tools/gen_rules_doc.js` 从代码生成。

---

## 和 C5 的关系

C5 的 `promptlint` 是一个 12 条规则的 Python 静态检查器，验证了「prompt 可以 lint」这件事。
C6 把它做成了**产品**：浏览器里直接可用、有预算和版本这两个真实决策功能、有 CLI 和 SARIF 可以直接接进流水线、有可离线安装的 PWA。

规则从 12 条变成 15 条，新增的是 C5 里没有的 `PG008`（变量名拼写不一致）、`PG013`（缺 few-shot）、`PG015`（体量预算）。引擎重写为 JS，因为要跑在浏览器里；**两套实现不共享代码**，这一点在 [拿来说明.md](拿来说明.md) 里写清楚了。

---

## 部署

仓库根目录的工作流 `.github/workflows/c6-pages.yml` 把 `C6_交付/app` 作为 Pages artifact 发布：

```yaml
on: { push: { branches: [master], paths: ['C6_交付/app/**'] }, workflow_dispatch: }
permissions: { contents: read, pages: write, id-token: write }
```

即：**改 app 里的文件并合入 master，线上就更新**，不需要手动上传。CI（`c6-ci.yml`）在每次 push 时跑测试 + 文档漂移检查。

---

## 目录结构

```
C6_交付/
├── app/                     # 可独立运行的 Web 应用（双击 index.html 即可）
│   ├── index.html
│   ├── styles.css           # 深/浅色、响应式、打印样式
│   ├── manifest.webmanifest
│   ├── sw.js                # 离线缓存
│   ├── assets/              # 图标（tools/make_icons.py 生成）
│   └── js/
│       ├── core/            # 11 个纯逻辑模块（parser/tokenizer/diff/rules/gate/exporter/storage/models/samples/report/util）
│       ├── ui.js            # 数据 → HTML 字符串（无状态）
│       └── app.js           # 唯一持有状态的一层
├── tools/
│   ├── promptgate-cli.js    # CLI 入口（同一套引擎）
│   ├── gen_rules_doc.js     # docs/rules.md 生成器
│   ├── make_icons.py        # 图标生成（只在改图时需要）
│   └── shots.ps1            # demo 截图脚本
├── tests/                   # 130 项，node --test
├── demo/                    # 演示脚本 + 7 张截图
├── docs/rules.md            # 自动生成的规则说明
├── README.md                # 本文件
├── 提交说明.md               # 交付物对照 + 评审阅读顺序
├── AI日志.md                 # 逐轮 AI 协作记录（含 failure）
├── AAR复盘.md                # 预期/实际/失败经验/改进方案
├── 拿来说明.md               # 关键决策的取舍过程
└── CHANGELOG.md
```

---

## 诚实边界

写在这里的每一条都希望评审在打分时看到：

1. **静态分析看不到「prompt 效果」**。PG003 说「没有格式约束」，但有了格式约束的 prompt 也可能答得很差。工具只能证明「结构上有缺陷」，不能证明「内容好」。
2. **规则是启发式的**。PG002/003/012/013/014 都靠关键词，换一种写法就可能漏检或误报。每条规则的误报边界写在 `docs/rules.md` 末尾。
3. **token 是估算，误差约 ±20%**。中文按 0.75 token/字、英文按 1.3 token/词。精确值要用官方 `count_tokens`。预算的用途是「量级判断」，不是「财务对账」。
4. **价格是 2026-11-01 的快照**，会过期。所以 UI 允许直接改价，报告里也印着快照日期。
5. **版本存 localStorage**，不同步、换设备就没了、上限 20 条。这不是一个协作产品，是单人本地的工具。
6. **没有真实用户数据**。所有「好用」的判断来自我自己反复使用，没有埋点、没有留存曲线。上线后第一件该做的事是加最小埋点（见 AAR 复盘 §5）。
7. **窄屏（< 720px）会隐藏行号槽**并允许折行 —— 手机上的取舍，不是缺陷，但确实损失了「点行号跳转」的能力。

---

## License

MIT，见 [LICENSE](LICENSE)。
