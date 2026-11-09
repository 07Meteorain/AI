"""Structure rules: the template itself is empty, unbalanced, or inconsistent."""

from __future__ import annotations

from typing import Iterable, List

from ..config import Config
from ..model import Finding, SourceFile
from ..parser import ParsedPrompt
from ..util import make_finding
from .base import Rule


class EmptyPrompt(Rule):
    id = "PL001"
    name = "prompt-empty"
    default_severity = "error"
    summary = "The prompt body is empty."
    rationale = (
        "A file that contains only front matter or whitespace sends nothing to the "
        "model. This is almost always a broken template or a wrong path."
    )
    bad_example = "---\nvars: [topic]\n---\n"
    good_example = "---\nvars: [topic]\n---\nExplain {{topic}} in one paragraph.\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        if parsed.body_text.strip():
            return []
        return [
            make_finding(
                source,
                self.id,
                self.default_severity,
                "prompt body is empty",
                parsed.body_line,
                1,
                hint="Add the instruction the model should follow.",
            )
        ]


class UndeclaredPlaceholder(Rule):
    id = "PL002"
    name = "placeholder-undeclared"
    default_severity = "error"
    summary = "A placeholder is used but not listed in front-matter vars."
    rationale = (
        "When a template declares its variables, an undeclared placeholder is a "
        "typo or a forgotten declaration. The renderer will either fail or ship a "
        "literal '{{name}}' to the model."
    )
    bad_example = "---\nvars: [topic]\n---\nWrite about {{topik}}.\n"
    good_example = "---\nvars: [topic]\n---\nWrite about {{topic}}.\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        if not parsed.vars_declared:
            return []
        findings: List[Finding] = []
        for placeholder in parsed.placeholders:
            if placeholder.valid and placeholder.name not in parsed.vars:
                findings.append(
                    make_finding(
                        source,
                        self.id,
                        self.default_severity,
                        "placeholder '{{%s}}' is not declared in vars"
                        % placeholder.name,
                        placeholder.line,
                        placeholder.column,
                        hint="Add it to vars or fix the spelling.",
                    )
                )
        return findings


class UnusedVariable(Rule):
    id = "PL003"
    name = "placeholder-unused"
    default_severity = "warning"
    summary = "A declared variable is never used."
    rationale = (
        "Unused variables usually mean the template drifted: a section was removed "
        "but its input stayed, or the author forgot to reference the value."
    )
    bad_example = "---\nvars: [tone, topic]\n---\nExplain {{topic}}.\n"
    good_example = "---\nvars: [tone, topic]\n---\nIn a {{tone}} tone, explain {{topic}}.\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        if not parsed.vars_declared:
            return []
        used = {item.name for item in parsed.placeholders if item.valid}
        findings: List[Finding] = []
        for name, decl in sorted(parsed.vars.items()):
            if name not in used:
                findings.append(
                    make_finding(
                        source,
                        self.id,
                        self.default_severity,
                        "variable '%s' is declared but never used" % name,
                        decl.line,
                        decl.column,
                        hint="Remove it from vars or reference it as {{%s}}." % name,
                    )
                )
        return findings


class MalformedPlaceholder(Rule):
    id = "PL004"
    name = "placeholder-malformed"
    default_severity = "error"
    summary = "A placeholder has broken syntax."
    rationale = (
        "Unbalanced braces, empty names, and invalid identifiers do not render. "
        "They silently reach the model as literal text, which makes the output "
        "look like a model failure instead of a template bug."
    )
    bad_example = "Hello {{name\nHello {{ }}\nHello {{1st_name}}\n"
    good_example = "Hello {{name}}\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        findings: List[Finding] = []
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
                    hint="Use ASCII letters, digits, '_', '.', or '-' inside {{...}}.",
                )
            )
        return findings
