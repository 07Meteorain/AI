请调用 memory 工具，把下面这一条写入用户档案（target=user，action=add），只写这一条，不要新增其他内容：

用户称呼：Meteorain；身份：AI 课程学生；偏好：中文、先结论后细节、命令必须可复现；当前挑战：C10H。

写完后用 terminal 执行命令确认文件存在并打印其内容：
  ls -l /e/hermes/memories/USER.md && cat /e/hermes/memories/USER.md

最后在回复里报告：memory 工具返回的 success 字段、terminal 命令退出码、USER.md 的实际内容。禁止在没有 tool_use 记录时声称成功。
