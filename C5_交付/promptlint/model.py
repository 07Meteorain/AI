"""Core data types shared by the parser, rules, and reporters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

SEVERITIES = ("error", "warning", "info", "off")
SEVERITY_RANK = {"error": 3, "warning": 2, "info": 1, "off": 0}


@dataclass
class Finding:
    """One problem found in one prompt file.

    ``line`` and ``column`` are 1-based so they can be pasted straight into
    editors and CI annotations.
    """

    rule_id: str
    severity: str
    message: str
    line: int
    column: int
    end_line: int
    end_column: int
    hint: str = ""
    snippet: str = ""

    def as_dict(self) -> dict:
        return {
            "rule": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "hint": self.hint,
            "snippet": self.snippet,
        }


@dataclass
class SourceFile:
    """A prompt file plus the path forms needed by reports and baselines."""

    path: str
    rel_path: str
    text: str
    lines: List[str]

    def snippet_for(self, line: int, limit: int = 160) -> str:
        if not 1 <= line <= len(self.lines):
            return ""
        text = self.lines[line - 1].strip()
        if len(text) > limit:
            return text[: limit - 3] + "..."
        return text
