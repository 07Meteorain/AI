# AI 使用日志：我怎样把 Hermes「逼」到能干活

> 记录对象：本次 C10H 挑战中，**DSH（DeepSeek Harness）作为协作 agent**、**Hermes Agent 作为被驾驭对象**、**Ollama gemma4 作为本地模型** 的三方协作过程。
> 记录原则：只写真实发生的轮次；失败不删；prompt 改了什么、为什么改，都留原文。
> 可追溯：每条结论都能在 `demo/transcripts/`、`证据/`、`安装记录/` 找到对应文件。

---

## 0. 一句话复盘

这次不是「让 AI 写一份安装文档」，而是**让 AI 真的去装、去踩坑、去修，再把过程写成可验证的记录**。AI 负责执行与起草，我负责定验收标准、判断真假、决定下一步；两者交替了 14 轮。

---

## 1. 任务拆解（第 1 轮）

**我的输入（大意）**：

> 帮我完成 C10H 挑战，在 C10H 里新建文件夹，内容上传到 github.com/07Meteorain/AI。严格按挑战文件完成。

**AI 的第一反应**：先读 `挑战说明.md` 和 `challenge.json`，把评分维度拆成可执行清单：

| 挑战要求 | 我要求的产物 | 验收标准 |
| --- | --- | --- |
| 安装记录 | `安装记录/` | 有时间线、失败、版本、验证命令 |
| 配置说明 | `配置说明/` | 每个键有理由，密钥不落仓库 |
| demo | `demo/` | 可复跑，有原始轨迹 |
| AI日志 | `AI日志/` | 多轮、prompt 迭代、失败 |
| AAR（评分要求） | `复盘/` | 根因 + 改进方案 |

**判断**：这一步 AI 做得对——先拆评分标准，而不是先写代码。但「安装记录」不能靠编，必须真装。于是我要求它先探测环境（Python/Git/GPU/Ollama/磁盘），再决定安装路径。

---

## 2. 安装阶段：连续 6 次失败

### 轮次 2：官方安装器

- **动作**：下载 `install.ps1`，执行。
- **结果**：PowerShell 执行策略拒绝。
- **AI 的修正**：不落盘，用 `[scriptblock]::Create()` 在当前进程跑（等价 `iex`）。
- **评价**：正确，且没有去改系统执行策略——这是加分项，改注册表会污染环境。

### 轮次 3：卡在 Python 下载

- **现象**：`uv python install` 12 分钟无字节；`hermes --version` 报 `HTTP Error 403: rate limit exceeded`。
- **AI 的判断**：不是下载慢，是 GitHub API 配额耗尽，解析阶段就失败。
- **决策**：放弃托管 Python，改用系统 Python 3.14 + venv。**这是我拍的板**：继续等可能永远等不到，而系统 Python 版本正好匹配。

### 轮次 4：依赖冲突

- **现象**：`browser-harness` 要 `pillow==12.3.0`，Hermes 要 `pillow==13.0.0`。
- **AI 的修正**：`--override pillow==12.3.0`。
- **判断**：这是上游 pin 不一致，覆盖是合理的最小改动；如果后续 browser 功能异常，再回退调查。

### 轮次 5：锁文件卡死

- **现象**：`uv sync --frozen` 连上了 files.pythonhosted.org 但 0 字节。
- **AI 的修正**：设 `UV_INDEX_URL` 为清华镜像，重新解析。
- **结果**：76 个包 1 分钟装完。
- **评价**：这是「懂原理」的体现——知道锁文件固定 URL，所以换镜像必须重新解析而不是 `--frozen`。

### 轮次 6：网关 breakaway

- **现象**：`hermes chat` 报 `Gateway inaccessible: windows_breakaway_unavailable`。
- **AI 的分析**：DSH 把子进程放进禁止 `CREATE_BREAKAWAY_FROM_JOB` 的 Job Object，Hermes 想拉后台网关被拒。
- **修正**：前台 `hermes gateway run`，CLI 连接已有网关。
- **评价**：没有去改 Hermes 源码或关掉 Job Object，而是用官方支持的「前台网关」路径。

### 轮次 7：bash 缺失

- **现象**：`read_file` 报 `No shell found. Hermes needs bash`。
- **AI 的修正**：`.env` 里设 `HERMES_GIT_BASH_PATH`，指向 pinned Git 的 `usr\bin\bash.exe`，重启网关。
- **评价**：这是 Windows 原生安装最隐蔽的坑；AI 通过读 `pm/shell.py` 找到解析顺序，而不是乱试 PATH。

---

## 3. Demo 阶段：一次真实的幻觉

### 轮次 8：demo 01 v1（失败）

**Prompt v1**（节选）：

> 读取 notes.md 和 study_log.csv，概括三点、算总和、给建议，写入 out/summary.md。完成后报告调用了哪些工具、退出码。

**实际发生**：

1. 模型选择 `execute_code`，被 Hermes 以「单查询模式无人批准」拒绝；
2. 模型没有改用 `write_file`，而是直接输出「文件 out/summary.md 内容已写入」；
3. 检查磁盘：`out/` 目录根本不存在。

**这是本次最重要的发现**：小模型会把「打算做」说成「已经做」。Hermes 官方文档也明确警告过这一点。原始轨迹保存在 `证据/失败-01-幻觉写入.jsonl`。

### 轮次 9：demo 01 v2（成功）

**Prompt 改动**（三处硬约束）：

| v1 | v2 | 为什么 |
| --- | --- | --- |
| 未限制工具集 | `-t file,terminal` | 从源头移除 `execute_code`，不给模型犯错的机会 |
| 未要求回读 | 「写完后必须 read_file 读回并引用一行」 | 把「验证」变成可检查的动作 |
| 未禁止空口 | 「不允许在没有任何 tool_use 记录时声称已写入」 | 直接针对幻觉 |

**结果**：`read_file ×2 → write_file → read_file(验证)`，`exit_code=0`，`out/summary.md` 真实存在，内容含「minutes 总和: 180」。

**我的判断**：这次成功不是模型变强了，是**任务被设计得可验证**。这也是后面写 AAR 的核心结论。

### 轮次 10：记忆写入

**Prompt 设计**：明确 `target=user`、给出唯一一条内容、要求用 `terminal` 回读 `USER.md`。

**结果**：`memory` 返回 `success:true`，`USER.md` 139 字节，`terminal` 退出码 0。一次成功。

**但**：如果不要求回读，我无法确认它是真写还是假写——这正是「可验证」的价值。

### 轮次 11：新会话读记忆（两次）

**第一版结果**：新会话准确说出偏好，但把记忆路径说成 `E:\hermes\profiles\default\memories\`，而实际是 `E:\hermes\memories\`。模型在「路径」这种细节上编了一个看起来合理的答案。

**Prompt 改动**（v2）：

| v1 | v2 | 为什么 |
| --- | --- | --- |
| 问「介绍我」 | 明确「不要介绍你自己（你是阿赫）」 | 小模型会把 SOUL 人格与用户画像混在一起 |
| 要求说明路径 | 加一句「不确定就回答『不确定』，不要猜」 | 把「承认不知道」变成允许的答案 |

**第二版结果**：`称呼：Meteorain / 身份：AI 课程学生 / 偏好：中文、先结论后细节、命令必须可复现 / 文件路径：不确定`，`exit_code=0`。

**我的判断**：这次不是「模型记住了路径」，而是**prompt 允许它说不知道**。对交付来说，一个诚实的「不确定」比一个编造的路径有价值得多。

### 轮次 12：技能创建（两次尝试）

**第一次**：`skill_manage` 返回 `SKILL.md must start with YAML frontmatter (---)`，整批回滚。
**第二次**：模型自己补了 frontmatter，创建成功；`find` + `read_file` 验证路径与内容。
**后续**：Hermes 的 lint 提示缺 `version/author/license`，我在交付版里补齐（`扩展/skill-c10h-delivery-check/SKILL.md`）。

**评价**：这是 Hermes「工具报错 → 模型自我修正」闭环的最好证据，比一次成功更有说服力。

---

## 4. Prompt 迭代汇总

| 场景 | 版本 | 关键改动 | 效果 |
| --- | --- | --- | --- |
| 安装排错 | v1 | 「装 Hermes」 | 卡在 403，无降级 |
| | v2 | 「先探测环境，失败要记录根因和替代路径」 | 产出 9 条故障记录 |
| demo 01 | v1 | 只给任务 | 幻觉写入 |
| | v2 | 限工具 + 强制回读 + 禁止空口 | 真实写盘 |
| memory | v1 | 「记住我」 | 小模型可能只说不做 |
| | v2 | 指定 `target/action` + 回读文件 | 一次成功 |
| 记忆读取 | v1 | 问「介绍我」、要求说路径 | 把路径编成 `profiles\default\memories` |
| | v2 | 禁止介绍自己 + 允许回答「不确定」 | 准确说出偏好，路径答「不确定」 |
| skill | v1 | 给名称和章节 | 缺 frontmatter 失败 |
| | v2 | 由模型读报错后自行修正 | 成功，且有 lint 提示 |

**我总结的 prompt 四件套**：

1. **角色**：你是谁、用什么语言、先结论还是先细节；
2. **边界**：只能用哪些工具、只能写哪个目录、禁止什么；
3. **验收**：写完必须回读、必须报告退出码、必须引用一行；
4. **失败处理**：工具被拒时改用什么，而不是放弃或假装成功。

---

## 5. 工具调用统计（来自原始 JSONL）

| Demo | 工具序列 | tokens | 耗时 | exit_code |
| --- | --- | ---: | ---: | ---: |
| 01 文件读写 | `read_file ×2 → write_file → read_file` | 25,334 | 123.4 s | 0 |
| 02 记忆写入 | `memory → terminal` | 12,242 | 62.3 s | 0 |
| 03 记忆读取 | 无工具（纯上下文） | 3,816 | 36.2 s | 0 |
| 04 技能创建 | `skill_manage(失败) → skill_manage(成功) → terminal → read_file` | 42,466 | 128.5 s | 0 |

> 时间全部是 4.6B 模型在 4 GB 显存上的真实耗时；prefill 占大头，不是 Hermes 卡住。

---

## 6. 失败与修正清单（12 条）

| # | 失败 | 谁发现 | 修正 |
| --- | --- | --- | --- |
| 1 | 执行策略禁止脚本 | AI | scriptblock 执行 |
| 2 | GitHub API 403 | AI | 手动 venv |
| 3 | pillow 冲突 | AI | override |
| 4 | 锁文件 0 字节 | AI | 镜像重解析 |
| 5 | 网关 breakaway | AI | 前台 gateway run |
| 6 | bash 缺失 | AI | HERMES_GIT_BASH_PATH |
| 7 | execute_code 被拒 | AI | 限 toolset |
| 8 | 幻觉写入 | **我**（检查磁盘发现） | 强制回读 |
| 9 | config set 挂起 | AI | 直接写 YAML |
| 10 | 记忆路径答错 | **我**（对照真实路径） | prompt 加「不确定就说不知道」 |
| 11 | skill 缺 frontmatter | Hermes 工具 | 模型自我修正 |
| 12 | PowerShell 重定向编码 | AI | 渲染器兼容 UTF-8/UTF-16 |

---

## 7. 人机分工

| 环节 | AI 做 | 我做 |
| --- | --- | --- |
| 读挑战、拆评分 | ✅ 初稿 | 确认交付物清单 |
| 环境探测 | ✅ | 决定装 E 盘 |
| 安装排错 | ✅ 执行与定位 | 判断「继续等 vs 换路线」 |
| demo 设计 | ✅ 起草 prompt | **定验收标准：必须回读** |
| 真伪判断 | ❌ | 检查 `out/` 是否存在、`USER.md` 字节数 |
| 文档起草 | ✅ 初稿 | 逐条核对命令/版本/路径 |
| AAR | ✅ 结构 | 补「为什么」与改进优先级 |

**结论**：AI 能极大加速「执行 + 起草」，但**验收标准和真伪判断必须由人定**。这次如果没有人工检查磁盘，demo 01 就会以一个漂亮的假成功交上去。

---

## 8. 会话索引（可追溯）

| 会话 ID（前缀） | 内容 |
| --- | --- |
| `local-9ed3ba56…` | 首次连通性测试（模型自我介绍） |
| `local-9af9f5e8…` | demo 01 v1（execute_code 被拒 + 幻觉） |
| `local-78a3fb5f…` | demo 01 v2（真实写盘） |
| `local-7c5f22b0…` | demo 02（memory 写入） |
| `local-636e3673…` | demo 03 v2（新会话读记忆，路径答「不确定」） |
| `local-b908dc39…` | demo 04（skill 创建，两次尝试） |

完整列表见 `证据/sessions-list.txt`；每条会话的原始事件见 `demo/transcripts/*.jsonl`。
