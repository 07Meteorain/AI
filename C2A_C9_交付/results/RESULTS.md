# NovCal — Run Results

All numbers produced by `scripts/make_report.py` from the JSONL records in this directory. Re-run `python scripts/make_report.py` to regenerate.

## Headline comparison

| System | n | Accuracy | ECE↓ | AUROC↑ | AURC↓ | Brier↓ | MCG↑ | Flags |
|---|---|---|---|---|---|---|---|---|
| Frontier model (combined) | 56 | 0.732 | 0.192 | 0.889 | 0.0717 | 0.122 | 0.332 | — |
| Frontier model (batch 1) | 24 | 0.958 | 0.256 | 0.739 | 0.0140 | 0.141 | 0.086 | — |
| Frontier model (batch 2) | 32 | 0.562 | 0.208 | 0.944 | 0.1507 | 0.107 | 0.385 | — |
| Heuristic rule-induction | 351 | 0.311 | 0.295 | 0.930 | 0.3755 | 0.177 | 0.189 | ⚠ degenerate |
| Copy-the-input | 351 | 0.000 | 0.450 | n/a | 1.0000 | 0.203 | n/a | ⚠ degenerate |
| Constant confidence 50 | 351 | 0.000 | 0.500 | n/a | 1.0000 | 0.250 | n/a | ⚠ degenerate |
| Random guess | 351 | 0.000 | 0.487 | n/a | 1.0000 | 0.324 | n/a | ⚠ degenerate |
| Oracle (upper bound) | 351 | 1.000 | 0.000 | n/a | 0.0000 | 0.000 | n/a | ⚠ degenerate |

**Reading the table.** ECE is the calibration error of the stated probability; AUROC measures whether confidence separates right from wrong answers; AURC measures selective-prediction quality (lower is better); MCG is the metacognitive gap, mean confidence on correct answers minus mean confidence on wrong ones.

## Why the ECE-only view is misleading

`scripts/demonstrate_ece_trap.py` reproduces the failure mode directly:

| System | Accuracy | ECE↓ | AUROC↑ |
|---|---|---|---|
| **Trap:** constant 50 with 50% accuracy | 0.500 | **0.000** | 0.500 |
| Random guess | 0.250 | 0.250 | 0.500 |
| **Frontier model (measured)** | 0.732 | 0.192 | 0.889 |

The trap system posts **ECE = 0.000**, better than the frontier model's 0.192 — while its AUROC is exactly 0.5, meaning it cannot tell a right answer from a wrong one at all. A leaderboard ranking on ECE alone would place a system that knows nothing **above** the real model.

NovCal therefore always prints AUROC and AURC beside ECE, and marks degenerate systems explicitly. Degenerate systems are forbidden from ECE ranking altogether.

## Phase B vs Phase C (KSTAR feedback loop)

| Phase | n | Accuracy | ECE | AUROC |
|---|---|---|---|---|
| B | 28 | 0.714 | 0.174 | 0.887 |
| C | 28 | 0.750 | 0.211 | 0.895 |
