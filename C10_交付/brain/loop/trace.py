"""运行轨迹：每一次「想—做—看—记」的完整留痕。

**为什么单独一层文件**：出问题时，你需要回答的不是"它说了什么"，而是
"它调了哪个工具、传了什么参数、失败在哪一步、当时记忆里有什么"。
没有 trace 的 agent 只能靠复现，而复现依赖当时的记忆——记忆已经变了。

trace 按天一个 JSONL 文件：一天的运行坏了不会影响别的天，直接 ``tail`` 就能看。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..config import Config
from ..util import append_jsonl, iso, new_id, read_jsonl, stable_hash


@dataclass
class Step:
    index: int
    tool: str
    args: dict[str, Any]
    ok: bool
    ms: float
    note: str = ""
    error: str = ""
    data_digest: str = ""

    def line(self) -> str:
        mark = "✓" if self.ok else "✗"
        detail = self.note or self.error
        return f"{self.index}. {mark} {self.tool}  {detail[:80]}"


@dataclass
class RunTrace:
    run_id: str
    session: str
    input: str
    intent: str
    confidence: float
    started: str
    ended: str = ""
    steps: list[Step] = field(default_factory=list)
    answer: str = ""
    evidence: list[str] = field(default_factory=list)
    recall_hits: int = 0
    status: str = "ok"  # ok / degraded / failed
    degraded: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return sum(s.ms for s in self.steps)

    def add(self, step: Step) -> None:
        self.steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration_ms"] = round(self.duration_ms, 2)
        return data

    def brief(self) -> str:
        return (
            f"{self.run_id}  [{self.status}]  intent={self.intent}({self.confidence:.2f})  "
            f"{len(self.steps)} 步  {self.duration_ms:.0f}ms"
        )


def new_trace(session: str, text: str, intent: str, confidence: float) -> RunTrace:
    return RunTrace(
        run_id=new_id("run", seed=stable_hash(text, 4)),
        session=session,
        input=text,
        intent=intent,
        confidence=confidence,
        started=iso(),
    )


class TraceStore:
    """按天落盘的 trace 仓库。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()

    def _path(self, stamp: str) -> Path:
        return self.config.traces_dir / f"{stamp[:10]}.jsonl"

    def append(self, trace: RunTrace) -> Path:
        path = self._path(trace.started)
        path.parent.mkdir(parents=True, exist_ok=True)
        append_jsonl(path, trace.to_dict())
        return path

    def files(self) -> list[Path]:
        if not self.config.traces_dir.is_dir():
            return []
        return sorted(self.config.traces_dir.glob("*.jsonl"))

    def all(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in self.files():
            rows.extend(read_jsonl(path))
        rows.sort(key=lambda r: str(r.get("started", "")))
        return rows

    def recent(self, n: int = 5) -> list[dict[str, Any]]:
        return self.all()[-n:]

    def count(self) -> int:
        return len(self.all())
