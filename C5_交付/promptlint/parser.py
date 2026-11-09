"""Parse a prompt template into front matter, placeholders, and fenced regions.

The parser is deliberately small and dependency-free. It understands only the
minimum needed to lint templates reliably:

* an optional YAML-ish ``---`` front matter block with a ``vars`` list;
* ``{{name}}`` placeholders (whitespace inside the braces is allowed);
* fenced code blocks (``` or ~~~) and inline ``code`` spans, which are ignored
  for placeholder analysis because they are usually examples, not templates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

PLACEHOLDER_RE = re.compile(r"\{\{(.*?)\}\}")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
DELIM_RE = re.compile(r"\{\{|\}\}")


@dataclass
class VarDecl:
    name: str
    line: int
    column: int


@dataclass
class Placeholder:
    name: str
    raw: str
    line: int
    column: int
    valid: bool
    reason: str = ""


@dataclass
class ParseIssue:
    rule_id: str
    message: str
    line: int
    column: int


@dataclass
class ParsedPrompt:
    text: str
    lines: List[str]
    body_start: int
    front_matter: Dict[str, str]
    vars: Dict[str, VarDecl]
    vars_declared: bool
    placeholders: List[Placeholder]
    issues: List[ParseIssue]
    fenced: List[bool] = field(default_factory=list)

    @property
    def body_text(self) -> str:
        return "\n".join(self.lines[self.body_start:])

    @property
    def body_line(self) -> int:
        """1-based line number of the first body line."""
        return self.body_start + 1


def _mask_inline_code(line: str) -> str:
    """Replace inline-code spans with spaces so offsets stay unchanged."""
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _parse_vars_inline(value: str) -> List[str]:
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_strip_quotes(part) for part in inner.split(",")]


def parse_prompt(text: str) -> ParsedPrompt:
    # Normalise line endings once so 1-based positions and absolute offsets are
    # computed against the same string even when an API caller passes CRLF text.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    front_matter: Dict[str, str] = {}
    variables: Dict[str, VarDecl] = {}
    vars_declared = False
    issues: List[ParseIssue] = []
    body_start = 0

    if lines and lines[0].strip() == "---":
        close: Optional[int] = None
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                close = i
                break
        if close is None:
            issues.append(
                ParseIssue(
                    "PL012",
                    "front matter opens with '---' but is never closed",
                    1,
                    1,
                )
            )
        else:
            i = 1
            while i < close:
                raw = lines[i]
                stripped = raw.strip()
                if not stripped or stripped.startswith("#"):
                    i += 1
                    continue
                if ":" not in stripped:
                    issues.append(
                        ParseIssue(
                            "PL012",
                            "front-matter line is not 'key: value': %r" % stripped[:60],
                            i + 1,
                            1,
                        )
                    )
                    i += 1
                    continue
                key, value = stripped.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                if key != "vars":
                    front_matter[key] = value
                    i += 1
                    continue

                vars_declared = True
                if value.startswith("[") and value.endswith("]"):
                    for name in _parse_vars_inline(value):
                        if not NAME_RE.match(name):
                            issues.append(
                                ParseIssue(
                                    "PL012",
                                    "invalid variable name %r in vars list" % name,
                                    i + 1,
                                    1,
                                )
                            )
                            continue
                        variables[name] = VarDecl(name, i + 1, 1)
                    front_matter[key] = value
                    i += 1
                    continue

                if value == "":
                    j = i + 1
                    while j < close:
                        item = lines[j].strip()
                        if not item or item.startswith("#"):
                            j += 1
                            continue
                        if item.startswith("- "):
                            name = _strip_quotes(item[2:])
                            if not NAME_RE.match(name):
                                issues.append(
                                    ParseIssue(
                                        "PL012",
                                        "invalid variable name %r in vars list" % name,
                                        j + 1,
                                        1,
                                    )
                                )
                            else:
                                variables[name] = VarDecl(name, j + 1, item.index("-") + 1)
                            j += 1
                            continue
                        break
                    front_matter[key] = value
                    i = j
                    continue

                issues.append(
                    ParseIssue(
                        "PL012",
                        "vars must be an inline list ('vars: [a, b]') or a block list",
                        i + 1,
                        1,
                    )
                )
                i += 1
            body_start = close + 1

    fenced = [False] * len(lines)
    in_fence = False
    fence_marker = ""
    for i in range(body_start, len(lines)):
        match = FENCE_RE.match(lines[i])
        if match:
            marker = match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
            fenced[i] = True
        else:
            fenced[i] = in_fence

    placeholders: List[Placeholder] = []
    for i in range(body_start, len(lines)):
        if fenced[i]:
            continue
        line = lines[i]
        masked = _mask_inline_code(line)
        spans = []
        for match in PLACEHOLDER_RE.finditer(masked):
            spans.append((match.start(), match.end()))
            inner = match.group(1)
            name = inner.strip()
            column = match.start() + 1
            if not name:
                issues.append(
                    ParseIssue("PL004", "empty placeholder '{{}}'", i + 1, column)
                )
                placeholders.append(Placeholder("", match.group(0), i + 1, column, False, "empty"))
            elif not NAME_RE.match(name):
                issues.append(
                    ParseIssue(
                        "PL004",
                        "invalid placeholder name %r" % name,
                        i + 1,
                        column,
                    )
                )
                placeholders.append(
                    Placeholder(name, match.group(0), i + 1, column, False, "invalid name")
                )
            else:
                placeholders.append(
                    Placeholder(name, match.group(0), i + 1, column, True)
                )

        # Any brace pair left after removing valid placeholders is unbalanced.
        chars = list(masked)
        for start, end in spans:
            for index in range(start, end):
                chars[index] = " "
        remainder = "".join(chars)
        for match in DELIM_RE.finditer(remainder):
            issues.append(
                ParseIssue(
                    "PL004",
                    "unbalanced placeholder delimiter %r" % match.group(0),
                    i + 1,
                    match.start() + 1,
                )
            )

    return ParsedPrompt(
        text=text,
        lines=lines,
        body_start=body_start,
        front_matter=front_matter,
        vars=variables,
        vars_declared=vars_declared,
        placeholders=placeholders,
        issues=issues,
        fenced=fenced,
    )


def line_offset(lines: List[str], line: int, column: int) -> int:
    """Return the absolute offset of a 1-based (line, column) in the joined text."""
    offset = 0
    for index in range(min(line - 1, len(lines))):
        offset += len(lines[index]) + 1
    return offset + max(column - 1, 0)
