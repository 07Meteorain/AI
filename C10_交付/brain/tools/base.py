"""工具层：智能体伸向外部世界的手，以及这只手的刹车。

一条工具要有五样东西才算"可交付"，缺一样就不该被注册：

1. **声明式契约**（``ToolSpec.params``）——调用方不需要读实现就能知道怎么用；
2. **权限等级**（``danger``）——``read`` / ``write`` / ``exec``，写和跑要能被策略拦；
3. **执行上下文**（``ToolContext``）——工具不能自己去找全局变量；
4. **结果对象**（``ToolResult``）——成功与失败同构，循环层才能统一处理；
5. **审计**——每次调用进 trace，失败才有据可查。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Config
    from ..memory.kstar import KSTARMemory

DANGER_LEVELS = ("read", "write", "exec")


@dataclass
class Param:
    name: str
    type: str = "string"
    required: bool = False
    desc: str = ""
    default: Any = None

    def schema(self) -> dict[str, Any]:
        out = {"type": self.type, "required": self.required, "desc": self.desc}
        if self.default is not None:
            out["default"] = self.default
        return out


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    params: list[Param] = field(default_factory=list)
    danger: str = "read"
    timeout: float = 10.0

    def __post_init__(self) -> None:
        if self.danger not in DANGER_LEVELS:
            raise ValueError(f"未知危险等级：{self.danger}")

    def signature(self) -> str:
        args = ", ".join(
            f"{p.name}{'=' + repr(p.default) if p.default is not None else ''}" for p in self.params
        )
        return f"{self.name}({args})"

    def help_line(self) -> str:
        return f"{self.name:<16} [{self.danger:<5}] {self.description}"


@dataclass
class ToolResult:
    tool: str
    ok: bool
    data: Any = None
    error: str = ""
    ms: float = 0.0
    args: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def summary(self, limit: int = 70) -> str:
        if not self.ok:
            return f"✗ {self.tool}: {self.error[:limit]}"
        return f"✓ {self.tool}: {self.note or _brief(self.data, limit)}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "ms": round(self.ms, 2),
            "args": self.args,
            "note": self.note,
        }


def _brief(data: Any, limit: int) -> str:
    if isinstance(data, list):
        return f"{len(data)} 项"
    if isinstance(data, dict):
        keys = "、".join(list(data)[:4])
        return f"{{{'、'.join(list(data)[:4])}{'…' if len(data) > 4 else ''}}}" if keys else "{}"
    text = " ".join(str(data).split()) if data is not None else "（空）"
    return text[:limit] + ("…" if len(text) > limit else "")


class ToolError(Exception):
    """工具内部抛这个，registry 会把它变成 ok=False 的结果（而不是让循环崩掉）。"""


@dataclass
class ToolContext:
    """工具能看到的世界。刻意收窄：只有配置、记忆、技能、工具和当前运行 id。"""

    config: "Config"
    memory: "KSTARMemory"
    run_id: str = ""
    skills: Any = None
    allow_write: bool = True
    tools: Any = None  # 工具可以回调别的工具（技能脚手架需要），但仍是同一套权限闸门

    def rel(self, path: str | Path) -> str:
        return self.config.rel(path)

    def elapsed(self) -> float:
        return time.perf_counter()
