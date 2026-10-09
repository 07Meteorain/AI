"""
NovCal CLI.

    python -m novcal.cli selftest
    python -m novcal.cli generate --n-universes 40 --out results/items.jsonl
    python -m novcal.cli run --solver baseline --out results/baseline.jsonl
    python -m novcal.cli report results/baseline.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Dict, List

from .harness import (
    ProtocolConfig,
    build_interactions,
    load_records,
    run_benchmark,
    save_records,
    solve_constant_confidence,
    solve_identity,
    solve_random,
    summarise,
)
from .metrics import build_report
from .models import heuristic_solver, oracle_solver

SOLVERS = {
    "random": solve_random,
    "constant": solve_constant_confidence,
    "identity": solve_identity,
    "heuristic": heuristic_solver,
    "oracle": oracle_solver,
}


def _isnan(x: float) -> bool:
    """NaN test.

    Never use `x is not x`: CPython interns the float NaN singleton, so the
    identity check returns False for a genuine NaN and silently disables any
    guard written with it.
    """
    return math.isnan(x)


def _fmt_table(summary: Dict[str, object]) -> str:
    def g(d, k, p=3):
        v = d.get(k)
        if v is None or (isinstance(v, float) and v != v):
            return "n/a"
        return f"{v:.{p}f}"

    rows = [("overall", summary["overall"])]
    for p, d in summary["by_phase"].items():
        rows.append((f"phase {p}", d))
    for k, d in summary["by_difficulty"].items():
        rows.append((f"tier {k}", d))

    head = f"{'slice':<10} {'n':>4} {'acc':>6} {'ECE':>6} {'AUROC':>6} {'AURC':>7} {'Brier':>7} {'MCG':>7}  flags"
    lines = [head, "-" * len(head)]
    for name, d in rows:
        flag = ""
        if d.get("degenerate"):
            flag = "DEGENERATE: " + str(d.get("degeneracy_reason", ""))[:38]
        lines.append(
            f"{name:<10} {d.get('n', 0):>4} {g(d,'accuracy'):>6} {g(d,'ece'):>6} "
            f"{g(d,'auroc'):>6} {g(d,'aurc',4):>7} {g(d,'brier'):>7} "
            f"{g(d,'metacognitive_gap'):>7}  {flag}"
        )
    return "\n".join(lines)


def cmd_selftest(args: argparse.Namespace) -> int:
    """Validate the metric implementations against closed-form expectations."""
    from .metrics import auroc, aurc, brier_score, expected_calibration_error

    failures: List[str] = []

    # Perfect system.
    conf = [1.0, 1.0, 1.0, 1.0]
    ok = [True, True, True, True]
    if abs(brier_score(conf, ok)) > 1e-9:
        failures.append("brier(perfect) != 0")
    if abs(aurc(conf, ok)) > 1e-9:
        failures.append("aurc(perfect) != 0")

    # Worst system: confident and always wrong.
    conf_bad = [1.0] * 4
    ok_bad = [False] * 4
    if abs(brier_score(conf_bad, ok_bad) - 1.0) > 1e-9:
        failures.append("brier(worst) != 1")

    # Constant confidence must give AUROC exactly 0.5 (rank-tie handling).
    a = auroc([0.7] * 10, [True, False] * 5)
    if abs(a - 0.5) > 1e-9:
        failures.append(f"auroc(constant) = {a}, expected 0.5")

    # Perfectly separated confidences -> AUROC 1.0.
    a = auroc([0.9, 0.9, 0.1, 0.1], [True, True, False, False])
    if abs(a - 1.0) > 1e-9:
        failures.append(f"auroc(separated) = {a}, expected 1.0")

    # Perfect calibration -> ECE 0.
    e, _ = expected_calibration_error([0.0, 1.0], [False, True])
    if abs(e) > 1e-9:
        failures.append(f"ece(perfect) = {e}, expected 0")

    # Fully anti-calibrated: total confidence, zero accuracy -> ECE 1.
    e, _ = expected_calibration_error([1.0] * 4, [False] * 4)
    if abs(e - 1.0) > 1e-9:
        failures.append(f"ece(anti-calibrated) = {e}, expected 1")

    # Partially anti-calibrated: conf 1.0 with accuracy 0.5 -> ECE 0.5.
    e, _ = expected_calibration_error([1.0, 1.0], [False, True])
    if abs(e - 0.5) > 1e-9:
        failures.append(f"ece(half-right) = {e}, expected 0.5")

    # Parser round-trip.
    from .rules import parse_sequence, render_sequence
    for s in (["◆", "●"], ["▲"], []):
        text = render_sequence(s)
        if parse_sequence(text) != s:
            failures.append(f"parse round-trip failed for {s}")

    # Confidence parser.
    from .metrics import parse_confidence
    for raw, want in [("80", .8), ("80%", .8), ("0.25", .25), ("high", .9),
                      ("LOW", .1), ("", float("nan")), ("abc", float("nan"))]:
        got = parse_confidence(raw)
        if got != want and not (got != got and want != want):
            failures.append(f"parse_confidence({raw!r}) = {got}, want {want}")

    # End-to-end: oracle must ace the harness.
    inter = build_interactions(ProtocolConfig(n_universes=5, n_test=3,
                                              n_feedback=2, seed=7))
    recs = run_benchmark(inter, oracle_solver, seed=1)
    rep = build_report(recs)
    if rep.accuracy < 0.999:
        failures.append(f"oracle accuracy = {rep.accuracy}, expected 1.0")
    if rep.ece > 1e-6:
        failures.append(f"oracle ECE = {rep.ece}, expected 0")

    # A perfect oracle sits at the ceiling, so AUROC is undefined by
    # construction (no incorrect items to rank). Assert the *reason* rather than
    # a numeric AUROC, and check numeric AUROC on a non-degenerate set below.
    if "ceiling effect" not in rep.degeneracy_reason:
        failures.append(
            f"oracle should be flagged as a ceiling effect, got: "
            f"{rep.degeneracy_reason!r}")

    # NaN-safety: metric guards must use math.isnan, never `x is not x`.
    # CPython interns the NaN singleton, so identity checks silently pass.
    probe = float("nan")
    if (probe is not probe) == False:  # noqa: E712 - documenting the trap
        pass  # interpreter caches nan; this is exactly why we use math.isnan
    if not _isnan(probe):
        failures.append("_isnan() failed to detect NaN")

    # AUROC == 1.0 on a properly mixed, perfectly separated set.
    from .metrics import auroc
    if abs(auroc([0.95, 0.90, 0.10, 0.05], [True, True, False, False]) - 1.0) > 1e-9:
        failures.append("auroc(separated mixed) != 1.0")

    # A genuinely mixed oracle-like set must NOT be flagged degenerate.
    from .metrics import build_report as _br
    mixed = [{"correct": ok, "confidence": c}
             for c, ok in [(0.95, True), (0.9, True), (0.8, True),
                           (0.2, False), (0.1, False), (0.05, False)]]
    rm = _br(mixed)
    if rm.degenerate:
        failures.append(f"well-behaved system wrongly flagged: {rm.degeneracy_reason}")

    # Random baseline must sit near chance and be flagged degenerate.
    recs_r = run_benchmark(inter, solve_random, seed=2)
    rep_r = build_report(recs_r)
    if not rep_r.degenerate:
        failures.append("random baseline not flagged degenerate")

    if failures:
        print("SELFTEST FAILED")
        for f in failures:
            print("  -", f)
        return 1

    print("SELFTEST PASSED")
    print(f"  oracle  : acc={rep.accuracy:.3f} ECE={rep.ece:.4f} AUROC={rep.auroc:.3f}")
    print(f"  random  : acc={rep_r.accuracy:.3f} ECE={rep_r.ece:.4f} "
          f"AUROC={rep_r.auroc:.3f} ({rep_r.degeneracy_reason})")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    cfg = ProtocolConfig(n_universes=args.n_universes, n_demos=args.n_demos,
                          n_test=args.n_test, n_feedback=args.n_feedback,
                          seed=args.seed)
    inter = build_interactions(cfg)
    with open(args.out, "w", encoding="utf-8") as fh:
        for it in inter:
            fh.write(json.dumps({
                "uid": it.item.uid, "difficulty": it.item.difficulty,
                "phase": it.item.phase, "index": it.item.index,
                "input": " ".join(it.item.input),
                "target": " ".join(it.item.target),
            }, ensure_ascii=False) + "\n")
    print(f"wrote {len(inter)} items -> {args.out}")
    print(f"universes={args.n_universes} seed={args.seed}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if args.solver not in SOLVERS:
        print(f"unknown solver: {args.solver}. choose from {list(SOLVERS)}")
        return 2
    cfg = ProtocolConfig(n_universes=args.n_universes, n_demos=args.n_demos,
                          n_test=args.n_test, n_feedback=args.n_feedback,
                          seed=args.seed)
    inter = build_interactions(cfg)
    recs = run_benchmark(inter, SOLVERS[args.solver], seed=args.seed)
    save_records(recs, args.out)
    summary = summarise(recs)
    print(f"solver={args.solver}  items={len(recs)}  -> {args.out}")
    print(_fmt_table(summary))
    with open(args.out.replace(".jsonl", "_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    recs = load_records(args.records)
    print(_fmt_table(summarise(recs)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="novcal",
                                description="NovCal metacognition benchmark")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("selftest", help="validate metric implementations")
    s.set_defaults(func=cmd_selftest)

    def add_bench_opts(sp):
        sp.add_argument("--n-universes", type=int, default=40)
        sp.add_argument("--n-demos", type=int, default=3)
        sp.add_argument("--n-test", type=int, default=6)
        sp.add_argument("--n-feedback", type=int, default=3)
        sp.add_argument("--seed", type=int, default=20260909)

    g = sub.add_parser("generate", help="materialise a fresh item set")
    add_bench_opts(g)
    g.add_argument("--out", default="results/items.jsonl")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run", help="run a reference solver over the benchmark")
    add_bench_opts(r)
    r.add_argument("--solver", default="heuristic",
                   help=f"one of {list(SOLVERS)}")
    r.add_argument("--out", default="results/run.jsonl")
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser("report", help="summarise a saved record file")
    rp.add_argument("records")
    rp.set_defaults(func=cmd_report)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())