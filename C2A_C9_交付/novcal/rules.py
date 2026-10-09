"""
NovCal — Procedural Rule Universes for Metacognitive Calibration.

Design rationale
----------------
The central measurement problem in Track 2 (Metacognition) is *contamination*:
any benchmark built from a fixed public question bank can be answered from
pre-training memory, and a model that has memorised an answer can appear
"confident and correct" without possessing any metacognitive signal at all.

NovCal therefore does not ship questions. It ships a **generator**. Every
"rule universe" is minted at evaluation time from a cryptographically-seeded
RNG: the symbol inventory is drawn from a large glyph pool, and the
transformation program is assembled from composable primitives. Two runs with
different seeds produce disjoint task spaces, so memorisation is structurally
impossible rather than merely discouraged.

Adapted from
------------
* ARC (Chollet, 2019)  — the "task must be novel / anti-memorisation" principle
  and exact-match scoring. We take the philosophy, drop the visual grids.
* SCAN (Lake & Baroni, 2018) — compositional command->transformation structure.
  We take the composition idea, drop the *fixed* vocabulary (SCAN's rules are
  public and therefore contaminable).

See docs/拿来说明.md for the full attribution table.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Glyph inventory
# --------------------------------------------------------------------------
# A deliberately large pool (56 symbols). A universe uses only k of them, so
# the joint space of (inventory, rules) is astronomically larger than any
# pre-training corpus could contain. All glyphs are BMP characters that render
# in standard terminals and in the Kaggle notebook viewer.

GLYPH_POOL: Tuple[str, ...] = (
    "◆", "◇", "●", "○", "■", "□", "▲", "△", "▼", "▽",
    "★", "☆", "⬟", "⬠", "⬡", "⬢",
    "⌘", "⌬", "⍟", "⍠", "⍡", "⍢",
    "⊕", "⊗", "⊙", "⊘", "⊚", "⊛",
    "†", "‡", "§", "¶", "¤", "¢",
    "Ω", "Δ", "Θ", "Λ", "Ξ", "Π",
    "Σ", "Φ", "Ψ", "Υ", "Χ",
)

# Length-bucket tags: appended when a program requests a length tag.
LEN_TAGS: Tuple[str, ...] = ("₁", "₂", "₃", "₄", "₅", "₆")


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------

Op = Callable[[List[str]], List[str]]


@dataclass(frozen=True)
class Substitution:
    """token -> token (1:1 relabelling)."""

    mapping: Dict[str, str]

    def apply(self, seq: List[str]) -> List[str]:
        return [self.mapping.get(tok, tok) for tok in seq]

    def render(self) -> str:
        body = ", ".join(f"{a}→{b}" for a, b in sorted(self.mapping.items()))
        return f"relabel({body})"


@dataclass(frozen=True)
class Expansion:
    """token -> multiple tokens (1:n expansion)."""

    mapping: Dict[str, Tuple[str, ...]]

    def apply(self, seq: List[str]) -> List[str]:
        out: List[str] = []
        for tok in seq:
            out.extend(self.mapping.get(tok, (tok,)))
        return out

    def render(self) -> str:
        body = ", ".join(f"{a}→{''.join(b)}" for a, b in sorted(self.mapping.items()))
        return f"expand({body})"


@dataclass(frozen=True)
class Swap:
    """Exchange the positions of two symbols (restores multiset)."""

    a: str
    b: str

    def apply(self, seq: List[str]) -> List[str]:
        out = []
        for tok in seq:
            if tok == self.a:
                out.append(self.b)
            elif tok == self.b:
                out.append(self.a)
            else:
                out.append(tok)
        return out

    def render(self) -> str:
        return f"swap({self.a},{self.b})"


@dataclass(frozen=True)
class Reverse:
    def apply(self, seq: List[str]) -> List[str]:
        return list(reversed(seq))

    def render(self) -> str:
        return "reverse()"


@dataclass(frozen=True)
class Rotate:
    """Rotate left by k (k normalised modulo length)."""

    k: int

    def apply(self, seq: List[str]) -> List[str]:
        if not seq:
            return seq
        k = self.k % len(seq)
        return seq[k:] + seq[:k]

    def render(self) -> str:
        return f"rotate({self.k})"


@dataclass(frozen=True)
class KeepOnly:
    """Drop every token not in `keep`."""

    keep: Tuple[str, ...]

    def apply(self, seq: List[str]) -> List[str]:
        keep = set(self.keep)
        return [t for t in seq if t in keep]

    def render(self) -> str:
        return f"keep_only({''.join(self.keep)})"


@dataclass(frozen=True)
class Duplicate:
    """Repeat each occurrence of `sym` n times, in place."""

    sym: str
    times: int

    def apply(self, seq: List[str]) -> List[str]:
        out: List[str] = []
        for tok in seq:
            if tok == self.sym:
                out.extend([tok] * self.times)
            else:
                out.append(tok)
        return out

    def render(self) -> str:
        return f"duplicate({self.sym},{self.times})"


@dataclass(frozen=True)
class TagLength:
    """Append a subscript tag encoding min(len(seq), 6)."""

    def apply(self, seq: List[str]) -> List[str]:
        return seq + [LEN_TAGS[min(len(seq), len(LEN_TAGS)) - 1]]

    def render(self) -> str:
        return "tag_length()"


@dataclass(frozen=True)
class TagIdentity:
    """Append the first token of the sequence (or '∅' if empty)."""

    fallback: str

    def apply(self, seq: List[str]) -> List[str]:
        return seq + [seq[0] if seq else self.fallback]

    def render(self) -> str:
        return "tag_identity()"


# --------------------------------------------------------------------------
# Guards (conditions)
# --------------------------------------------------------------------------

Guard = Callable[[List[str]], bool]


@dataclass(frozen=True)
class Contains:
    sym: str

    def __call__(self, seq: List[str]) -> bool:
        return self.sym in seq

    def render(self) -> str:
        return f"contains({self.sym})"


@dataclass(frozen=True)
class NotContains:
    sym: str

    def __call__(self, seq: List[str]) -> bool:
        return self.sym not in seq

    def render(self) -> str:
        return f"not_contains({self.sym})"


@dataclass(frozen=True)
class LengthGE:
    n: int

    def __call__(self, seq: List[str]) -> bool:
        return len(seq) >= self.n

    def render(self) -> str:
        return f"len>={self.n}"


@dataclass(frozen=True)
class CountEQ:
    sym: str
    n: int

    def __call__(self, seq: List[str]) -> bool:
        return seq.count(self.sym) == self.n

    def render(self) -> str:
        return f"count({self.sym})=={self.n}"


GUARD_POOL: Tuple[Callable[[], Guard], ...] = (
    lambda: NotContains,
    lambda: LengthGE,
    lambda: CountEQ,
)


# --------------------------------------------------------------------------
# Rule universe
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    """A guarded primitive. `guard=None` means unconditional."""

    op: object
    guard: Optional[object] = None

    def active(self, seq: List[str]) -> bool:
        if self.guard is None:
            return True
        return bool(self.guard(seq))

    def apply(self, seq: List[str]) -> List[str]:
        if not self.active(seq):
            return seq
        return self.op.apply(seq)

    def render(self) -> str:
        body = self.op.render()
        if self.guard is None:
            return body
        return f"IF {self.guard.render()} THEN {body}"


@dataclass
class Universe:
    """A single procedurally-minted rule universe."""

    uid: str
    symbols: List[str]
    rules: List[Rule]
    difficulty: int  # 1..4, the nominal tier
    program_text: str = field(default="")

    def run(self, seq: Sequence[str]) -> List[str]:
        """Apply the full program in order. Pure and deterministic."""
        out = list(seq)
        for rule in self.rules:
            out = rule.apply(out)
        return out

    def render_program(self) -> str:
        return " ; ".join(r.render() for r in self.rules)

    def finalise(self) -> "Universe":
        self.program_text = self.render_program()
        return self


# --------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------

# Tier -> (rule count range, guard probability, input length range)
TIER_SPEC: Dict[int, Tuple[Tuple[int, int], float, Tuple[int, int]]] = {
    1: ((1, 1), 0.0, (3, 5)),
    2: ((2, 2), 0.35, (4, 6)),
    3: ((2, 3), 0.60, (5, 7)),
    4: ((3, 4), 0.75, (6, 9)),
}


def _make_rule(rng: random.Random, symbols: List[str], difficulty: int) -> Rule:
    """Sample one primitive, attaching a guard with tier-dependent probability."""
    guard_p = TIER_SPEC[difficulty][1]
    kinds = ["substitution", "reverse", "rotate", "keep_only", "duplicate",
             "tag_length", "tag_identity", "expansion", "swap"]

    # Bias toward transformations that do not destroy all content: a universe
    # whose output is always empty carries no signal.
    weights = {
        "substitution": 3.0, "reverse": 2.0, "rotate": 2.0, "keep_only": 1.2,
        "duplicate": 1.5, "tag_length": 1.5, "tag_identity": 1.2,
        "expansion": 1.5, "swap": 1.5,
    }
    kind = rng.choices(kinds, weights=[weights[k] for k in kinds], k=1)[0]

    if kind == "substitution":
        picks = rng.sample(symbols, k=min(2, len(symbols)))
        op: object = Substitution({picks[0]: picks[-1]})
    elif kind == "reverse":
        op = Reverse()
    elif kind == "rotate":
        op = Rotate(rng.randint(1, 3))
    elif kind == "keep_only":
        k = max(1, len(symbols) - rng.randint(1, 2))
        op = KeepOnly(tuple(sorted(rng.sample(symbols, k=k))))
    elif kind == "duplicate":
        op = Duplicate(rng.choice(symbols), rng.randint(2, 3))
    elif kind == "tag_length":
        op = TagLength()
    elif kind == "tag_identity":
        op = TagIdentity(fallback=rng.choice(symbols))
    elif kind == "expansion":
        picks = rng.sample(symbols, k=min(2, len(symbols)))
        pool = [s for s in symbols if s not in picks]
        if not pool:
            op = Reverse()
        else:
            op = Expansion({picks[0]: (picks[-1], rng.choice(pool))})
    else:  # swap
        picks = rng.sample(symbols, k=2)
        op = Swap(picks[0], picks[1])

    guard: Optional[object] = None
    if rng.random() < guard_p:
        gkind = rng.choices(["contains", "not_contains", "length_ge", "count_eq"],
                            weights=[3.0, 2.0, 2.0, 2.0], k=1)[0]
        if gkind == "contains":
            guard = Contains(rng.choice(symbols))
        elif gkind == "not_contains":
            guard = NotContains(rng.choice(symbols))
        elif gkind == "length_ge":
            guard = LengthGE(rng.randint(2, 5))
        else:
            guard = CountEQ(rng.choice(symbols), rng.randint(1, 2))

    return Rule(op=op, guard=guard)


def generate_universe(rng: random.Random, difficulty: int, uid: str,
                      n_symbols: int = 4) -> Universe:
    """Mint one rule universe at the requested difficulty tier."""
    lo, hi = TIER_SPEC[difficulty][0]
    n_rules = rng.randint(lo, hi)
    symbols = sorted(rng.sample(GLYPH_POOL, k=n_symbols))
    rules = [_make_rule(rng, symbols, difficulty) for _ in range(n_rules)]
    return Universe(uid=uid, symbols=symbols, rules=rules,
                    difficulty=difficulty).finalise()


def sample_input(rng: random.Random, universe: Universe) -> List[str]:
    """Draw an input sequence appropriate to the tier's length window."""
    lo, hi = TIER_SPEC[universe.difficulty][2]
    n = rng.randint(lo, hi)
    return [rng.choice(universe.symbols) for _ in range(n)]


# --------------------------------------------------------------------------
# Text rendering (the wire format the model actually sees)
# --------------------------------------------------------------------------

def render_sequence(seq: Sequence[str]) -> str:
    """Canonical text form of a token sequence."""
    return " ".join(seq) if seq else "(empty)"


def parse_sequence(text: str) -> List[str]:
    """Parse a model response back into tokens. Tolerant of spacing/punctuation.

    Returns [] for an explicit empty marker. Raises ValueError when the response
    contains no recognisable glyph, so the caller can score it as a parse error
    rather than silently crediting a wrong-but-empty answer.
    """
    if text is None:
        raise ValueError("empty response")
    s = text.strip()
    if not s:
        raise ValueError("empty response")
    # Strip common wrappers models add: "Output:", quotes, brackets, code ticks.
    for a, b in (("`", ""), ("[", ""), ("]", ""), ("(", " "), (")", " ")):
        s = s.replace(a, b)
    s = s.replace('"', " ").replace("'", " ").replace(",", " ")
    s = s.replace("Output:", " ").replace("output:", " ")
    s = s.replace("→", " ").replace("->", " ")

    # NB: case is preserved for glyph extraction. Several pool symbols are
    # Greek capitals (Χ Ψ Σ ...), and lowercasing the response would corrupt
    # them into tokens that are not in the pool, silently truncating answers.
    # A separate lowered copy is used only for keyword matching.
    lowered = s.strip().lower()
    if lowered in {"(empty)", "empty", "none", "nothing", "∅"}:
        return []
    if lowered in {"-", "∅"}:
        raise ValueError("no glyph tokens found")

    tokens = [ch for ch in s if not ch.isspace()]
    # Valid tokens are the glyph pool *plus* the length-bucket tags, which are
    # legitimate program outputs. Omitting the tags here would silently drop
    # them from every target, making those items unanswerable.
    known = [t for t in tokens if t in GLYPH_POOL or t in LEN_TAGS]
    if not known:
        raise ValueError("no glyph tokens found")
    return known