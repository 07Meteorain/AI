"""Base class for lint rules."""

from __future__ import annotations

from typing import Iterable

from ..config import Config
from ..model import Finding, SourceFile
from ..parser import ParsedPrompt


class Rule:
    """A single, independently testable check."""

    id = ""
    name = ""
    default_severity = "warning"
    summary = ""
    rationale = ""
    bad_example = ""
    good_example = ""

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        raise NotImplementedError

    def metadata(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.default_severity,
            "summary": self.summary,
            "rationale": self.rationale,
            "bad_example": self.bad_example,
            "good_example": self.good_example,
        }
