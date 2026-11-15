"""技能运行时：加载 handler、执行、记账。

技能可以调工具（``ctx.tools.call``），但不应该自己去找全局状态——
所以 handler 只收到两样东西：``ctx``（配置/记忆/工具/运行 id）和 ``args``（dict）。

记账很重要：``used / ok / failed / last_used`` 是 ``brain evolve`` 判断
"这个技能还活着吗"的唯一依据。没有账本的技能层，三个月后没人知道哪些能删。
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any

from ..config import Config
from ..util import append_jsonl, iso, read_jsonl
from .loader import SkillLoader
from .model import Skill, SkillResult


class SkillRuntime:
    def __init__(self, config: Config | None = None, loader: SkillLoader | None = None):
        self.config = config or Config.load()
        self.loader = loader or SkillLoader(self.config)
        self._modules: dict[str, Any] = {}

    # -- 执行 ----------------------------------------------------------
    def run(self, name: str, args: dict[str, Any] | None = None, *, ctx: Any = None) -> SkillResult:
        import time

        args = dict(args or {})
        start = time.perf_counter()
        try:
            skill = self.loader.require(name)
        except KeyError as exc:
            return SkillResult(skill=name, ok=False, error=str(exc))

        if skill.status == "broken":
            return self._finish(skill, SkillResult(skill=skill.name, ok=False, error=skill.error), start, ctx)

        if not skill.executable:
            # 纯说明型技能：不假装执行，把"该怎么用"返回给调用方
            result = SkillResult(
                skill=skill.name,
                ok=True,
                mode="prompt",
                outputs={
                    "summary": "说明型技能（无 handler），已返回使用说明",
                    "instructions": (skill.body or skill.description)[:600],
                },
            )
            return self._finish(skill, result, start, ctx)

        module = self._load_module(skill)
        runner = getattr(module, "run", None)
        if not callable(runner):
            return self._finish(
                skill,
                SkillResult(skill=skill.name, ok=False, error=f"{skill.handler} 里没有可调用的 run(ctx, args)"),
                start,
                ctx,
            )

        try:
            raw = runner(ctx, args)
        except Exception as exc:  # noqa: BLE001 —— 技能是用户代码，边界必须兜住
            detail = traceback.format_exc(limit=3)
            self._log(skill, False, 0.0, error=f"{type(exc).__name__}: {exc}", ctx=ctx)
            return SkillResult(
                skill=skill.name,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                ms=(time.perf_counter() - start) * 1000,
                outputs={"traceback": detail},
            )

        outputs = raw if isinstance(raw, dict) else {"result": raw}
        return self._finish(skill, SkillResult(skill=skill.name, ok=True, outputs=outputs), start, ctx)

    # -- 内部 ----------------------------------------------------------
    def _finish(self, skill: Skill, result: SkillResult, start: float, ctx: Any) -> SkillResult:
        import time

        result.ms = (time.perf_counter() - start) * 1000
        self._log(skill, result.ok, result.ms, error=result.error, ctx=ctx)
        return result

    def _log(self, skill: Skill, ok: bool, ms: float, *, error: str = "", ctx: Any = None) -> None:
        append_jsonl(
            self.config.db_dir / "skill_usage.jsonl",
            {
                "ts": iso(),
                "skill": skill.name,
                "ok": ok,
                "ms": round(ms, 2),
                "mode": skill.status,
                "run_id": getattr(ctx, "run_id", ""),
                "error": error[:200],
            },
        )

    def _load_module(self, skill: Skill) -> Any:
        path = skill.dir / skill.handler
        key = f"{skill.name}:{path}"
        if key in self._modules:
            return self._modules[key]
        module_name = f"brain_skill_{skill.name.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载技能模块：{path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self._modules[key] = module
        return module

    # -- 统计 ----------------------------------------------------------
    def usage(self) -> list[dict[str, Any]]:
        return read_jsonl(self.config.db_dir / "skill_usage.jsonl")

    def stats(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in self.usage():
            name = str(row.get("skill") or "?")
            slot = out.setdefault(name, {"calls": 0, "ok": 0, "failed": 0, "last": "", "ms": 0.0})
            slot["calls"] += 1
            slot["ok" if row.get("ok") else "failed"] += 1
            slot["last"] = str(row.get("ts") or slot["last"])
            slot["ms"] = round(slot["ms"] + float(row.get("ms") or 0.0), 1)
        for slot in out.values():
            slot["success_rate"] = round(slot["ok"] / slot["calls"], 3) if slot["calls"] else 0.0
        return out

    def table(self) -> str:
        from ..util import table

        skills = self.loader.load_all()
        usage = self.stats()
        rows = []
        for s in skills:
            u = usage.get(s.name, {})
            rows.append(
                [s.name, s.status, str(u.get("calls", 0)), str(u.get("ok", 0)), str(u.get("failed", 0)), (u.get("last") or "-")[:16]]
            )
        return table(rows, ["技能", "状态", "调用", "成功", "失败", "最近一次"])
