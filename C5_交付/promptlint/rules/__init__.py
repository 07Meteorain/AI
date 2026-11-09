"""Rule registry. Import order defines report order."""

from __future__ import annotations

from typing import Dict, List

from .base import Rule
from .meta import InvalidFrontMatter
from .quality import DuplicateInstruction, MissingOutputContract, PromptTooLong
from .safety import (
    InvisibleCharacters,
    PiiLiteral,
    SecretLiteral,
    UntrustedInputBoundary,
)
from .structure import (
    EmptyPrompt,
    MalformedPlaceholder,
    UndeclaredPlaceholder,
    UnusedVariable,
)

RULES: List[Rule] = [
    EmptyPrompt(),
    UndeclaredPlaceholder(),
    UnusedVariable(),
    MalformedPlaceholder(),
    SecretLiteral(),
    PiiLiteral(),
    MissingOutputContract(),
    DuplicateInstruction(),
    UntrustedInputBoundary(),
    PromptTooLong(),
    InvisibleCharacters(),
    InvalidFrontMatter(),
]

RULE_INDEX: Dict[str, Rule] = {rule.id: rule for rule in RULES}

__all__ = ["RULES", "RULE_INDEX", "Rule"]
