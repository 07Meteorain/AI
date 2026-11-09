"""Small helpers shared by rule implementations."""

from __future__ import annotations

from typing import Optional

from .model import Finding, SourceFile


def make_finding(
    source: SourceFile,
    rule_id: str,
    severity: str,
    message: str,
    line: int,
    column: int,
    hint: str = "",
    end_line: Optional[int] = None,
    end_column: Optional[int] = None,
) -> Finding:
    line = max(int(line), 1)
    column = max(int(column), 1)
    return Finding(
        rule_id=rule_id,
        severity=severity,
        message=message,
        line=line,
        column=column,
        end_line=end_line if end_line is not None else line,
        end_column=end_column if end_column is not None else column + 1,
        hint=hint,
        snippet=source.snippet_for(line),
    )
