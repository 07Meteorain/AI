"""SARIF 2.1.0 output for GitHub code scanning and other CI viewers."""

from __future__ import annotations

from typing import List

from .baseline import fingerprint
from .rules import RULES
from .version import __version__

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
HELP_URI = "https://github.com/07Meteorain/AI/blob/master/C5_%E4%BA%A4%E4%BB%98/docs/rules.md"

LEVELS = {"error": "error", "warning": "warning", "info": "note"}


def _rules() -> List[dict]:
    return [
        {
            "id": rule.id,
            "name": rule.name,
            "shortDescription": {"text": rule.summary},
            "fullDescription": {"text": rule.rationale},
            "defaultConfiguration": {"level": LEVELS[rule.default_severity]},
            "helpUri": HELP_URI + "#" + rule.id.lower(),
        }
        for rule in RULES
    ]


def build_sarif(result) -> dict:
    rule_index = {rule.id: index for index, rule in enumerate(RULES)}
    results = []
    for source, findings in result.files:
        for finding in findings:
            end_column = max(finding.end_column, finding.column + 1)
            results.append(
                {
                    "ruleId": finding.rule_id,
                    "ruleIndex": rule_index[finding.rule_id],
                    "level": LEVELS.get(finding.severity, "warning"),
                    "message": {"text": finding.message},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {
                                    "uri": source.rel_path.replace("\\", "/")
                                },
                                "region": {
                                    "startLine": finding.line,
                                    "startColumn": finding.column,
                                    "endLine": finding.end_line,
                                    "endColumn": end_column,
                                },
                            }
                        }
                    ],
                    "partialFingerprints": {
                        "promptlint/v1": fingerprint(source.rel_path, finding)
                    },
                }
            )
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "promptlint",
                        "informationUri": HELP_URI.rsplit("/docs/", 1)[0],
                        "version": __version__,
                        "rules": _rules(),
                    }
                },
                "results": results,
            }
        ],
    }
