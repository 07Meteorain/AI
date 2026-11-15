"""组合根：把五层接起来。

单独一个文件做装配，是为了让"层与层之间怎么连"变成**一段能读的代码**，
而不是散落在 CLI 各处的 ``Xxx(...)``。看完 ``App.__init__`` 就看完了整个系统的接线图。
"""

from __future__ import annotations

from typing import Any

from .config import Config
from .llm import LLMPlanner, OfflineProvider, build_provider, tool_help
from .loop import AgentLoop, RulePlanner, TraceStore
from .memory import KSTARMemory
from .skills import SkillLoader, SkillRuntime
from .tools import ToolContext, build_registry


class App:
    def __init__(self, config: Config | None = None, provider: Any = None):
        self.config = config or Config.load()
        self.config.ensure_dirs()

        self.memory = KSTARMemory(self.config)          # L5 记忆
        self.loader = SkillLoader(self.config)          # L4 技能（发现）
        self.skills = SkillRuntime(self.config, self.loader)  # L4 技能（执行）
        self.tools = build_registry()                   # L2 工具
        self.provider = provider or build_provider(self.config)  # 可选模型
        self.mode = "offline" if isinstance(self.provider, OfflineProvider) else "llm"

        if self.mode == "offline":
            self.planner = RulePlanner()
        else:
            self.planner = LLMPlanner(self.provider, tool_help(self.tools), max_steps=self.config.max_steps)

        self.traces = TraceStore(self.config)           # 追踪
        self.loop = AgentLoop(                          # L3 循环
            self.config,
            self.memory,
            self.tools,
            self.skills,
            planner=self.planner,
            trace_store=self.traces,
            mode=self.mode,
            provider=self.provider,
        )

    # ------------------------------------------------------------------
    def context(self, run_id: str = "cli", *, allow_write: bool | None = None) -> ToolContext:
        return ToolContext(
            config=self.config,
            memory=self.memory,
            run_id=run_id,
            skills=self.skills,
            allow_write=self.config.write_memory if allow_write is None else allow_write,
            tools=self.tools,
        )

    def ask(
        self,
        text: str,
        *,
        session: str = "cli",
        allow_write: bool | None = None,
        persist: bool = True,
        force_intent: Any = None,
    ):
        return self.loop.run(
            text, session=session, allow_write=allow_write, persist=persist, force_intent=force_intent
        )

    def describe(self) -> str:
        return (
            f"brain {self.config.root.name}  "
            f"模式={self.mode}  工具={len(self.tools.specs())}  "
            f"技能={len(self.loader.load_all())}  记忆={self.memory.describe()}"
        )
