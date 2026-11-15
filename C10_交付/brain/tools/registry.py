"""工具注册表：契约校验、权限闸门、超时、熔断、审计。

三个机制值得单独说：

**权限闸门**：``read`` 永远放行；``write``/``exec`` 受 ``ctx.allow_write`` 与
``--no-write`` 控制。这样 ``--dry-run`` 是真的不写，而不是"写了但假装没写"。

**熔断**：同一个工具连续失败 3 次就临时禁用。理由不是性能，是**防止循环空转**：
规划器如果反复挑同一个必败的工具，没有熔断的话整轮预算会被烧光。

**软超时**：纯函数工具用不到；``git`` 这类子进程工具自己有 timeout。
registry 仍然记录耗时并对超时阈值给出标记，但**不会强杀线程**——
Python 里杀线程本身就是不安全的，假装能杀比不杀更危险。
"""

from __future__ import annotations

import time
from typing import Any, Iterable

from .base import Param, ToolContext, ToolResult, ToolSpec

BREAKER_THRESHOLD = 3


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._fail_streak: dict[str, int] = {}
        self._disabled: set[str] = set()
        self.calls: list[ToolResult] = []

    # -- 注册 ----------------------------------------------------------
    def register(self, spec: ToolSpec) -> ToolSpec:
        if not spec.name or " " in spec.name:
            raise ValueError(f"工具名不合法：{spec.name!r}")
        self._tools[spec.name] = spec
        return spec

    def tool(self, name: str, description: str, params: Iterable[Param] | None = None, danger: str = "read"):
        """装饰器形式注册，减少样板。"""

        def deco(fn):
            self.register(
                ToolSpec(name=name, description=description, handler=fn, params=list(params or []), danger=danger)
            )
            return fn

        return deco

    # -- 查询 ----------------------------------------------------------
    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[n] for n in sorted(self._tools)]

    def disabled(self) -> list[str]:
        return sorted(self._disabled)

    def enable_all(self) -> None:
        self._disabled.clear()
        self._fail_streak.clear()

    def describe(self) -> str:
        lines = [spec.help_line() for spec in self.specs()]
        if self._disabled:
            lines.append("（熔断中：" + "、".join(self.disabled()) + "）")
        return "\n".join(lines)

    # -- 调用 ----------------------------------------------------------
    def call(self, name: str, args: dict[str, Any] | None = None, ctx: ToolContext | None = None) -> ToolResult:
        args = dict(args or {})
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(tool=name, ok=False, error=f"未知工具：{name}", args=args)
        if name in self._disabled:
            return ToolResult(tool=name, ok=False, error="工具处于熔断状态，已跳过", args=args)

        problem = self._validate(spec, args)
        if problem:
            return self._finish(ToolResult(tool=name, ok=False, error=problem, args=args))

        if spec.danger != "read" and ctx is not None and not ctx.allow_write:
            return ToolResult(tool=name, ok=False, error="当前为只读模式（--no-write），写/执行类工具被拒绝", args=args)

        start = time.perf_counter()
        try:
            data = spec.handler(ctx, **args) if _takes_ctx(spec.handler) else spec.handler(**args)
            result = ToolResult(tool=name, ok=True, data=data, args=args)
        except TypeError as exc:  # 参数名对不上的典型错误，单独给清楚的提示
            result = ToolResult(tool=name, ok=False, error=f"参数错误：{exc}", args=args)
        except Exception as exc:  # noqa: BLE001 —— 工具边界必须兜住一切
            result = ToolResult(tool=name, ok=False, error=f"{type(exc).__name__}: {exc}", args=args)
        result.ms = (time.perf_counter() - start) * 1000
        if result.ms > spec.timeout * 1000:
            result.note = (result.note + f"（超时阈值 {spec.timeout}s）").strip()
        return self._finish(result)

    def _finish(self, result: ToolResult) -> ToolResult:
        self.calls.append(result)
        if result.ok:
            self._fail_streak[result.tool] = 0
        else:
            streak = self._fail_streak.get(result.tool, 0) + 1
            self._fail_streak[result.tool] = streak
            if streak >= BREAKER_THRESHOLD:
                self._disabled.add(result.tool)
        return result

    @staticmethod
    def _validate(spec: ToolSpec, args: dict[str, Any]) -> str:
        declared = {p.name for p in spec.params}
        unknown = [k for k in args if k not in declared]
        if unknown:
            return f"未知参数：{'、'.join(unknown)}（可用：{'、'.join(sorted(declared)) or '无'}）"
        for p in spec.params:
            if p.required and p.name not in args:
                return f"缺少必填参数：{p.name}（{p.desc}）"
        return ""

    # -- 统计 ----------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        total = len(self.calls)
        ok = sum(1 for c in self.calls if c.ok)
        per: dict[str, dict[str, int]] = {}
        for call in self.calls:
            slot = per.setdefault(call.tool, {"calls": 0, "ok": 0})
            slot["calls"] += 1
            slot["ok"] += 1 if call.ok else 0
        return {
            "total": total,
            "ok": ok,
            "failed": total - ok,
            "success_rate": round(ok / total, 3) if total else 0.0,
            "per_tool": per,
            "disabled": self.disabled(),
        }


def _takes_ctx(fn) -> bool:
    code = getattr(fn, "__code__", None)
    if code is None:
        return False
    return "ctx" in code.co_varnames[: code.co_argcount]
