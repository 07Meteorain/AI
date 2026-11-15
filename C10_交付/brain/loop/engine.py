"""循环：一次把事做完的完整过程。

    classify → plan → (call tool → observe) × N → compose → reflect → trace

四条硬规则，每条都对应一种真实翻车方式：

1. **步数上限**（``max_steps``）。没有上限的循环，会在一棵错的树上走到底。
2. **工具失败不中断，只记录**。一次 ``fs.read`` 失败不该让整轮回答消失——
   用户要的是答案，不是异常栈；但失败必须进 trace，否则"偶尔答错"永远查不出来。
3. **反思先于回答**。先写 AR 再返回，否则程序崩在半路时，这段经历就丢了。
4. **只读模式真的只读**。``--no-write`` 时 ctx.allow_write=False，工具层直接拒写，
   不是"写了再回滚"——回滚在进程被杀时不会发生。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..config import Config
from ..memory.kstar import KSTARMemory
from ..tools import ToolContext, ToolRegistry
from ..util import iso, truncate
from .compose import compose
from .planner import Intent, RulePlanner
from .trace import RunTrace, Step, TraceStore, new_trace


@dataclass
class RunResult:
    trace: RunTrace
    answer: str
    evidence: list[str] = field(default_factory=list)
    records: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": self.trace.to_dict(),
            "answer": self.answer,
            "evidence": self.evidence,
            "records": self.records,
        }


class AgentLoop:
    def __init__(
        self,
        config: Config,
        memory: KSTARMemory,
        tools: ToolRegistry,
        skills: Any = None,
        *,
        planner: Any = None,
        trace_store: TraceStore | None = None,
        mode: str = "offline",
        provider: Any = None,
    ):
        self.config = config
        self.memory = memory
        self.tools = tools
        self.skills = skills
        self.planner = planner or RulePlanner()
        self.traces = trace_store or TraceStore(config)
        self.mode = mode
        self.provider = provider

    # ------------------------------------------------------------------
    def run(
        self,
        text: str,
        *,
        session: str = "cli",
        allow_write: bool | None = None,
        persist: bool = True,
        force_intent: Intent | None = None,
    ) -> RunResult:
        allow_write = self.config.write_memory if allow_write is None else allow_write
        intent: Intent = force_intent or self.planner.classify(text)
        trace = new_trace(session, text, intent.kind, intent.confidence)
        trace.meta["rationale"] = intent.rationale
        trace.meta["mode"] = self.mode

        ctx = ToolContext(
            config=self.config,
            memory=self.memory,
            run_id=trace.run_id,
            skills=self.skills,
            allow_write=allow_write,
            tools=self.tools,
        )

        try:
            plan = self.planner.plan(intent, text, context={"memory": self.memory, "tools": self.tools, "skills": self.skills})
            plan = list(plan)[: max(0, self.config.max_steps)]
            trace.meta["plan"] = [str(s) for s in plan]
            results = []
            for idx, planned in enumerate(plan, 1):
                result = self.tools.call(planned.tool, planned.args, ctx)
                results.append(result)
                trace.add(
                    Step(
                        index=idx,
                        tool=planned.tool,
                        args=planned.args,
                        ok=result.ok,
                        ms=result.ms,
                        note=result.note or (planned.why if result.ok else ""),
                        error=result.error,
                    )
                )

            answer, evidence = compose(intent, text, results, mode=self.mode)
            answer = self._maybe_generate(text, results, answer, trace)
            trace.answer = answer
            trace.evidence = evidence
            trace.recall_hits = _recall_hits(results)
            failed = [s for s in trace.steps if not s.ok]
            trace.status = "ok" if not failed else ("degraded" if len(failed) < len(trace.steps) else "failed")
            if getattr(self.planner, "fallback", False):
                trace.meta["fallback"] = True
                trace.meta["degraded_reasons"] = list(getattr(self.planner, "degraded_reasons", [])[-4:])
            if self.mode != "offline":
                trace.degraded = bool(trace.meta.get("fallback"))

            self._reflect(trace, intent, results, allow_write)
            return RunResult(trace=trace, answer=answer, evidence=evidence)
        except Exception as exc:  # noqa: BLE001 —— 循环边界：宁可返回半个结果，也不要丢 trace
            trace.status = "failed"
            trace.answer = f"运行失败：{type(exc).__name__}: {exc}"
            trace.meta["exception"] = trace.answer
            return RunResult(trace=trace, answer=trace.answer)
        finally:
            trace.ended = iso()
            if persist:
                self.traces.append(trace)

    # ------------------------------------------------------------------
    def _maybe_generate(self, text: str, results: list[Any], fallback_answer: str, trace: RunTrace) -> str:
        """LLM 模式下让模型基于证据作答；失败则保留抽取式回答并标降级。"""

        if self.mode == "offline" or self.provider is None:
            return fallback_answer
        blob = _evidence_blob(results)
        if not blob.strip():
            # 没有证据也让模型回答，但明确告诉它"手上什么都没有"。
            # 直接跳过生成会让"记忆里没有"这件事永远以模板口吻出现，
            # 用户分不清是检索为空还是系统不会说话。
            blob = "（本次没有检索到任何证据）"
        try:
            generated = self.provider.answer(text, blob)
        except Exception as exc:  # noqa: BLE001
            generated = None
            trace.meta["answer_error"] = f"{type(exc).__name__}: {exc}"
        if not generated:
            trace.meta["fallback"] = True
            return fallback_answer
        return (
            generated.strip()
            + f"\n\n— LLM 模式：回答由 {getattr(self.provider, 'model', 'model')} 基于下列证据生成；"
            + f"未经人工改写，运行 id `{trace.run_id}`。"
        )

    # ------------------------------------------------------------------
    def _reflect(self, trace: RunTrace, intent: Intent, results: list[Any], allow_write: bool) -> None:
        """把这次经历写回记忆。AR 是"我做过什么"，S 是"当时是什么场景"。"""

        if not allow_write:
            trace.meta["reflected"] = False
            return

        ok_steps = [s for s in trace.steps if s.ok]
        workflow = ">".join(s.tool for s in trace.steps)
        error = next((s.error for s in trace.steps if not s.ok), "")
        # 提问本身会被存档，但存档不该在下次被当成"证据"。
        # 打上 echo 标记，检索时默认跳过——否则同一句话问两遍，
        # 第二遍永远"命中"的是第一遍的问句。这个 bug 在演示里真的出现过。
        echo = intent.kind in ("recall", "chat")
        ar_text = (
            f"意图 {intent.kind}（{intent.rationale}）｜输入：{truncate(trace.input, 60)}｜"
            f"执行 {len(trace.steps)} 步（成功 {len(ok_steps)}）｜结果：{truncate(trace.answer, 80)}"
        )
        meta = {
            "intent": intent.kind,
            "workflow": workflow,
            "steps": [s.tool for s in trace.steps],
            "ok": trace.status == "ok",
            "error": error,
            "session": trace.session,
            "run_id": trace.run_id,
            "duration_ms": round(trace.duration_ms, 2),
            "recall_hits": trace.recall_hits,
            "echo": echo,
        }
        self.memory.write(
            "AR",
            ar_text,
            title=f"{intent.kind}：{truncate(trace.input, 32)}",
            tags=[intent.kind, trace.status],
            source=trace.run_id,
            importance=0.55 if trace.status == "ok" else 0.7,
            status="ok" if trace.status == "ok" else "failed",
            meta=meta,
        )
        self.memory.write(
            "S",
            f"[{trace.session}] {trace.input}\n→ {truncate(trace.answer, 160)}",
            title=truncate(trace.input, 28),
            tags=["会话", intent.kind],
            source=trace.run_id,
            importance=0.45,
            meta={"run_id": trace.run_id, "intent": intent.kind, "session": trace.session, "echo": echo},
        )
        trace.meta["reflected"] = True


def _recall_hits(results: list[Any]) -> int:
    for res in results:
        if getattr(res, "tool", "") == "memory.search" and getattr(res, "ok", False) and isinstance(res.data, list):
            return len(res.data)
    return 0


def _evidence_blob(results: list[Any], limit: int = 8000) -> str:
    """给模型的证据块。带 id，这样模型引用时可以被核对。"""

    lines: list[str] = []
    for res in results:
        if not getattr(res, "ok", False):
            continue
        if getattr(res, "tool", "") == "memory.search" and isinstance(res.data, list):
            for hit in res.data:
                lines.append(f"- [{hit['id']}] ({hit['layer']}) {hit['title']}：{hit['text']}")
        elif res.data is not None:
            try:
                payload = json.dumps(res.data, ensure_ascii=False)
            except (TypeError, ValueError):
                payload = str(res.data)
            lines.append(f"- {res.tool}: {payload[:400]}")
    return "\n".join(lines)[:limit]
