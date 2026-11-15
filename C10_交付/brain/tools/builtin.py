"""内置工具：9 个，刻意少。

每加一个工具，循环层就多一种走错的可能。所以这里只放"每天真的会用"的：

========================  ======  ============================================
工具                      等级    干什么
========================  ======  ============================================
``time.now``              read    当前时间（模型对时间的直觉不可信）
``memory.search``         read    在 KSTAR 四层里检索（带分数与命中词）
``memory.get``            read    按 id 取一条（溯源用）
``memory.write``          write   写一条记忆（默认 S，可指定层）
``memory.promote``        write   跑一遍沉淀规则（默认 dry-run）
``task.add`` / ``task.list``/``task.done``  write/read  任务层状态机
``fs.read`` / ``fs.list`` read    只读地看项目文件
``git.status``            exec    只读 git（status/log/diff --stat）
``skill.run``             exec    调用技能层
========================  ======  ============================================

**没有``shell.run``**。一个"能跑任意命令"的工具会把前面所有权限设计变成装饰品；
真需要跑命令时，写成技能（技能是显式的、可 review 的），而不是给循环层一把万能钥匙。
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from pathlib import Path
from typing import Any

from ..memory.promote import apply_proposal, collect_proposals
from ..util import iso, truncate
from .base import Param, ToolContext, ToolError
from .registry import ToolRegistry

MAX_READ_BYTES = 200_000
ALLOWED_GIT = {"status", "log", "diff"}


def _safe_path(ctx: ToolContext, rel: str) -> Path:
    """把用户给的相对路径钉死在项目根内。``..`` 越界一律拒绝。"""

    root = ctx.config.root.resolve()
    target = (root / (rel or ".")).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ToolError(f"路径越界：{rel!r} 不在项目根内") from exc
    return target


def _parse_layers(raw: str) -> list[str] | None:
    if not raw:
        return None
    parts = [p.strip().upper() for p in str(raw).replace("，", ",").split(",") if p.strip()]
    bad = [p for p in parts if p not in {"K", "S", "T", "AR"}]
    if bad:
        raise ToolError(f"未知记忆层：{'、'.join(bad)}（可用 K/S/T/AR）")
    return parts


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
def build_registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool("time.now", "当前时间（本地时区 UTC+8）", danger="read")
    def time_now(ctx: ToolContext) -> dict[str, Any]:
        now = iso()
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][_dt.date.fromisoformat(now[:10]).weekday()]
        return {"iso": now, "date": now[:10], "weekday": weekday}

    @reg.tool(
        "memory.search",
        "在 KSTAR 四层记忆里检索，返回分数与命中词",
        [
            Param("query", required=True, desc="查询语句"),
            Param("k", "integer", desc="返回条数", default=5),
            Param("layers", desc="限定层，逗号分隔，如 K,T", default=""),
            Param("echo", "boolean", desc="是否包含'问句回声'记录（默认不含）", default=False),
        ],
        danger="read",
    )
    def memory_search(ctx: ToolContext, query: str, k: int = 5, layers: str = "", echo: bool = False) -> list[dict[str, Any]]:
        hits = ctx.memory.search(
            str(query), top_k=int(k or 5), layers=_parse_layers(layers), include_echo=bool(echo)
        )
        return [
            {
                "id": h.record.id,
                "layer": h.record.layer,
                "title": h.record.title,
                "score": h.score,
                "matched": h.matched[:8],
                "text": truncate(h.record.text, 240),
            }
            for h in hits
        ]

    @reg.tool(
        "memory.get",
        "按 id 读取一条记忆（含来源与元数据）",
        [Param("id", required=True, desc="记录 id，如 k-20261115-ab12cd")],
        danger="read",
    )
    def memory_get(ctx: ToolContext, id: str) -> dict[str, Any]:  # noqa: A002
        rec = ctx.memory.get(str(id))
        if rec is None:
            raise ToolError(f"没有这条记录：{id}")
        return rec.to_dict()

    @reg.tool(
        "memory.write",
        "写一条记忆（默认 S 情境层）",
        [
            Param("text", required=True, desc="正文"),
            Param("layer", desc="K/S/T/AR", default="S"),
            Param("title", desc="标题", default=""),
            Param("tags", desc="逗号分隔标签", default=""),
            Param("importance", "number", desc="0~1", default=0.5),
        ],
        danger="write",
    )
    def memory_write(
        ctx: ToolContext, text: str, layer: str = "S", title: str = "", tags: str = "", importance: float = 0.5
    ) -> dict[str, Any]:
        tags_list = [t.strip() for t in str(tags).replace("，", ",").split(",") if t.strip()]
        rec = ctx.memory.write(
            layer or "S",
            str(text),
            title=title,
            tags=tags_list,
            source=ctx.run_id or "tool",
            importance=float(importance),
            dedupe=True,
        )
        return {"id": rec.id, "layer": rec.layer, "title": rec.title}

    @reg.tool(
        "memory.promote",
        "跑一遍沉淀规则：AR→K 沉淀、S 归档（默认只看不写）",
        [Param("apply", "boolean", desc="是否真的写入", default=False)],
        danger="write",
    )
    def memory_promote(ctx: ToolContext, apply: bool = False) -> dict[str, Any]:
        proposals = collect_proposals(ctx.memory)
        applied = 0
        if apply:
            applied = sum(1 for p in proposals if apply_proposal(ctx.memory, p))
        return {"proposals": [p.line() for p in proposals], "applied": applied}

    @reg.tool(
        "task.add",
        "新增一个任务（T 层）",
        [
            Param("title", required=True, desc="任务名"),
            Param("detail", desc="补充说明", default=""),
            Param("due", desc="截止日 YYYY-MM-DD", default=""),
        ],
        danger="write",
    )
    def task_add(ctx: ToolContext, title: str, detail: str = "", due: str = "") -> dict[str, Any]:
        rec = ctx.memory.write(
            "T",
            detail or title,
            title=str(title),
            tags=["task"],
            source=ctx.run_id or "tool",
            importance=0.7,
            status="open",
            meta={"due": due, "started": iso()},
        )
        return {"id": rec.id, "title": rec.title, "status": rec.status}

    @reg.tool(
        "task.list",
        "列出任务（默认只看未完成）",
        [Param("status", desc="open/done/all", default="open")],
        danger="read",
    )
    def task_list(ctx: ToolContext, status: str = "open") -> list[dict[str, Any]]:
        status = (status or "open").lower()
        rows = []
        for rec in sorted(ctx.memory.all("T"), key=lambda r: r.created, reverse=True):
            if status != "all" and rec.status != status:
                continue
            rows.append(
                {"id": rec.id, "title": rec.title, "status": rec.status, "due": rec.meta.get("due", ""), "created": rec.created[:10]}
            )
        return rows

    @reg.tool(
        "task.done",
        "把任务标记完成，并自动生成一条 AR 行动记录",
        [Param("id", required=True, desc="任务 id 或标题前缀")],
        danger="write",
    )
    def task_done(ctx: ToolContext, id: str) -> dict[str, Any]:  # noqa: A002
        target = ctx.memory.get(str(id))
        if target is None or target.layer != "T":
            needle = str(id).strip()
            for rec in ctx.memory.all("T"):
                if rec.title.startswith(needle) or needle in rec.title:
                    target = rec
                    break
        if target is None or target.layer != "T":
            raise ToolError(f"找不到任务：{id}")
        from ..memory.promote import task_done_to_action

        ctx.memory.update(target.id, status="done", importance=0.4)
        ar = task_done_to_action(ctx.memory, target)
        return {"task": target.id, "status": "done", "action_record": ar.id}

    @reg.tool(
        "fs.read",
        "只读地读项目内的文本文件（默认前 60 行）",
        [Param("path", required=True, desc="相对路径"), Param("lines", "integer", desc="行数", default=60)],
        danger="read",
    )
    def fs_read(ctx: ToolContext, path: str, lines: int = 60) -> dict[str, Any]:
        target = _safe_path(ctx, str(path))
        if not target.is_file():
            raise ToolError(f"不是文件：{path}")
        data = target.read_bytes()[:MAX_READ_BYTES]
        text = data.decode("utf-8", errors="replace")
        rows = text.splitlines()
        return {
            "path": ctx.rel(target),
            "lines": len(rows),
            "truncated": len(rows) > int(lines),
            "text": "\n".join(rows[: int(lines)]),
        }

    @reg.tool(
        "fs.list",
        "列出项目内某目录的文件",
        [Param("path", desc="相对路径", default="."), Param("limit", "integer", default=40)],
        danger="read",
    )
    def fs_list(ctx: ToolContext, path: str = ".", limit: int = 40) -> list[dict[str, Any]]:
        target = _safe_path(ctx, str(path))
        if not target.is_dir():
            raise ToolError(f"不是目录：{path}")
        rows = []
        for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))[: int(limit)]:
            rows.append({"name": child.name, "dir": child.is_dir(), "bytes": child.stat().st_size if child.is_file() else 0})
        return rows

    @reg.tool(
        "git.status",
        "只读 git：status / log / diff --stat",
        [Param("sub", desc="status|log|diff", default="status"), Param("limit", "integer", default=10)],
        danger="exec",
    )
    def git_status(ctx: ToolContext, sub: str = "status", limit: int = 10) -> dict[str, Any]:
        sub = (sub or "status").lower()
        if sub not in ALLOWED_GIT:
            raise ToolError(f"git 只允许：{'、'.join(sorted(ALLOWED_GIT))}")
        cmd = ["git", "-C", str(ctx.config.root)]
        if sub == "status":
            cmd += ["status", "--porcelain=v1", "-b"]
        elif sub == "log":
            cmd += ["log", f"-{max(1, int(limit))}", "--oneline", "--no-decorate"]
        else:
            cmd += ["diff", "--stat"]
        try:
            proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=8)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError(f"git 执行失败：{exc}") from exc
        text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        rows = [line for line in text.splitlines() if line.strip()]
        return {"sub": sub, "lines": rows[: int(limit)], "truncated": len(rows) > int(limit)}

    @reg.tool(
        "skill.run",
        "调用技能层的一个技能",
        [Param("name", required=True, desc="技能名"), Param("args", desc="JSON 字符串或纯文本参数", default="{}")],
        danger="exec",
    )
    def skill_run(ctx: ToolContext, name: str, args: str = "{}") -> dict[str, Any]:
        if ctx.skills is None:
            raise ToolError("本次运行没有挂载技能层")
        parsed: Any
        text = str(args or "").strip()
        if text in ("", "{}"):
            parsed = {}
        elif text.startswith("{"):
            try:
                parsed = json.loads(text)
            except ValueError as exc:
                raise ToolError(f"args 不是合法 JSON：{exc}") from exc
        else:
            parsed = {"query": text, "text": text}
        result = ctx.skills.run(str(name), parsed, ctx=ctx)
        if not result.ok:
            # 技能内部失败必须变成工具失败：否则循环层会把一次失败记成成功，
            # 熔断、降级、复盘全部跟着失真。
            raise ToolError(f"{result.skill}: {result.error}")
        return {
            "skill": result.skill,
            "ok": result.ok,
            "mode": result.mode,
            "outputs": result.outputs,
            "ms": round(result.ms, 2),
        }

    return reg
