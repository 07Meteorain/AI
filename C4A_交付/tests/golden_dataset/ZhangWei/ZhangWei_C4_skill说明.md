# ZhangWei 的 C4 技能：GitHub PR 描述自动生成器

## 解决什么问题

团队写 Pull Request 时经常卡在描述上——改了什么、为什么改、怎么测，全靠回忆。
这个技能把 `git diff` 和 commit 信息喂进去，自动产出结构化的 PR 描述。

## 使用场景

- 提交代码前自检 PR 描述是否完整
- 批量为多个 PR 补描述
- Code Review 前快速了解变更意图

## 输入输出

- **输入**：一个 git 仓库路径（本地路径，或已clone 的工作目录）
- **输出**：一份 Markdown 格式的 PR 描述文件 `PR_DESCRIPTION.md`

## 使用步骤

### 步骤 1：安装依赖

```bash
pip install -r requirements.txt
```

依赖：Python 3.9+、无第三方库依赖（纯标准库实现）。

### 步骤 2：运行

```bash
python scripts/pr_desc.py --repo . --base main --out PR_DESCRIPTION.md
```

参数说明：

| 参数 | 必填 | 说明 |
|---|---|---|
| `--repo` | 是 | 仓库路径，相对或绝对均可 |
| `--base` | 否 | 基准分支，默认 main |
| `--out` | 否 | 输出文件路径，默认 stdout |

## 真实案例

输入：一个包含 3 次 commit 的小型仓库

```bash
$ python scripts/pr_desc.py --repo . --base main
```

输出：

```markdown
## PR 描述（自动生成）

### 变更内容
- 新增 pr_desc.py：解析 git log 生成结构化描述
- 新增 tests/test_pr_desc.py：覆盖 3 个测试用例

### 变更原因
- 解决 PR 描述缺失问题

### 验证方式
- pytest tests/ → 3 passed
```

## 预期输出

运行成功后应生成包含 `## 变更内容` / `### 变更原因` / `### 验证方式`
三个小节的 Markdown。缺任一小节即为异常。

## 常见坑

1. **仓库有未提交改动**：先 `git stash` 再运行，否则 diff 会包含脏文件
2. **`--base` 分支名写错**：会静默得到空描述，建议先 `git branch -a` 确认
3. **Windows 换行符**：脚本已用 `newline=""` 处理，一般无需干预

## 边界情况

- 仓库无 commit：输出空模板并以退出码 1 结束
- diff 超过 2000 行：只取前 2000 行并在末尾标注截断
- 分支无差异：提示 "no changes"，退出码 0