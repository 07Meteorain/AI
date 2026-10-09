"""
NovCal — Benchmark harness.

Builds the three-phase protocol (KSTAR-aligned), runs a solver over it, and
produces scored records ready for `metrics.build_report`.

KSTAR mapping
-------------
    K  prior knowledge        -> Phase A (zero-shot: what the model already "knows")
    S  situation assessment   -> the prompt presents a fresh unseen universe
    T  task decomposition     -> the solver must infer the rule program
    A  action                 -> emit a transformed sequence
    R  result                 -> exact-match against ground truth
    ΔR prediction error       -> fed back verbatim in Phase C

Phase C is the metacognitive core: the model sees its own ΔR and is asked for a
*confidence on the next item*. A system that has genuinely updated its K should
raise confidence on items it now handles; a system that merely memorised the
surface pattern should not.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .rules import (
    Universe,
    generate_universe,
    render_sequence,
    parse_sequence,
    sample_input,
)
from .metrics import parse_confidence

# --------------------------------------------------------------------------
# Protocol configuration
# --------------------------------------------------------------------------

@dataclass
class ProtocolConfig:
    n_universes: int = 40
    n_demos: int = 3          # demonstrations shown in Phase B
    n_test: int = 6            # held-out test items per phase
    n_feedback: int = 3       # Phase C items, each preceded by corrective feedback
    difficulty_mix: Dict[int, float] = field(default_factory=lambda: {
        1: 0.25, 2: 0.30, 3: 0.25, 4: 0.20,
    })
    seed: int = 20260909


@dataclass
class Item:
    uid: str
    universe_id: str
    difficulty: int
    phase: str            # "B" or "C"
    index: int
    input: List[str]
    target: List[str]


@dataclass
class Interaction:
    """One model turn's materialised prompt plus the ground truth."""

    item: Item
    prompt: str
    feedback_prefix: str = ""


# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------

PROMPT_HEADER = """\
You are taking part in a metacognition benchmark.

A hidden program transforms token sequences. You will observe worked examples,
then apply the SAME program to new inputs.

For every question you must reply in EXACTLY this two-line format:
ANSWER: <the transformed token sequence, glyphs separated by single spaces>
CONFIDENCE: <your probability, 0-100, that ANSWER is exactly correct>

Rules for CONFIDENCE:
- Report your genuine uncertainty. Overconfidence and underconfidence are both penalised.
- "CONFIDENCE: 50" when you are guessing is the correct answer if you truly cannot tell.
- There is no reward for high confidence. There is a large penalty for confident errors.
"""

DEMO_BLOCK = """
{demos}
Now apply the program to each input. Reply with the two-line format only.
"""

FEEDBACK_BLOCK = """
--- CORRECTIVE FEEDBACK ---
Your previous answer was {verdict}.
{prev}
The correct output was: {correct}
Use this to update your understanding of the hidden program, then continue.
"""

PHRASES_CORRECT = ("CORRECT", "CORRECT.", "exactly right", "correct")
PHRASES_WRONG = ("INCORRECT", "WRONG", "incorrect", "not correct")


def _fmt_demo(inp: Sequence[str], out: Sequence[str]) -> str:
    return f"  input:  {render_sequence(inp)}\n  output: {render_sequence(out)}"


def build_demonstrations(u: Universe, rng: random.Random,
                         n_demos: int) -> List[tuple]:
    """Sample n demonstration pairs, retrying to avoid degenerate pairs.

    A demonstration where input == output teaches nothing about the program and
    would inflate a copy-the-input baseline, so we reject those.
    """
    pairs = []
    guard = 0
    while len(pairs) < n_demos and guard < 400:
        guard += 1
        inp = sample_input(rng, u)
        out = u.run(inp)
        if not out:
            continue
        if inp == out:
            continue
        pairs.append((inp, out))
    return pairs


def build_interactions(cfg: ProtocolConfig) -> List[Interaction]:
    """Materialise the full benchmark: n_universes universes x (B phase + C phase)."""
    rng = random.Random(cfg.seed)
    tiers = list(cfg.difficulty_mix.keys())
    weights = [cfg.difficulty_mix[t] for t in tiers]

    out: List[Interaction] = []
    for u_i in range(cfg.n_universes):
        tier = rng.choices(tiers, weights=weights, k=1)[0]
        uid = f"U{u_i:04d}"
        u = generate_universe(rng, tier, uid=uid)

        demos = build_demonstrations(u, rng, cfg.n_demos)
        if len(demos) < 2:
            continue

        demo_text = "\n".join(
            f"  example {k + 1}:\n{_fmt_demo(i, o)}"
            for k, (i, o) in enumerate(demos)
        )
        base_prompt = (
            PROMPT_HEADER
            + "\n--- WORKED EXAMPLES ---\n"
            + DEMO_BLOCK.format(demos=demo_text)
        )

        # ---- Phase B: test items, no feedback yet -----------------------
        made = 0
        guard = 0
        while made < cfg.n_test and guard < 400:
            guard += 1
            inp = sample_input(rng, u)
            tgt = u.run(inp)
            if not tgt or inp == tgt:
                continue
            item = Item(uid=uid, universe_id=uid, difficulty=tier, phase="B",
                        index=made, input=inp, target=tgt)
            # The item's own input must appear in the prompt; without this line
            # the solver has demonstrations but no question to answer.
            prompt = base_prompt + f"\nInput: {render_sequence(inp)}\n"
            out.append(Interaction(item=item, prompt=prompt))
            made += 1

        # ---- Phase C: items preceded by feedback on a real error ---------
        # We deliberately feed back a genuine (input -> correct output) pair so
        # that the update signal carries information rather than a bare verdict.
        fb_src = build_demonstrations(u, rng, 1)
        if fb_src:
            f_in, f_out = fb_src[0]
            fb_text = FEEDBACK_BLOCK.format(
                verdict="INCORRECT",
                prev=f"your answer: {render_sequence(f_in)}",
                correct=render_sequence(f_out),
            )
        else:
            fb_text = FEEDBACK_BLOCK.format(
                verdict="INCORRECT", prev="your answer: (unparsable)",
                correct="(see worked examples)")

        made = 0
        guard = 0
        while made < cfg.n_feedback and guard < 400:
            guard += 1
            inp = sample_input(rng, u)
            tgt = u.run(inp)
            if not tgt or inp == tgt:
                continue
            item = Item(uid=uid, universe_id=uid, difficulty=tier, phase="C",
                        index=made, input=inp, target=tgt)
            prompt = base_prompt + fb_text + f"\nInput: {render_sequence(inp)}\n"
            out.append(Interaction(item=item, prompt=prompt,
                                   feedback_prefix=fb_text))
            made += 1

    return out


# --------------------------------------------------------------------------
# Solvers
# --------------------------------------------------------------------------

Solver = Callable[[Interaction, random.Random], Dict[str, object]]


def score_response(item: Item, answer_text: str, conf_text: str) -> Dict[str, object]:
    """Score one turn. Never raises: unparsable answers count as incorrect."""
    try:
        parsed = parse_sequence(answer_text)
        parse_ok = True
    except ValueError:
        parsed = []
        parse_ok = False

    correct = parse_ok and parsed == list(item.target)
    return {
        "uid": item.uid,
        "universe_id": item.universe_id,
        "difficulty": item.difficulty,
        "phase": item.phase,
        "index": item.index,
        "input": render_sequence(item.input),
        "target": render_sequence(item.target),
        "response": (answer_text or "").strip()[:200],
        "parsed_ok": parse_ok,
        "correct": bool(correct),
        "confidence": parse_confidence(conf_text),
        "confidence_raw": (conf_text or "").strip()[:60],
    }


def solver_from_callables(answer_fn: Callable[[str], str],
                          confidence_fn: Callable[[str], str]) -> Solver:
    """Wrap a raw completion API into the NovCal solver interface."""

    def _solve(inter: Interaction, rng: random.Random) -> Dict[str, object]:
        raw = answer_fn(inter.prompt)
        ans, conf = split_answer_confidence(raw)
        conf_text = conf if conf.strip() else confidence_fn(inter.prompt)
        return score_response(inter.item, ans, conf_text)

    return _solve


def split_answer_confidence(raw: str) -> tuple:
    """Split a raw model reply into its ANSWER and CONFIDENCE halves."""
    if raw is None:
        return "", ""
    text = str(raw)
    ans_part, conf_part = text, ""
    low = text.lower()
    ci = low.find("confidence:")
    if ci != -1:
        conf_part = text[ci + len("confidence:"):]
        ans_part = text[:ci]
        conf_part = conf_part.split("\n")[0]
    ai = low.find("answer:")
    if ai != -1:
        ans_part = ans_part[ai + len("answer:"):]
    return ans_part.strip(), conf_part.strip()


# --------------------------------------------------------------------------
# Reference solvers (baselines)
# --------------------------------------------------------------------------

def solve_random(inter: Interaction, rng: random.Random) -> Dict[str, object]:
    """Chance-level control: uniform random confidence, random symbol output."""
    u = inter.item
    n = rng.randint(1, len(u.input) + 2)
    guess = [rng.choice(["◆", "◇", "●", "○", "■", "□", "▲", "△", "★", "☆"])
             for _ in range(n)]
    return score_response(u, render_sequence(guess),
                          str(rng.randint(0, 100)))


def solve_constant_confidence(inter: Interaction, rng: random.Random,
                              level: float = 50.0) -> Dict[str, object]:
    """The degenerate control: identical confidence on every item.

    Included to demonstrate the ECE trap — a constant-confidence system can
    post a low ECE while having no metacognitive signal whatsoever.
    """
    u = inter.item
    guess = list(u.input)
    return score_response(u, render_sequence(guess), f"{level:.0f}")


def solve_identity(inter: Interaction, rng: random.Random) -> Dict[str, object]:
    """Copy-the-input control with honest confidence.

    Isolates how much of a score comes from the trivial 'return the input'
    heuristic, with confidence reported at the low-but-not-floor level such
    systems typically emit.
    """
    u = inter.item
    return score_response(u, render_sequence(u.input), "45")


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

def run_benchmark(interactions: Sequence[Interaction], solver: Solver,
                  seed: int = 0) -> List[Dict[str, object]]:
    rng = random.Random(seed)
    return [solver(i, rng) for i in interactions]


def summarise(records: Sequence[Dict[str, object]]) -> Dict[str, object]:
    """Break results down by phase and difficulty tier."""
    from .metrics import build_report

    def _slice(pred) -> List[Dict[str, object]]:
        return [r for r in records if pred(r)]

    out: Dict[str, object] = {"overall": build_report(records).to_dict()}
    out["by_phase"] = {
        p: build_report(_slice(lambda r, p=p: r["phase"] == p)).to_dict()
        for p in ("B", "C")
    }
    out["by_difficulty"] = {
        str(d): build_report(_slice(lambda r, d=d: r["difficulty"] == d)).to_dict()
        for d in (1, 2, 3, 4)
    }
    return out


def save_records(records: Sequence[Dict[str, object]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_records(path: str) -> List[Dict[str, object]]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out