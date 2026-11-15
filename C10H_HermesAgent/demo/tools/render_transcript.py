#!/usr/bin/env python3
"""把 Hermes `--format stream-json` 的 JSONL 转成便于阅读的 Markdown。

用法:
    python render_transcript.py 01_summary.jsonl [01_summary.md]

只依赖标准库；无法解析的行（例如 stderr 混入的 Session: 提示）会被跳过。
流式 text 事件会按顺序拼回完整段落。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def short(value, limit: int = 800) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace("\r\n", "\n")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（截断，共 {len(text)} 字符）"


def read_events(path: Path):
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(sys.argv[1])

    out: list[str] = [f"# 会话记录：{path.name}", ""]
    tools = 0
    streamed: list[str] = []

    def flush_text() -> None:
        body = "".join(streamed).strip()
        streamed.clear()
        if body:
            out.extend([body, ""])

    for event in read_events(path):
        kind = event.get("type")
        if kind == "system":
            out += [f"- session_id: `{event.get('session_id') or '（见文末）'}`", ""]
        elif kind == "text":
            streamed.append(event.get("text", ""))
        elif kind == "tool_use":
            flush_text()
            tools += 1
            out += [f"## 工具调用 #{tools}：`{event.get('name')}`", "",
                    "```json", short(event.get("input", {}), 1500), "```", ""]
        elif kind == "tool_result":
            flush_text()
            status = "错误" if event.get("is_error") else "成功"
            out += [f"结果（{status}，{event.get('duration_ms', 0)} ms）：", "",
                    "```text", short(event.get("output", ""), 1200), "```", ""]
        elif kind == "result":
            flush_text()
            out += ["---", "",
                    f"**最终结果**：exit_code={event.get('exit_code')}，"
                    f"耗时 {round((event.get('duration_ms') or 0) / 1000, 1)} s，"
                    f"tokens={event.get('tokens', {}).get('total')}", "",
                    short(event.get("text", ""), 4000), "",
                    f"session_id: `{event.get('session_id', '')}`", ""]
    flush_text()

    rendered = "\n".join(out)
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.buffer.write(rendered.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
