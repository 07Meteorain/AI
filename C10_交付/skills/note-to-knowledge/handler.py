"""note-to-knowledge：把一条笔记升格成知识，并挂上它和旧记忆的关系。

刻意不做"质量判断"。一个自动判断"这条值不值得记住"的系统，
最后会把所有它看不懂的东西丢掉。
"""

from __future__ import annotations

from brain.util import truncate


def run(ctx, args=None):
    args = args or {}
    text = str(args.get("query") or args.get("text") or "").strip()
    if not text:
        raise ValueError("缺少笔记原文（query）")

    existing = ctx.memory.find_duplicate("K", text)
    if existing is not None:
        return {
            "summary": f"知识层已有这条（{existing.id}），未重复写入",
            "id": existing.id,
            "related": [],
            "deduped": True,
        }

    hits = ctx.memory.search(text, top_k=3, layers=["K", "AR", "S"], touch=False)
    related = [h.record.id for h in hits]

    title = str(args.get("title") or "").strip()
    if not title:
        first = " ".join(text.split())
        title = truncate(first, 24)
        if len(text) < 12:
            title += "（待提炼）"

    rec = ctx.memory.write(
        "K",
        text,
        title=title,
        tags=["distilled"],
        source=ctx.run_id or "skill:note-to-knowledge",
        importance=0.7,
        meta={"related": related, "kind": "note"},
        dedupe=True,
    )
    return {
        "summary": f"已升格为知识 `{rec.id}`，关联 {len(related)} 条旧记忆",
        "id": rec.id,
        "related": related,
    }
