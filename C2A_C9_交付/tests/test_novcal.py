"""
Regression tests for the NovCal harness and metrics.

Run with:  python -m pytest tests/ -q
       or: python tests/test_novcal.py     (stdlib fallback, no pytest needed)
"""

from __future__ import annotations

import math
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from novcal.harness import (  # noqa: E402
    ProtocolConfig,
    build_interactions,
    run_benchmark,
    score_response,
    solve_random,
    split_answer_confidence,
)
from novcal.metrics import (  # noqa: E402
    auroc,
    aurc,
    brier_score,
    build_report,
    expected_calibration_error,
    parse_confidence,
)
from novcal.models import heuristic_solver, oracle_solver  # noqa: E402
from novcal.rules import (  # noqa: E402
    GLYPH_POOL,
    LEN_TAGS,
    generate_universe,
    parse_sequence,
    render_sequence,
    sample_input,
)


# ----------------------------------------------------------------------
# rules
# ----------------------------------------------------------------------

def test_glyph_pool_has_no_duplicates():
    assert len(GLYPH_POOL) == len(set(GLYPH_POOL))


def test_glyph_pool_excludes_length_tags():
    """Length tags must not also be ordinary glyphs, or parsing gets ambiguous."""
    assert not (set(GLYPH_POOL) & set(LEN_TAGS))


def test_universe_program_is_deterministic():
    """Same seed -> same program. Guards reproducibility of published scores."""
    a = generate_universe(random.Random(11), 2, "X")
    b = generate_universe(random.Random(11), 2, "X")
    assert a.program_text == b.program_text


def test_different_seeds_give_different_programs():
    a = generate_universe(random.Random(1), 3, "X")
    b = generate_universe(random.Random(2), 3, "X")
    assert a.program_text != b.program_text


def test_universe_run_is_pure():
    """Running a program must not mutate the input list."""
    u = generate_universe(random.Random(5), 3, "X")
    s = sample_input(random.Random(0), u)
    before = list(s)
    u.run(s)
    assert s == before


def test_parse_roundtrip_preserves_greek_capitals():
    """Regression: lowercasing responses corrupted Χ/Ψ/Σ glyphs.

    parse_sequence used to call .lower() on the whole response, which turned
    'Χ' into 'χ' — not a member of GLYPH_POOL — so correct answers were
    silently truncated and scored wrong.
    """
    for seq in (["Χ", "Ψ"], ["Σ", "Ω", "Δ"], ["Χ", "■", "Φ"]):
        assert parse_sequence(render_sequence(seq)) == seq


def test_parse_handles_length_tags():
    assert parse_sequence("‡ ₆ ⊙") == ["‡", "₆", "⊙"]


def test_parse_empty_marker():
    for text in ("(empty)", "empty", "none", "∅"):
        assert parse_sequence(text) == []


def test_parse_rejects_garbage():
    for text in ("", "   ", "hello world"):
        try:
            parse_sequence(text)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {text!r}")


def test_parse_tolerates_wrappers():
    assert parse_sequence("Output: ◆ ●") == ["◆", "●"]
    assert parse_sequence("`[▲, ★]`") == ["▲", "★"]
    assert parse_sequence("◆ → ●") == ["◆", "●"]


# ----------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------

def test_auroc_constant_is_exactly_half():
    """Tie handling: a constant-confidence system must score 0.5, not garbage."""
    assert abs(auroc([0.7] * 10, [True, False] * 5) - 0.5) < 1e-9


def test_auroc_perfect_and_inverted():
    assert abs(auroc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) - 1.0) < 1e-9
    assert abs(auroc([0.1, 0.2, 0.8, 0.9], [True, True, False, False]) - 0.0) < 1e-9


def test_auroc_nan_when_no_positives_or_negatives():
    assert math.isnan(auroc([0.5, 0.5], [False, False]))
    assert math.isnan(auroc([0.5, 0.5], [True, True]))


def test_ece_edges():
    assert abs(expected_calibration_error([0.0, 1.0], [False, True])[0]) < 1e-9
    assert abs(expected_calibration_error([1.0] * 4, [False] * 4)[0] - 1.0) < 1e-9
    assert abs(expected_calibration_error([1.0, 1.0], [False, True])[0] - 0.5) < 1e-9


def test_brier_edges():
    assert abs(brier_score([1.0] * 3, [True] * 3)) < 1e-9
    assert abs(brier_score([1.0] * 3, [False] * 3) - 1.0) < 1e-9


def test_aurc_perfect_is_zero():
    """A system that is right whenever it is confident has AURC = 0."""
    assert abs(aurc([0.9, 0.8], [True, True])) < 1e-9
    # 3 correct then 1 wrong: risks 0, 0, 0, 0.25 -> mean 0.0625
    assert abs(aurc([0.9, 0.8, 0.4, 0.3], [True, True, True, False]) - 0.0625) < 1e-9


def test_aurc_matches_hand_computed_value():
    """AURC averages the selective risk over all coverage levels k/n.

    Sorted by descending confidence: [T, T, F, F].
      k=1 -> 0 errors / 1 = 0.0
      k=2 -> 0 errors / 2 = 0.0
      k=3 -> 1 error  / 3 = 0.3333
      k=4 -> 2 errors / 4 = 0.5
    mean = (0 + 0 + 1/3 + 0.5) / 4 = 0.20833...
    """
    expected = (0.0 + 0.0 + (1 / 3) + 0.5) / 4
    got = aurc([0.9, 0.8, 0.4, 0.3], [True, True, False, False])
    assert abs(got - expected) < 1e-9, f"aurc={got}, expected {expected}"


def test_aurc_worse_when_ranking_is_inverted():
    good = aurc([0.9, 0.8, 0.2, 0.1], [True, True, False, False])
    bad = aurc([0.1, 0.2, 0.8, 0.9], [True, True, False, False])
    assert bad > good


def test_degeneracy_flags_constant_confidence():
    recs = [{"correct": ok, "confidence": 0.5}
            for ok in [True, False] * 5]
    assert build_report(recs).degenerate


def test_degeneracy_flags_floor_effect():
    recs = [{"correct": False, "confidence": 0.1 + 0.1 * i} for i in range(10)]
    rep = build_report(recs)
    assert rep.degenerate and "floor effect" in rep.degeneracy_reason


def test_well_calibrated_system_not_flagged():
    recs = [{"correct": ok, "confidence": c}
            for c, ok in [(0.95, True), (0.9, True), (0.85, True),
                           (0.15, False), (0.1, False), (0.05, False)]]
    assert not build_report(recs).degenerate


def test_nan_confidence_excluded_but_counted_in_accuracy():
    recs = [{"correct": True, "confidence": float("nan")},
            {"correct": False, "confidence": 0.9}]
    rep = build_report(recs)
    assert rep.accuracy == 0.5      # both items counted
    assert rep.n_parsed == 1        # only one had usable confidence


def test_parse_confidence_variants():
    assert parse_confidence("80") == 0.8
    assert parse_confidence("80%") == 0.8
    assert parse_confidence("0.25") == 0.25
    assert parse_confidence("high") == 0.9
    assert parse_confidence("LOW") == 0.1
    assert math.isnan(parse_confidence(""))
    assert math.isnan(parse_confidence("banana"))


def test_nan_guard_uses_isnan_not_identity():
    """`x is not x` is False for CPython's interned NaN singleton."""
    probe = float("nan")
    assert math.isnan(probe)
    assert not (probe is not probe)  # demonstrates the trap


# ----------------------------------------------------------------------
# harness
# ----------------------------------------------------------------------

def test_prompt_contains_the_item_input():
    """Regression: Phase B prompts originally omitted the `Input:` line, so the
    solver saw demonstrations but no question. Any prompt whose input sequence
    is absent is unusable."""
    inter = build_interactions(ProtocolConfig(n_universes=6, n_test=2,
                                              n_feedback=2, seed=4242))
    assert inter
    for it in inter:
        rendered = render_sequence(it.item.input)
        assert f"Input: {rendered}" in it.prompt, (
            f"item {it.item.uid}/{it.item.phase} prompt is missing its input")


def test_phase_c_prompts_carry_feedback():
    inter = build_interactions(ProtocolConfig(n_universes=6, n_test=2,
                                              n_feedback=2, seed=4242))
    for it in inter:
        if it.item.phase == "C":
            assert "CORRECTIVE FEEDBACK" in it.prompt
        else:
            assert "CORRECTIVE FEEDBACK" not in it.prompt


def test_no_demonstration_is_identity():
    """input == output demos teach nothing and inflate a copy baseline.

    build_demonstrations must reject such pairs, so every demo block in a
    materialised prompt must have differing input/output lines.
    """
    inter = build_interactions(ProtocolConfig(n_universes=30, n_demos=3,
                                              n_test=2, n_feedback=1, seed=99))
    checked = 0
    for it in inter:
        for m in re.finditer(
            r"input:\s*(.+?)\n\s*output:\s*(.+?)(?=\n|$)", it.prompt
        ):
            assert m.group(1).strip() != m.group(2).strip(), (
                f"identity demonstration leaked into {it.item.uid}")
            checked += 1
    assert checked > 0, "no demonstrations found to check"


def test_targets_are_reachable_and_parsable():
    """Every ground-truth target must survive a parse round-trip."""
    inter = build_interactions(ProtocolConfig(n_universes=25, n_test=2,
                                              n_feedback=2, seed=7))
    for it in inter:
        text = render_sequence(it.item.target)
        try:
            assert parse_sequence(text) == list(it.item.target)
        except ValueError:
            raise AssertionError(f"unparsable target: {text!r}")


def test_universe_is_a_function_of_its_input():
    """Applying the program twice must be identical (determinism of ground truth)."""
    u = generate_universe(random.Random(3), 4, "X")
    for _ in range(20):
        s = sample_input(random.Random(_), u)
        if not u.run(s):
            continue
        assert u.run(s) == u.run(list(s))


def test_oracle_scores_perfectly():
    inter = build_interactions(ProtocolConfig(n_universes=5, n_test=3,
                                              n_feedback=2, seed=7))
    rep = build_report(run_benchmark(inter, oracle_solver, seed=1))
    assert rep.accuracy == 1.0
    assert rep.ece < 1e-6


def test_random_baseline_is_flagged_degenerate():
    inter = build_interactions(ProtocolConfig(n_universes=5, n_test=3,
                                              n_feedback=2, seed=7))
    rep = build_report(run_benchmark(inter, solve_random, seed=2))
    assert rep.degenerate


def test_same_seed_reproduces_records():
    inter = build_interactions(ProtocolConfig(n_universes=8, n_test=3,
                                              n_feedback=2, seed=555))
    a = run_benchmark(inter, heuristic_solver, seed=5)
    b = run_benchmark(inter, heuristic_solver, seed=5)
    assert a == b


def test_difficulty_gradient_orders_tiers():
    """Tier 1 must be strictly easier than tier 4 for any real solver."""
    inter = build_interactions(ProtocolConfig(n_universes=60, n_test=3,
                                              n_feedback=1, seed=2026))
    recs = run_benchmark(inter, heuristic_solver, seed=1)

    def acc(tier):
        sel = [r for r in recs if r["difficulty"] == tier]
        return sum(1 for r in sel if r["correct"]) / len(sel) if sel else 0.0

    assert acc(1) > acc(3), f"tier1 {acc(1):.3f} should exceed tier3 {acc(3):.3f}"


def test_score_response_never_raises():
    inter = build_interactions(ProtocolConfig(n_universes=2, n_test=1,
                                              n_feedback=1, seed=1))
    for junk in ("", "???", None, "ANSWER:", "ΩΩΩ"):
        r = score_response(inter[0].item, junk, "")
        assert r["correct"] is False
        assert math.isnan(r["confidence"])


def test_split_answer_confidence():
    ans, conf = split_answer_confidence("ANSWER: ◆ ●\nCONFIDENCE: 70")
    assert "◆" in ans and conf.strip() == "70"
    ans2, _ = split_answer_confidence("just some text")
    assert "just some text" in ans2


# ----------------------------------------------------------------------
# runner
# ----------------------------------------------------------------------

def _main() -> int:
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - len(failed)}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())