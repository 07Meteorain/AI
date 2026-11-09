"""Safety rules: secrets, personal data, injection surface, invisible characters."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

from ..config import Config
from ..model import Finding, SourceFile
from ..parser import ParsedPrompt, line_offset
from ..util import make_finding
from .base import Rule

SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "OpenAI-style API key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
]

GENERIC_CREDENTIAL = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})"
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CN_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?![\d@])")
CN_ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")

UNTRUSTED_NAMES = {
    "input",
    "user_input",
    "userinput",
    "message",
    "user_message",
    "context",
    "document",
    "doc",
    "untrusted",
    "retrieved",
    "content",
    "data",
    "source",
    "corpus",
    "email_body",
    "webpage",
}

WRAPPER_RE = re.compile(r"<([A-Za-z][A-Za-z0-9_-]*)(?:\s[^<>]*)?>(.*?)</\1>", re.S)

INVISIBLE = {
    "\u200b": "zero width space",
    "\u200c": "zero width non-joiner",
    "\u200d": "zero width joiner",
    "\u202a": "left-to-right embedding",
    "\u202b": "right-to-left embedding",
    "\u202c": "pop directional formatting",
    "\u202d": "left-to-right override",
    "\u202e": "right-to-left override",
    "\u2060": "word joiner",
    "\ufeff": "byte order mark",
    "\u00a0": "non-breaking space",
}


def mask_secret(value: str) -> str:
    # Below 12 characters a four-and-four mask would reveal most of the value,
    # so report only its length instead.
    if len(value) < 12:
        return "<redacted:%d chars>" % len(value)
    return value[:4] + "..." + value[-4:]


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    if not local:
        return "***@" + domain
    return local[0] + "***@" + domain


class SecretLiteral(Rule):
    id = "PL005"
    name = "secret-literal"
    default_severity = "error"
    summary = "A credential looks hard-coded in the prompt."
    rationale = (
        "Prompts are copied into logs, issues, and model providers. A key pasted "
        "into a template leaks everywhere the prompt goes; rotate it and load it "
        "from the environment instead."
    )
    bad_example = "Call the API with sk-live-1234567890abcdef1234\n"
    good_example = "Read OPENAI_API_KEY from the environment.\n"

    def _scan(self, line: str):
        seen = set()
        for pattern, label in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                key = (match.start(), match.end())
                if key in seen:
                    continue
                seen.add(key)
                yield match, label, match.group(0)
        for match in GENERIC_CREDENTIAL.finditer(line):
            key = (match.start(2), match.end(2))
            if key in seen:
                continue
            seen.add(key)
            yield match, "hard-coded credential", match.group(2)

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        findings: List[Finding] = []
        for index, line in enumerate(parsed.lines, start=1):
            for match, label, secret in self._scan(line):
                findings.append(
                    make_finding(
                        source,
                        self.id,
                        self.default_severity,
                        "possible %s: %s" % (label, mask_secret(secret)),
                        index,
                        match.start() + 1,
                        hint="Remove it, rotate the key, and read the value from the environment.",
                    )
                )
        return findings


class PiiLiteral(Rule):
    id = "PL006"
    name = "pii-literal"
    default_severity = "warning"
    summary = "The prompt contains what looks like personal data."
    rationale = (
        "Emails, phone numbers, and national ids in a template end up in request "
        "logs and provider dashboards. Use synthetic placeholders for examples."
    )
    bad_example = "Contact alice@example.com or 13800138000.\n"
    good_example = "Contact {{email}} or {{phone}}.\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        findings: List[Finding] = []
        for index, line in enumerate(parsed.lines, start=1):
            for match in EMAIL_RE.finditer(line):
                findings.append(
                    make_finding(
                        source,
                        self.id,
                        self.default_severity,
                        "email address in prompt: %s" % mask_email(match.group(0)),
                        index,
                        match.start() + 1,
                        hint="Replace it with a placeholder such as {{email}}.",
                    )
                )
            for match in CN_MOBILE_RE.finditer(line):
                findings.append(
                    make_finding(
                        source,
                        self.id,
                        self.default_severity,
                        "mobile number in prompt: %s"
                        % mask_secret(match.group(0)),
                        index,
                        match.start() + 1,
                        hint="Replace it with a placeholder such as {{phone}}.",
                    )
                )
            for match in CN_ID_RE.finditer(line):
                findings.append(
                    make_finding(
                        source,
                        self.id,
                        self.default_severity,
                        "national id in prompt: %s" % mask_secret(match.group(0)),
                        index,
                        match.start() + 1,
                        hint="Replace it with a placeholder such as {{national_id}}.",
                    )
                )
        return findings


class UntrustedInputBoundary(Rule):
    id = "PL009"
    name = "untrusted-input-boundary"
    default_severity = "warning"
    summary = "Untrusted input is interpolated without a delimiter."
    rationale = (
        "When retrieved text or user content sits in the same channel as the "
        "instructions, a sentence inside the data can act as an instruction. "
        "Wrapping it in an XML tag (or similar delimiter) gives the model a "
        "structural boundary to trust."
    )
    bad_example = "Summarise this: {{user_message}}\n"
    good_example = "<user_message>\n{{user_message}}\n</user_message>\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        spans: Optional[List[tuple]] = None
        findings: List[Finding] = []
        for placeholder in parsed.placeholders:
            if not placeholder.valid or placeholder.name.lower() not in UNTRUSTED_NAMES:
                continue
            offset = line_offset(parsed.lines, placeholder.line, placeholder.column)
            if spans is None:
                spans = [
                    (match.start(), match.end())
                    for match in WRAPPER_RE.finditer(parsed.text)
                ]
            if any(start <= offset < end for start, end in spans):
                continue
            findings.append(
                make_finding(
                    source,
                    self.id,
                    self.default_severity,
                    "untrusted input '{{%s}}' is not delimited" % placeholder.name,
                    placeholder.line,
                    placeholder.column,
                    hint="Wrap it: <input>\\n{{%s}}\\n</input>" % placeholder.name,
                )
            )
        return findings


class InvisibleCharacters(Rule):
    id = "PL011"
    name = "invisible-character"
    default_severity = "warning"
    summary = "Zero-width or bidirectional characters are present."
    rationale = (
        "Invisible characters can hide instructions, break exact matching, and "
        "make two identical-looking prompts behave differently. They usually "
        "arrive by copy-paste from a chat window or a PDF."
    )
    bad_example = "Ignore previous instructions.\u200b\n"
    good_example = "Ignore previous instructions.\n"

    def check(self, parsed: ParsedPrompt, source: SourceFile, config: Config) -> Iterable[Finding]:
        findings: List[Finding] = []
        for index, line in enumerate(parsed.lines, start=1):
            for column, char in enumerate(line, start=1):
                if char in INVISIBLE:
                    findings.append(
                        make_finding(
                            source,
                            self.id,
                            self.default_severity,
                            "invisible character U+%04X (%s)"
                            % (ord(char), INVISIBLE[char]),
                            index,
                            column,
                            hint="Delete it and retype the sentence.",
                        )
                    )
                    break
        return findings
