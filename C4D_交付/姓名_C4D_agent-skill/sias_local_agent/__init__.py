"""
C4D 本地大模型 Agent 技能包
Local LLM Agent Skill with Gemma 4

设计要点
--------
1. 零云端依赖：所有推理通过本地 Ollama (http://localhost:11434) 完成。
2. Agent 能力完整：
   - 工具调用 (function calling)：模型自主决定调用哪个工具
   - 结构化输出：强制 JSON schema 约束
   - 记忆：会话历史 + 事实记忆持久化到磁盘，重启后可恢复
   - 多步推理：ReAct 风格的循环，直到模型输出终止信号
   - 代码生成：模型生成可执行代码并沙箱校验
3. 可复用：以 skill 形式打包，可通过 pip install -e . 安装为命令行工具。

模块划分
--------
    llm.py        Ollama 客户端封装（chat / 结构化输出 / function calling）
    memory.py     记忆层（短期对话历史 + 长期事实记忆，SQLite 持久化）
    tools.py      工具注册表（每个工具是带 schema 的可调用对象）
    agent.py      Agent 主循环（ReAct + function calling 路由）
    skill.py      技能层：把 Agent 能力封装成可复用的「本地地理技能」
"""

__version__ = "1.0.0"
__all__ = ["__version__"]