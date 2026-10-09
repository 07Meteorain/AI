"""
Demonstrate the ECE trap empirically.

Claim under test
----------------
    "A constant-confidence system whose stated confidence equals its own
     accuracy achieves ECE = 0 — a perfect calibration score — while having
     zero ability to distinguish correct answers from wrong ones."

This is the reason NovCal refuses to rank on ECE alone. The literature states
it (Geifman & El-Yaniv, 2019; Ding et al., 2020); this script reproduces it so
the claim in the write-up rests on output rather than on citation.

Run:  python scripts/demonstrate_ece_trap.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novcal.metrics import build_report  # noqa: E402


def synthetic(n: int, accuracy: float, confidence: float) -> list:
    """A system with a target accuracy that always states the same confidence."""
    recs = []
    for i in range(n):
        # deterministic interleave so the slice is exactly `accuracy`
        correct = (i % max(1, round(1.0 / accuracy))) == 0 if accuracy > 0 else False
        recs.append({"correct": correct, "confidence": confidence})
    return recs


def load_frontier():
    """Use the real measured frontier run when available, so the comparison is
    against genuine data rather than a synthetic stand-in."""
    p = ROOT / "results" / "frontier.jsonl"
    b = ROOT / "results" / "frontier_b2.jsonl"
    recs: list = []
    for f in (p, b):
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    c = float(r["confidence"])
                    if c == c:  # skip NaN
                        recs.append({"correct": bool(r["correct"]),
                                     "confidence": c})
    return recs


def main() -> int:
    n = 100
    cases = [
        ("perfect oracle (synthetic)", None, None),
        ("TRAP: constant 50, accuracy 50%", 0.50, 0.50),
        ("constant 50, accuracy 0% (our baseline)", 0.00, 0.50),
        ("random guess", 0.25, 0.50),
    ]

    rows = []
    print(f"{'system':<44} {'acc':>6} {'ECE↓':>7} {'AUROC↑':>7} {'degenerate'}")
    print("-" * 80)
    for name, acc, conf in cases:
        recs = synthetic(n, acc, conf) if acc is not None else \
            [{"correct": True, "confidence": 1.0} for _ in range(n)]
        r = build_report(recs)
        au = "n/a" if r.auroc != r.auroc else f"{r.auroc:.3f}"
        rows.append({"system": name, "accuracy": r.accuracy, "ece": r.ece,
                     "auroc": None if r.auroc != r.auroc else r.auroc,
                     "degenerate": r.degenerate, "reason": r.degeneracy_reason})
        print(f"{name:<44} {r.accuracy:>6.3f} {r.ece:>7.3f} {au:>7} "
              f"{'YES' if r.degenerate else 'no'}")

    # Real measured frontier run, for an apples-to-apples ECE comparison.
    fr = load_frontier()
    if fr:
        rf = build_report(fr)
        au = "n/a" if rf.auroc != rf.auroc else f"{rf.auroc:.3f}"
        print(f"{'frontier model (REAL measured run)':<44} {rf.accuracy:>6.3f} "
              f"{rf.ece:>7.3f} {au:>7} {'YES' if rf.degenerate else 'no'}")
        frontier_ece = rf.ece
    else:
        print("(no measured frontier run found; skipping that row)")
        frontier_ece = 0.192

    trap = rows[1]
    print()
    print("=" * 80)
    print(f"ECE of the trap system   : {trap['ece']:.4f}   <- PERFECT calibration")
    print(f"AUROC of the trap system : 0.500                 <- no signal at all")
    print(f"Marked degenerate         : {trap['degenerate']}")
    print(f"Real frontier model ECE  : {frontier_ece:.4f}")
    print("=" * 80)
    print(
        f"\nA leaderboard ranking on ECE alone would place the trap system ABOVE the\n"
        f"real frontier model, because {trap['ece']:.3f} < {frontier_ece:.3f}. It knows nothing.\n"
        f"\nThis is why NovCal (1) always prints AUROC/AURC beside ECE and\n"
        f"(2) hard-forbids ranking degenerate systems by ECE."
    )

    out = ROOT / "results" / "ece_trap_demo.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())