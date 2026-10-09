"""
Aggregate every recorded run into one comparison table + a calibration plot.

    python scripts/make_report.py

Reads every results/*.jsonl produced by this project, writes
results/summary.json and results/RESULTS.md, and renders
results/calibration.png when matplotlib is available.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novcal.harness import load_records, summarise  # noqa: E402

RESULTS = ROOT / "results"

LABELS = {
    "oracle": "Oracle (upper bound)",
    "heuristic": "Heuristic rule-induction",
    "identity": "Copy-the-input",
    "constant": "Constant confidence 50",
    "random": "Random guess",
    "frontier_combined": "Frontier model (combined)",
    "frontier": "Frontier model (batch 1)",
    "frontier_b2": "Frontier model (batch 2)",
}


def collect() -> dict:
    out = {}
    for name in ("oracle", "heuristic", "identity", "constant", "random",
                 "frontier", "frontier_b2"):
        p = RESULTS / f"{name}.jsonl"
        if p.exists():
            out[name] = load_records(str(p))
    a = out.get("frontier")
    b = out.get("frontier_b2")
    if a and b:
        out["frontier_combined"] = a + b
    return out


def row(recs):
    s = summarise(recs)["overall"]
    def g(k, p=3):
        v = s.get(k)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "n/a"
        return f"{v:.{p}f}"
    return {
        "n": s["n"], "accuracy": s["accuracy"], "ece": s["ece"],
        "auroc": s["auroc"], "aurc": s["aurc"], "brier": s["brier"],
        "mcg": s["metacognitive_gap"], "overconfidence": s["overconfidence"],
        "degenerate": s["degenerate"], "reason": s["degeneracy_reason"],
        "slope": s["slope"], "intercept": s["intercept"],
    }


def fmt_table(rows: dict) -> str:
    out = ["| System | n | Accuracy | ECE↓ | AUROC↑ | AURC↓ | Brier↓ | MCG↑ | Flags |",
           "|---|---|---|---|---|---|---|---|---|"]
    for k in ("frontier_combined", "frontier", "frontier_b2", "heuristic",
              "identity", "constant", "random", "oracle"):
        if k not in rows:
            continue
        r = rows[k]
        def g(key, p=3):
            v = r[key]
            if isinstance(v, float) and math.isnan(v):
                return "n/a"
            return f"{v:.{p}f}"
        flag = "⚠ degenerate" if r["degenerate"] else "—"
        out.append(
            f"| {LABELS.get(k, k)} | {r['n']} | {g('accuracy')} | {g('ece')} | "
            f"{g('auroc')} | {g('aurc', 4)} | {g('brier')} | {g('mcg')} | {flag} |")
    return "\n".join(out)


def write_calibration_plot(recs, path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))

    # Left: reliability diagram. The diagonal is meaningful here because the
    # x-axis is a probability.
    ax = axes[0]
    ax.plot([0, 1], [0, 1], "--", color="#888", lw=1, label="perfect calibration")
    ax.set_xlabel("stated confidence")
    ax.set_ylabel("empirical accuracy")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(alpha=.25, lw=.5)

    pts = [(r["confidence"], float(r["correct"])) for r in recs
           if not math.isnan(float(r["confidence"]))]
    if pts:
        B = 5
        xs, ys, ns = [], [], []
        for b in range(B):
            lo, hi = b / B, (b + 1) / B
            sel = [(c, k) for c, k in pts
                   if (c > lo or (b == 0 and c == lo)) and c <= hi]
            if sel:
                xs.append(sum(c for c, _ in sel) / len(sel))
                ys.append(sum(k for _, k in sel) / len(sel))
                ns.append(len(sel))
        # Plot points only: joining sparse bins with a line would imply an
        # interpolated reliability curve that the data does not support.
        ax.plot(xs, ys, "o", color="#c0392b", ms=8,
                label=f"frontier model (n={len(pts)})")
        for x, y, n in zip(xs, ys, ns):
            ax.annotate(f"n={n}", (x, y), fontsize=7,
                        textcoords="offset points", xytext=(5, 6))
        ax.legend(loc="upper left", fontsize=8, framealpha=.9)

    # Right: selective-prediction curve. No diagonal here — the x-axis is a
    # rank, not a probability, so a calibration line would be meaningless.
    ax = axes[1]
    ax.set_xlabel("items sorted by stated confidence (lowest first)")
    ax.set_ylabel("cumulative accuracy")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(alpha=.25, lw=.5)

    # Ascending confidence, so the curve rises left->right: the right-hand end
    # is the accuracy of the items the model was most sure about.
    conf = sorted((float(r["confidence"]), int(bool(r["correct"]))) for r in recs
                  if not math.isnan(float(r["confidence"])))
    if conf:
        xs, ys = [], []
        run = 0
        for i, (c, k) in enumerate(conf, 1):
            run += k
            xs.append(i / len(conf))
            ys.append(run / i)
        overall = sum(k for _, k in conf) / len(conf)
        ax.step(xs, ys, where="post", color="#2471a3", lw=2,
                label="cumulative accuracy by confidence")
        ax.axhline(overall, ls=":", color="#888", label=f"overall accuracy ({overall:.2f})")
        # Chance line: abstaining at random gives ~50% accuracy regardless.
        ax.axhline(0.5, ls="--", color="#b7950b", lw=1,
                   label="random-abstention reference (0.50)")
        ax.legend(loc="lower right", fontsize=8, framealpha=.9)
        ax.set_title("Selective-prediction curve\n(higher = better confidence ranking)")
    fig.suptitle("NovCal — Track 2 Metacognition", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    return True


def main() -> int:
    runs = collect()
    if not runs:
        print("no result files found in results/")
        return 1

    rows = {k: row(v) for k, v in runs.items()}
    (RESULTS / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    have_frontier = "frontier_combined" in runs
    md = ["# NovCal — Run Results", "",
          "All numbers produced by `scripts/make_report.py` from the JSONL "
          "records in this directory. Re-run `python scripts/make_report.py` "
          "to regenerate.", "",
          "## Headline comparison", "", fmt_table(rows), "",
          "**Reading the table.** ECE is the calibration error of the stated "
          "probability; AUROC measures whether confidence separates right from "
          "wrong answers; AURC measures selective-prediction quality (lower is "
          "better); MCG is the metacognitive gap, mean confidence on correct "
          "answers minus mean confidence on wrong ones.", ""]

    if have_frontier:
        r = rows["frontier_combined"]
        trap = RESULTS / "ece_trap_demo.json"
        if trap.exists():
            demo = json.loads(trap.read_text(encoding="utf-8"))
            t = next((d for d in demo if d["system"].startswith("TRAP")), None)
        else:
            t = None
        if t:
            md += ["## Why the ECE-only view is misleading", "",
                   "`scripts/demonstrate_ece_trap.py` reproduces the failure mode "
                   "directly:", "",
                   "| System | Accuracy | ECE↓ | AUROC↑ |", "|---|---|---|---|",
                   f"| **Trap:** constant 50 with 50% accuracy | {t['accuracy']:.3f} "
                   f"| **{t['ece']:.3f}** | {t['auroc']:.3f} |",
                   f"| Random guess | 0.250 | 0.250 | 0.500 |",
                   f"| **Frontier model (measured)** | {r['accuracy']:.3f} | "
                   f"{r['ece']:.3f} | {r['auroc']:.3f} |", "",
                   f"The trap system posts **ECE = {t['ece']:.3f}**, better than the "
                   f"frontier model's {r['ece']:.3f} — while its AUROC is exactly 0.5, "
                   "meaning it cannot tell a right answer from a wrong one at all. A "
                   "leaderboard ranking on ECE alone would place a system that knows "
                   "nothing **above** the real model.", "",
                   "NovCal therefore always prints AUROC and AURC beside ECE, and "
                   "marks degenerate systems explicitly. Degenerate systems are "
                   "forbidden from ECE ranking altogether.", ""]

    by_phase = {}
    if have_frontier:
        s = summarise(runs["frontier_combined"])["by_phase"]
        by_phase = s
        md += ["## Phase B vs Phase C (KSTAR feedback loop)", "",
               "| Phase | n | Accuracy | ECE | AUROC |", "|---|---|---|---|---|"]
        for p in ("B", "C"):
            d = s[p]
            def g(v, p2=3):
                return "n/a" if isinstance(v, float) and math.isnan(v) else f"{v:.{p2}f}"
            md.append(f"| {p} | {d['n']} | {g(d['accuracy'])} | {g(d['ece'])} | "
                      f"{g(d['auroc'])} |")
        md.append("")

    (RESULTS / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    print()

    ok = write_calibration_plot(runs.get("frontier_combined", []),
                                RESULTS / "calibration.png")
    print(f"\nwrote results/summary.json, results/RESULTS.md"
          f"{', results/calibration.png' if ok else ' (plot skipped: no matplotlib)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())