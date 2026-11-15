"""技能层：把重复动作固化成"可调用、可版本化、可度量"的单元。

一个技能就是一个目录：

    skills/weekly-review/
        SKILL.md      ← 契约（front matter 元数据 + 正文说明）
        handler.py    ← 可选：真的能跑的 Python（def run(ctx, args) -> dict）

**为什么不是"存在 prompt 里的模板"**：模板没法被测试、没法统计失败率、
没法在失败时熔断。技能要有调用次数、成功率、最近使用时间，才谈得上"进化"。

**渐进披露（progressive disclosure）**：``list`` 只读 front matter（约 30 字/技能），
``show`` 才读正文，``run`` 才 import handler。这不是洁癖——把 10 个技能全文塞进
上下文，等于每轮都付一遍不需要的钱，还会稀释真正相关的信息。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_FM_LINE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")


def _coerce(value: str) -> Any:
    raw = value.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    low = raw.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """解析 SKILL.md 的 front matter。

    不引入 PyYAML 的原因很直接：这里只需要 YAML 的 5%——标量、列表、一层字典。
    为 5% 的语法引入一个 C 扩展依赖，会让"clone 下来就能跑"这条承诺作废。
    解析器只认这种形状，遇到不认识的形状**抛错而不是猜**。
    """

    lines = (text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text or ""
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        raise ValueError("front matter 没有闭合的 ---")

    meta: dict[str, Any] = {}
    i = 1
    while i < end:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        match = _FM_LINE.match(line)
        if not match:
            raise ValueError(f"front matter 第 {i + 1} 行无法解析：{line!r}")
        key, value = match.group(1), match.group(2)
        if value.strip():
            meta[key] = _coerce(value)
            i += 1
            continue

        # 空值 → 收集后续缩进块
        i += 1
        items: list[str] = []
        mapping: dict[str, Any] = {}
        while i < end:
            peek = lines[i]
            if not peek.strip():
                i += 1
                continue
            if not peek.startswith((" ", "\t")):
                break
            body = peek.strip()
            if body.startswith("- "):
                items.append(body[2:].strip())
            else:
                sub = _FM_LINE.match(body)
                if not sub:
                    raise ValueError(f"front matter 第 {i + 1} 行无法解析：{peek!r}")
                mapping[sub.group(1)] = _coerce(sub.group(2))
            i += 1
        if items and mapping:
            raise ValueError(f"字段 {key} 同时像列表又像字典，拒绝猜测")
        meta[key] = items if items else mapping

    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return meta, body


@dataclass
class Skill:
    name: str
    description: str
    path: Path
    version: str = "1.0"
    when: str = ""
    inputs: dict[str, str] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    handler: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)
    status: str = "ready"  # ready / draft / broken
    error: str = ""

    @property
    def dir(self) -> Path:
        return self.path.parent

    @property
    def executable(self) -> bool:
        return bool(self.handler) and (self.dir / self.handler).is_file()

    def meta_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": str(self.version),
            "when": self.when,
            "status": self.status,
            "executable": self.executable,
            "path": self.path.as_posix(),
            "inputs": self.inputs,
            "tags": self.tags,
        }


@dataclass
class SkillResult:
    skill: str
    ok: bool
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    ms: float = 0.0
    mode: str = "handler"  # handler / prompt

    def summary(self, limit: int = 70) -> str:
        if not self.ok:
            return f"✗ skill {self.skill}: {self.error[:limit]}"
        text = self.outputs.get("summary") or self.outputs.get("message") or ""
        if not text:
            text = "、".join(list(self.outputs)[:4]) or "完成"
        return f"✓ skill {self.skill}: {str(text)[:limit]}"
