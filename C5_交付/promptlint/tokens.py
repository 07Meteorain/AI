"""A deliberately simple, deterministic token estimate.

promptlint never calls a tokenizer API: that would add a dependency, a model
choice, and a network round-trip to a linter. The estimate below is within
roughly 30% of BPE token counts for mixed English/Chinese prompts, which is
enough to catch prompts an order of magnitude over budget. The rule message
always says "~" so the number is not mistaken for an exact count.
"""

from __future__ import annotations


def _is_wide(char: str) -> bool:
    code = ord(char)
    return (
        0x3040 <= code <= 0x30FF      # Japanese kana
        or 0x3400 <= code <= 0x9FFF   # CJK ideographs
        or 0xAC00 <= code <= 0xD7AF   # Hangul
        or 0xFF00 <= code <= 0xFFEF   # fullwidth forms
    )


def estimate_tokens(text: str) -> int:
    wide = sum(1 for char in text if _is_wide(char))
    other = len(text) - wide
    return max(1, wide + (other + 3) // 4)
