"""Meta rules about the template file itself."""

from __future__ import annotations

from typing import Iterable

from ..config import Config
from ..model import Finding, SourceFile
from ..parser import ParsedPrompt
from ..util import make_finding
from .base import Rule


class InvalidFrontMatter(Rule):
    id = "PL012"
    name = "front-matter-invalid"
    default_severity = "error"
    summary = "The front matter cannot be parsed."
    rationale = (
        "promptlint reads vars from front matter. If the block is malformed, "
        "variable checks silently switch off, so the template looks clean while "
        "nothing is actually verified."
    )
    bad_example = "---\nvars topic\n---\nHello {{topic}}\n"
    good_example = "---\nvars: [topic]\n---\nHello {{topic}}\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        findings = []
        for issue in parsed.issues:
            if issue.rule_id != self.id:
                continue
            findings.append(
                make_finding(
                    source,
                    self.id,
                    self.default_severity,
                    issue.message,
                    issue.line,
                    issue.column,
                    hint="Use 'key: value' lines; vars takes a list.",
                )
            )
        return findings
