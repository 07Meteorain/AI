"""Quality rules: output contract, duplicated instructions, prompt budget."""

from __future__ import annotations

import re
from typing import Iterable, List

from ..config import Config
from ..model import Finding, SourceFile
from ..parser import ParsedPrompt
from ..tokens import estimate_tokens
from ..util import make_finding
from .base import Rule

OUTPUT_KEYWORDS = re.compile(
    r"(?i)\b(?:json|yaml|markdown|xml|csv|tsv|html|schema|format|output|return|"
    r"respond|response|list|table|bullet)\b"
    r"|返回|输出|格式|表格|列表|字段|结构"
)

MIN_CONTRACT_LENGTH = 200


class MissingOutputContract(Rule):
    id = "PL007"
    name = "missing-output-contract"
    default_severity = "warning"
    summary = "The prompt does not say what shape the answer should take."
    rationale = (
        "Without a stated format, two runs of the same prompt drift apart and "
        "downstream parsers break. Short prompts are exempt because they are "
        "often one-line questions where the format is obvious."
    )
    bad_example = "Summarise the following article in detail. " * 10
    good_example = "Summarise the article. Return JSON: {\"summary\": string}.\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        body = parsed.body_text.strip()
        if len(body) < MIN_CONTRACT_LENGTH or OUTPUT_KEYWORDS.search(body):
            return []
        return [
            make_finding(
                source,
                self.id,
                self.default_severity,
                "no output format is specified (%d characters of instructions)"
                % len(body),
                parsed.body_line,
                1,
                hint="State the format: JSON schema, Markdown table, or a numbered list.",
            )
        ]


class DuplicateInstruction(Rule):
    id = "PL008"
    name = "duplicate-instruction"
    default_severity = "warning"
    summary = "The same instruction appears more than once."
    rationale = (
        "Repeated lines usually survive an edit that replaced a sentence but left "
        "the old copy. They waste budget and can contradict the newer wording."
    )
    bad_example = "Always answer in English and cite sources.\nAlways answer in English and cite sources.\n"
    good_example = "Always answer in English and cite sources.\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        seen = {}
        findings: List[Finding] = []
        for index in range(parsed.body_start, len(parsed.lines)):
            if parsed.fenced[index]:
                continue
            raw = parsed.lines[index].strip()
            if not raw or raw.startswith("#") or len(raw) < 20:
                continue
            normalised = re.sub(r"\s+", " ", raw.lower()).strip(" .;:,!?。；：，！？")
            if normalised in seen:
                findings.append(
                    make_finding(
                        source,
                        self.id,
                        self.default_severity,
                        "instruction repeats line %d: %s"
                        % (seen[normalised], raw[:80]),
                        index + 1,
                        1,
                        hint="Delete the earlier copy, or merge the two versions.",
                    )
                )
            else:
                seen[normalised] = index + 1
        return findings


class PromptTooLong(Rule):
    id = "PL010"
    name = "prompt-too-long"
    default_severity = "warning"
    summary = "The prompt exceeds the configured token budget."
    rationale = (
        "Longer prompts cost more, hit context limits earlier, and tend to bury "
        "the instruction that matters. Split the task or retrieve only the "
        "relevant context."
    )
    bad_example = "# a prompt far above max_tokens\n"
    good_example = "# a prompt within the budget\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        estimate = estimate_tokens(parsed.body_text)
        if estimate <= config.max_tokens:
            return []
        return [
            make_finding(
                source,
                self.id,
                self.default_severity,
                "prompt is ~%d tokens (limit %d)" % (estimate, config.max_tokens),
                parsed.body_line,
                1,
                hint="Split the prompt or move reference material into retrieval.",
            )
        ]
