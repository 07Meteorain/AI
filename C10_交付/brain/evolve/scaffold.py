"""技能脚手架：把重复的工做序列变成一份能直接跑的 SKILL.md + handler.py。

**这是"让系统每次使用都在进化"里唯一真的会改代码的一步**，所以格外保守：

* 只写进 ``skills/_drafts/``，不碰人工维护的 ``skills/``；
* 草稿 ``version=0.1``、``status=draft``，回执与清单里都标"草稿"；
* 生成的 handler 只回放**已记录的工具调用**，不含任何新逻辑；
* 生成后不自动启用——要人看过 ``SKILL.md`` 再决定。

一个会悄悄给自己加代码的系统，迟早会长出没人能审计的行为。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..config import Config
from ..util import atomic_write_text, iso, slugify, stable_hash, truncate

SAFE_STEP_TOOLS = {
    "memory.search",
    "memory.write",
    "memory.promote",
    "time.now",
    "task.add",
    "task.list",
    "task.done",
    "fs.read",
    "fs.list",
    "git.status",
    "skill.run",
}

SKILL_TEMPLATE = """---
name: {name}
description: {description}
version: 0.1
when: 当你又要做一遍「{label}」这件事时
inputs:
  query: 本次的输入文本（会替换掉当初记录的那句话）
tags: auto, draft, {label}
tools: {tool_list}
handler: handler.py
---

# {name}

> 本技能由 `brain evolve` 从 {count} 次重复执行中自动生成，**未经人工审核**。
> 生成时间：{generated_at}

## 它复现的流程

```
{workflow_block}
```

## 为什么会有它

系统在 trace 里发现同一组工具被同样的顺序调用了 {count} 次：

{evidence_block}

所以把这条路径固定下来。以后再遇到同类任务，走技能只花 1 步，
而不是重新规划 {steps} 步。

## 什么时候不该用它

- 输入不是同一类任务时（本技能不做意图判断，它只回放流程）；
- 流程里含有本项目的临时状态时（比如某次特定的文件路径）。

## 怎么改进它

1. 读一遍 `handler.py`，把写死的参数改成真正有意义的输入；
2. 把 `version` 改成 1.0，移出 `_drafts/`；
3. 在 `tests/` 里加一条针对它的测试。
"""

HANDLER_TEMPLATE = '''"""自动生成的技能 handler —— 只回放已记录的工具调用，不含新逻辑。

由 ``brain evolve`` 于 {generated_at} 生成。
"""

from __future__ import annotations

from typing import Any

STEPS: list[dict[str, Any]] = {steps_repr}

WORKFLOW = {workflow!r}


def _fill(value: Any, query: str) -> Any:
    if isinstance(value, str):
        return value.replace("{{query}}", query)
    if isinstance(value, dict):
        return {{k: _fill(v, query) for k, v in value.items()}}
    if isinstance(value, list):
        return [_fill(v, query) for v in value]
    return value


def run(ctx, args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {{}}
    query = str(args.get("query") or args.get("text") or "")
    outputs = []
    failures = 0
    for step in STEPS:
        payload = _fill(step.get("args") or {{}}, query)
        result = ctx.tools.call(step["tool"], payload, ctx)
        if not result.ok:
            failures += 1
        outputs.append({{"tool": step["tool"], "ok": result.ok, "error": result.error}})
    return {{
        "summary": f"回放 {{len(STEPS)}} 步（失败 {{failures}}）",
        "workflow": WORKFLOW,
        "steps": outputs,
        "query": query,
    }}
'''


def draft_skill(
    config: Config,
    *,
    workflow: str,
    label: str,
    count: int,
    runs: list[dict[str, Any]],
    write: bool = True,
) -> dict[str, Any]:
    """从一条工作流签名生成草稿技能。

    ``write=False`` 时只计算"会生成什么"，一个字节都不落盘——
    ``brain evolve`` 默认必须是真的只读，而不是"写了再假装没写"。
    """

    tools = [t for t in workflow.split(">") if t]
    unsafe = [t for t in tools if t not in SAFE_STEP_TOOLS]
    if unsafe:
        return {"ok": False, "reason": f"流程含不可自动化的工具：{'、'.join(unsafe)}"}

    sample = runs[-1]
    steps = []
    for step in sample.get("steps") or []:
        args = {}
        for key, value in (step.get("args") or {}).items():
            if isinstance(value, str):
                # 把当初那句话换成占位符，技能才有输入
                text = str(sample.get("input") or "")
                value = value.replace(text, "{query}") if text else value
            args[key] = value
        steps.append({"tool": step.get("tool"), "args": args})

    name = _skill_name(label, workflow)
    target = config.drafts_dir / name
    if target.exists():
        return {"ok": False, "reason": f"草稿已存在：{name}", "name": name, "path": str(target)}

    tool_list = ", ".join(dict.fromkeys(tools))
    workflow_block = "\n".join(f"{i + 1}. {s['tool']}({json.dumps(s['args'], ensure_ascii=False)[:80]})" for i, s in enumerate(steps))
    evidence_block = "\n".join(
        f"- `{r.get('run_id', '?')}`  {truncate(str(r.get('input', '')), 44)}  → {truncate(str(r.get('answer', '')), 40)}"
        for r in runs[-3:]
    )

    if not write:
        return {
            "ok": True,
            "name": name,
            "path": str(target),
            "workflow": workflow,
            "steps": len(steps),
            "planned": True,
            "reason": f"（未落盘）将生成草稿技能 {name}（{len(steps)} 步，来自 {count} 次重复）",
        }

    target.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        target / "SKILL.md",
        SKILL_TEMPLATE.format(
            name=name,
            description=f"[草稿] 自动固化的工作流：{workflow}，来自 {count} 次重复。",
            label=label,
            count=count,
            generated_at=iso(),
            tool_list=tool_list,
            workflow_block=workflow_block,
            evidence_block=evidence_block,
            steps=len(steps),
        ),
    )
    atomic_write_text(
        target / "handler.py",
        HANDLER_TEMPLATE.format(
            generated_at=iso(),
            # 用 repr 而不是 json.dumps：JSON 的 false/null 在 Python 里是语法错误，
            # 生成出来的文件必须能被 import —— 这一条曾经真的踩过。
            steps_repr=repr(steps),
            workflow=workflow,
        ),
    )
    return {
        "ok": True,
        "name": name,
        "path": str(target),
        "workflow": workflow,
        "steps": len(steps),
        "reason": f"新草稿技能 {name}（{len(steps)} 步，来自 {count} 次重复）",
    }


def _skill_name(label: str, workflow: str) -> str:
    base = slugify(f"auto-{label}", maxlen=28, default="auto-flow")
    base = re.sub(r"[^a-z0-9\-]", "", base)
    if not base:
        base = "auto-flow"
    return f"{base}-{stable_hash(workflow, 4)}"
