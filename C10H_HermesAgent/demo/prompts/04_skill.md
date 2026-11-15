请使用 skill_manage 工具创建一个新技能，参数：
- name: c10h-delivery-check
- description: C10H 交付前检查清单
- 内容必须包含四个二级标题：## When to Use、## Procedure、## Pitfalls、## Verification
- Procedure 里列出 6 项检查：README、安装记录、配置说明、demo、AI日志、AAR 复盘

创建完成后，用 terminal 执行：
  find /e/hermes/skills -name SKILL.md -path '*c10h*' -print
并打印这个 SKILL.md 的前 20 行，确认文件真实存在。最后报告路径与 skill_manage 的返回状态。
