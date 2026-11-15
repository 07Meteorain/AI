"""组织回答：把工具结果拼成一段人话。

离线模式下这里做的是**抽取式回答**——把检索到的原始证据按相关度排好、
标出分数和命中词，再给一句"下一步"。它不编造任何句子。

这不是偷懒，是诚实：一个没有模型的后端如果开始"生成"，那就只是在拼模板，
而拼模板最擅长的恰恰是把"没找到"包装成"我建议你……"。检索不到就直说检索不到，
这比一段流畅的空话有用。
"""

from __future__ import annotations

from typing import Any

from ..tools.base import ToolResult


def _hits_of(results: list[ToolResult]) -> list[dict[str, Any]]:
    for res in results:
        if res.tool == "memory.search" and res.ok and isinstance(res.data, list):
            return res.data
    return []


def compose(intent: Any, text: str, results: list[ToolResult], *, mode: str = "offline") -> tuple[str, list[str]]:
    """返回 (回答文本, 证据 id 列表)。"""

    evidence: list[str] = []
    kind = getattr(intent, "kind", "chat")
    lines: list[str] = []

    if kind in ("recall", "chat"):
        hits = _hits_of(results)
        evidence = [h["id"] for h in hits]
        if hits:
            lines.append(f"在记忆里找到 {len(hits)} 条相关记录：")
            lines.append("")
            for i, hit in enumerate(hits, 1):
                matched = "、".join(hit.get("matched", [])[:5])
                lines.append(f"{i}. [{hit['layer']}] {hit['title']}（score {hit['score']}）")
                snippet = " ".join(str(hit.get("text", "")).split())
                lines.append(f"   {snippet[:150]}{'…' if len(snippet) > 150 else ''}")
                if matched:
                    lines.append(f"   命中：{matched}")
            lines.append("")
            lines.append("以上是原始证据，未做改写。需要结论就说「总结：「关键词」」，我会走复盘/沉淀流程。")
        else:
            lines.append("记忆里没有命中。")
            lines.append("")
            lines.append("这可能是三种情况：① 真的没记过；② 用了不同的说法（同义词还没学到）；")
            lines.append("③ 记录存在但关键词太泛。建议先 `记一下 …` 落一条，或换个更具体的词再问。")

    elif kind == "capture":
        rec = _first_ok(results, "memory.write")
        if rec:
            evidence = [rec["id"]]
            lines.append(f"已写入 {rec['layer']} 层：`{rec['id']}`")
            lines.append(f"标题：{rec['title']}")
            lines.append("")
            if rec["layer"] == "K":
                lines.append("知识层是长期资产：同时在 memory/knowledge/<id>.md 留了一份可读镜像，")
                lines.append("并且免疫于时间衰减（情境记录会随时间变冷，结论不会）。")
            else:
                lines.append("情境层记录的是「当时发生了什么」，会随时间衰减；")
                lines.append("如果这里面有值得复用的一句话，用「技能 note-to-knowledge」把它升格进知识层。")
            lines.append("")
            lines.append("提醒：写进记忆不等于以后能找到——检索靠词面命中。")
            lines.append("标题里放一个以后会用来找它的词，比正文写得漂亮更重要。")
        else:
            lines.append("写入失败，原因见下方工具回执。")

    elif kind == "task":
        done = _first_ok(results, "task.done")
        added = _first_ok(results, "task.add")
        listed = _first_ok(results, "task.list")
        if done:
            evidence = [done["task"], done["action_record"]]
            lines.append(f"任务已关闭：{done['task']}，并生成行动记录 `{done['action_record']}`。")
        elif added:
            evidence = [added["id"]]
            lines.append(f"新建任务 `{added['id']}`：{added['title']}")
        elif listed is not None:
            rows = listed if isinstance(listed, list) else []
            evidence = [r["id"] for r in rows]
            lines.append(f"当前有 {len(rows)} 条任务：" if rows else "当前没有未完成任务。")
            for r in rows:
                due = f"（截止 {r['due']}）" if r.get("due") else ""
                lines.append(f"- `{r['id']}` {r['title']}{due}")
        else:
            lines.append("任务操作没有成功，原因见下方回执。")

    elif kind in ("skill", "review"):
        skill_res = _first_ok(results, "skill.run")
        if skill_res:
            outputs = skill_res.get("outputs") or {}
            lines.append(f"技能 `{skill_res.get('skill')}` 执行完成（{skill_res.get('ms', 0)}ms）。")
            summary = outputs.get("summary") or outputs.get("message")
            if summary:
                lines.append("")
                lines.append(str(summary))
            for key in ("path", "out", "written"):
                if outputs.get(key):
                    lines.append(f"{key}：{outputs[key]}")
                    evidence.append(str(outputs[key]))
            if outputs.get("instructions"):
                lines.append("")
                lines.append(str(outputs["instructions"])[:400])
        else:
            lines.append("技能没有执行成功——看看是不是名字拼错，或技能还在草稿状态。")

    else:
        lines.append("（未识别的意图，按对话处理）")

    for res in results:
        if not res.ok:
            lines.append("")
            lines.append(f"⚠ {res.tool} 失败：{res.error}")

    if mode == "offline":
        lines.append("")
        lines.append("— 离线模式：以上为检索/工具结果，未调用任何大模型。")

    return "\n".join(lines).strip(), evidence


def _first_ok(results: list[ToolResult], tool: str) -> Any:
    for res in results:
        if res.tool == tool and res.ok:
            return res.data
    return None
