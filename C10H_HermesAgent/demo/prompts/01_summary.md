读取当前目录下 project/notes.md 和 project/study_log.csv，完成三件事：

1. 用三条中文要点概括 notes.md 的核心内容；
2. 计算 study_log.csv 里 minutes 列的总和；
3. 给出一句不超过 40 字的改进建议。

写入要求（必须遵守）：
- 本会话只启用了 file 和 terminal 工具，禁止使用 execute_code。
- 必须真实调用 write_file 工具，把结果写入 out/summary.md（Markdown）。
- 写完后必须调用 read_file 读回 out/summary.md，并在回复中引用其中一行作为验证。
- 如果 write_file 失败，改用 terminal 写文件，并报告命令与退出码。
- 不允许在没有任何 tool_use 记录的情况下声称"已写入"。
