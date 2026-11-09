# 仓库链接（C5 交付）

## 仓库地址

- 仓库主页：https://github.com/07Meteorain/AI
- C5 交付目录：https://github.com/07Meteorain/AI/tree/master/C5_交付
- 项目名称：promptlint —— 提示词模板静态检查器

## 交付内容定位

| 路径 | 说明 |
| --- | --- |
| `C5_交付/README.md` | 项目介绍、安装与用法、12 条规则说明 |
| `C5_交付/promptlint/` | 源码包（零依赖，Python 3.9+ 标准库） |
| `C5_交付/tests/` | 单元测试与规则用例 |
| `C5_交付/examples/` | 可直接运行的示例模板与问题样例 |
| `C5_交付/docs/` | 设计说明与规则依据文档 |
| `C5_交付/demo/` | 演示材料 |
| `C5_交付/AI日志.md` | AI 协作过程日志 |
| `C5_交付/AAR复盘.md` | 事后复盘（After Action Review） |
| `C5_交付/拿来说明.md` | 交付说明与自查 |

## 持续集成

- CI 工作流：https://github.com/07Meteorain/AI/blob/master/C5_交付/.github/workflows/
- 运行状态：通过仓库 Actions 页面的 `c5-promptlint` 工作流查看

## 本地复现

```bash
git clone https://github.com/07Meteorain/AI.git
cd AI/C5_交付
python -m pytest tests -q
python -m promptlint examples/
```
