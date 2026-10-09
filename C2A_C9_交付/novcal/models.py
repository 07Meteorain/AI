"""
NovCal — Model adapters.

`EchoSolver` and friends let the harness run end-to-end without network access,
so the benchmark is fully reproducible on any machine and in CI.

`LLMSolver` wraps any callable that maps a prompt string to a completion string.
That keeps the benchmark model-agnostic: OpenAI, Anthropic, Gemini, vLLM, Ollama
or a local HF endpoint all plug in through the same two-function contract, and
the adapter layer contains no benchmark logic at all.

Example
-------
    from openai import OpenAI
    client = OpenAI()

    def ask(prompt: str) -> str:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return r.choices[0].message.content or ""

    solver = novcal.solver_from_callables(ask, ask)
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from .harness import Interaction, score_response, solver_from_callables

CompletionFn = Callable[[str], str]


def make_llm_solver(ask: CompletionFn, system: Optional[str] = None,
                    temperature: float = 0.0, model: str = "unspecified",
                    retries: int = 2) -> tuple:
    """Return (solver, metadata) for a real completion endpoint.

    Retries transient failures (empty string / refusal) up to `retries` times,
    because a dropped request scored as "wrong" would silently deflate a model's
    measured accuracy and confidence calibration.
    """
    calls = {"n": 0, "failures": 0}

    def _ask(prompt: str) -> str:
        if system:
            prompt = f"{system}\n\n{prompt}"
        last = ""
        for _ in range(max(1, retries + 1)):
            calls["n"] += 1
            try:
                out = ask(prompt) or ""
            except Exception as exc:  # noqa: BLE001 - surface in metadata
                calls["failures"] += 1
                last = f"[api-error] {type(exc).__name__}"
                continue
            if out.strip():
                return out
            last = "[empty-response]"
        return last

    solver = solver_from_callables(_ask, _ask)
    meta = {"model": model, "temperature": temperature, "calls": calls}
    return solver, meta


# --------------------------------------------------------------------------
# Offline reference solvers
# --------------------------------------------------------------------------

def heuristic_solver(inter: Interaction, rng) -> dict:
    """A non-LLM control that attempts a real, shallow rule induction.

    It inspects the worked examples in the prompt and applies the simplest
    consistent hypothesis (relabeling / reversal / rotation) by string matching.
    This is the important non-trivial baseline: it shows what a competent but
    non-reasoning system scores, and whether its *confidence* tracks its actual
    competence (it typically does not).
    """
    u = inter.item
    prompt = inter.prompt

    demos = _extract_demo_pairs(prompt)
    target = list(u.target)
    input_seq = list(u.input)

    hypothesis = _infer_simple_rule(demos)
    if hypothesis is not None:
        guess = hypothesis(input_seq)
        if guess:
            return score_response(u, " ".join(guess), "62")

    guess = list(input_seq)
    return score_response(u, " ".join(guess), "40")


def _extract_demo_pairs(prompt: str) -> list:
    pairs = []
    for m in re.finditer(
        r"example\s+\d+:\s*\n\s*input:\s*(.+?)\n\s*output:\s*(.+?)(?=\n|$)",
        prompt, flags=re.IGNORECASE,
    ):
        pairs.append((m.group(1).strip(), m.group(2).strip()))
    return pairs


def _infer_simple_rule(demos: list):
    """Try to fit relabel / reverse / rotate from the demonstration pairs."""
    if not demos:
        return None

    parsed = []
    for i, o in demos:
        parsed.append((_glyphs(i), _glyphs(o)))
    if any(not a or not b for a, b in parsed):
        return None

    # (1) relabel
    mapping = {}
    for a, b in parsed:
        if len(a) != len(b):
            mapping = {}
            break
        for x, y in zip(a, b):
            if mapping.setdefault(x, y) != y:
                mapping = {}
                break
    if mapping:
        return lambda s: [mapping.get(t, t) for t in s]

    # (2) reverse
    if all(list(reversed(a)) == b for a, b in parsed):
        return lambda s: list(reversed(s))

    # (3) rotate by k
    for k in range(1, 5):
        if all(a[k:] + a[:k] == b for a, b in parsed):
            return lambda s: (s[k:] + s[:k]) if s else s

    # (4) filter: output is a subsequence of input
    if all(_is_subsequence(b, a) for a, b in parsed):
        keep = set()
        for a, b in parsed:
            keep |= set(b)
        if keep:
            return lambda s: [t for t in s if t in keep]
    return None


def _glyphs(text: str) -> list:
    text = text.replace("(empty)", " ")
    return [ch for ch in text if not ch.isspace()]


def _is_subsequence(small: list, big: list) -> bool:
    it = iter(big)
    return all(any(x == y for y in it) for x in small)


def oracle_solver(inter: Interaction, rng) -> dict:
    """Upper bound: perfect answers with perfect confidence.

    Sanity-checks that the harness can score a flawless system at 1.0. If this
    does not reach ~0 ECE and 1.0 AUROC, the metric code is wrong.
    """
    u = inter.item
    return score_response(u, " ".join(u.target), "100")