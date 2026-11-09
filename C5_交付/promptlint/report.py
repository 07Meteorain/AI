"""Human and machine readable reporters."""

from __future__ import annotations

import json
from typing import Dict, Iterable, List

from .model import Finding
from .version import __version__


def counts(findings: Iterable[Finding]) -> Dict[str, int]:
    result = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        result[finding.severity] = result.get(finding.severity, 0) + 1
    return result


def _plural(number: int, word: str) -> str:
    return "%d %s%s" % (number, word, "" if number == 1 else "s")


def format_text(result) -> str:
    lines: List[str] = []
    for source, findings in result.files:
        if not findings:
            continue
        lines.append(source.rel_path)
        for finding in findings:
            lines.append(
                "  %d:%d  %-7s %-5s  %s"
                % (
                    finding.line,
                    finding.column,
                    finding.severity,
                    finding.rule_id,
                    finding.message,
                )
            )
        lines.append("")

    findings = result.findings
    summary = counts(findings)
    if findings:
        lines.append(
            "%s in %s (%d error%s, %d warning%s, %d info)"
            % (
                _plural(len(findings), "problem"),
                _plural(result.file_count, "file"),
                summary["error"],
                "" if summary["error"] == 1 else "s",
                summary["warning"],
                "" if summary["warning"] == 1 else "s",
                summary["info"],
            )
        )
    else:
        lines.append("No problems found in %s." % _plural(result.file_count, "file"))
    if result.suppressed:
        lines.append(
            "%s suppressed by baseline." % _plural(result.suppressed, "finding")
        )
    return "\n".join(lines).rstrip() + "\n"


def format_json(result) -> str:
    summary = counts(result.findings)
    payload = {
        "tool": "promptlint",
        "version": __version__,
        "summary": {
            "files_checked": result.file_count,
            "findings": len(result.findings),
            "errors": summary["error"],
            "warnings": summary["warning"],
            "infos": summary["info"],
            "suppressed": result.suppressed,
        },
        "files": [
            {"path": source.rel_path, "findings": [item.as_dict() for item in findings]}
            for source, findings in result.files
            if findings
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
