"""decision-log：ADR 风格的决策记录。

为什么放技能而不是放记忆层：写 ADR 是一个**有固定结构的动作**（五个小节 + 编号规则），
固化下来以后，写入成本从"想怎么写"降到"填三个空"。
"""

from __future__ import annotations

from pathlib import Path

from brain.util import iso


def run(ctx, args=None):
    args = args or {}
    decision = str(args.get("query") or args.get("text") or "").strip()
    if not decision:
        raise ValueError("缺少决策内容（query）")

    reason = str(args.get("reason") or "").strip()
    options = [o.strip() for o in str(args.get("options") or "").replace("，", ",").split(",") if o.strip()]
    revisit = str(args.get("revisit") or "").strip()
    stamp = iso()[:10].replace("-", "")
    slug = "".join(ch for ch in decision[:16] if ch.isalnum() or "\u4e00" <= ch <= "\u9fff") or "adr"
    adr_id = f"ADR-{stamp}-{slug}"

    body = "\n".join(
        [
            f"# {adr_id}：{decision}",
            "",
            f"- 日期：{iso()[:10]}",
            f"- 状态：已决定",
            "",
            "## 背景",
            "",
            "（人补：当时面对什么约束。约束比理由更重要——理由会变，约束不会。）",
            "",
            "## 选项",
            "",
        ]
        + ([f"- 放弃：{o}" for o in options] if options else ["- （未记录被放弃的选项）"])
        + [
            "",
            "## 决定",
            "",
            decision,
            "",
            "## 理由",
            "",
            reason or "（未填写理由——这条 ADR 的可信度因此打了折）",
            "",
            "## 什么时候回头看",
            "",
            revisit or "（未设定；建议写一个具体月份，否则它永远不会被回看）",
            "",
        ]
    )

    adr_dir = ctx.config.knowledge_dir / "decisions"
    adr_dir.mkdir(parents=True, exist_ok=True)
    path = Path(adr_dir) / f"{adr_id}.md"
    path.write_text(body, encoding="utf-8")

    rec = ctx.memory.write(
        "K",
        f"决策 {adr_id}：{decision}\n理由：{reason or '（未记录）'}\n"
        f"放弃的选项：{'、'.join(options) if options else '（未记录）'}\n回看：{revisit or '（未设定）'}\n文件：{ctx.config.rel(path)}",
        title=f"决策：{decision[:24]}",
        tags=["decision"] + (["回看:" + revisit] if revisit else []),
        source=ctx.run_id or "skill:decision-log",
        importance=0.85,
        meta={"kind": "adr", "adr_id": adr_id, "revisit": revisit, "path": ctx.config.rel(path)},
        dedupe=True,
    )
    return {
        "summary": f"决策已记录：{adr_id}",
        "id": rec.id,
        "path": ctx.config.rel(path),
        "revisit": revisit,
    }
