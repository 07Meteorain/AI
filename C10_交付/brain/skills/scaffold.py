"""手工创建技能：给一个空壳，但把"该填什么"写在文件里。

``brain skill new`` 生成的骨架故意**能跑但什么都不做**（返回
``{"summary": "尚未实现"}``）。理由：一个一运行就报 ImportError 的模板，
会让人以为系统坏了；一个安静地返回占位结果的模板，至少能被测试发现"还没写"。
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..util import atomic_write_text, iso, slugify

SKILL_MD = """---
name: {name}
description: {description}
version: 0.1
when: {when}
inputs:
  query: 主要输入（一句话说清要处理什么）
tags: {name}
tools:
handler: handler.py
---

# {name}

> 由 `brain skill new` 生成于 {generated_at}。填完下面四节再改 `version` 到 1.0。

## 解决什么问题

（一句话。如果一句话说不清，说明它不是一件事，是两个。）

## 输入 / 输出

- 输入：`query` ——
- 输出：`summary`（必填）、以及调用方要用的结构化字段。

## 步骤

1.
2.

## 什么时候会失败

（写出至少一个你见过的失败场景，以及失败时应该返回什么。）
"""

HANDLER = '''"""技能实现骨架。约定：``run(ctx, args) -> dict``，返回 dict，必须有 ``summary``。"""

from __future__ import annotations

from typing import Any


def run(ctx, args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {{}}
    query = str(args.get("query") or "").strip()

    # 可以调工具：ctx.tools.call("memory.search", {{"query": query, "k": 3}}, ctx)
    # 可以写记忆：ctx.memory.write("K", text, title="…", source=ctx.run_id)
    return {{
        "summary": "尚未实现" + (f"：{{query}}" if query else ""),
        "todo": True,
    }}
'''


def create_skill(
    config: Config,
    name: str,
    *,
    description: str = "（待填写）",
    when: str = "（待填写）",
) -> dict[str, object]:
    slug = slugify(name, maxlen=40, default="new-skill")
    target: Path = config.skills_dir / slug
    if target.exists():
        return {"ok": False, "reason": f"技能已存在：{slug}", "path": str(target)}
    target.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        target / "SKILL.md",
        SKILL_MD.format(name=slug, description=description, when=when, generated_at=iso()),
    )
    atomic_write_text(target / "handler.py", HANDLER)
    return {"ok": True, "name": slug, "path": str(target), "reason": f"已创建技能骨架 {slug}"}
