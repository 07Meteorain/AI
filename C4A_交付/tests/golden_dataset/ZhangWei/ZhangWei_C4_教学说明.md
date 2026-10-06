# 教学说明：PR 描述生成器上手

## 快速开始

```bash
pip install -r requirements.txt
python scripts/pr_desc.py --repo . --base main
```

本项目只用 Python 标准库，`requirements.txt` 为空文件（占位，便于统一管理）。

## 分步骤

**第1 步** 确认 Python 版本 ≥ 3.9
**第 2 步** 在你的项目仓库根目录执行上面的命令
**第 3 步** 把输出复制到 GitHub PR 描述框

## 常见坑

- 忘记加 `--base main`，会对比到不存在的分支
- 在错误的目录下运行，`--repo .` 会指向当前目录而不是目标仓库

## 优化技巧

- 想自动写入 PR：用 `gh pr create --body-file PR_DESCRIPTION.md`
- 想只看统计不要全文：把 `--stat` 换成 `--numstat`