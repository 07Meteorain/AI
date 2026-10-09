"""
NovCal — Metacognition metrics.

Why these metrics and not just ECE
----------------------------------
Expected Calibration Error alone is a trap. A model that emits a *constant*
confidence equal to its own accuracy scores ECE = 0 while having zero ability to
tell right answers from wrong ones. This degeneracy is documented in the
selective-prediction literature (Geifman & El-Yaniv, 2019; Ding et al., 2020),
and it is precisely the failure mode a metacognition benchmark must not reward.

NovCal therefore reports a *panel* of metrics with deliberately different
failure modes:

    ECE        calibration of the probability scale    (gameable by constants)
    AUROC      ranking quality: right vs. wrong        (0.5 = no signal)
    AURC       selective-prediction quality            (ranking, coverage-aware)
    Brier      proper scoring rule, penalises both
    MCG        Metacognitive Gap: mean(correct conf) - mean(wrong conf)

A degenerate constant-confidence system scores well on ECE and at chance on
AUROC. NovCal flags that explicitly via `degeneracy_report`.

Attribution: ECE (Naeini et al., 2015; Guo et al., 2017), Brier (1950),
AUROC/AURC (Geifman & El-Yaniv, 2019; Nadeem et al., 2009), selective
prediction with abstention (Chow, 1970; Geifman & El-Yaniv, 2017).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Sequence, Tuple

# --------------------------------------------------------------------------
# Confidence extraction
# --------------------------------------------------------------------------

CONFIDENCE_SCALE = 100.0


def parse_confidence(raw: str) -> float:
    """Parse a stated confidence into [0, 1].

    Accepts "80", "80%", "0.8", "0.80", "high", "medium", "low".
    Returns nan when nothing parseable is present, so that a missing confidence
    is scored as a missing datum rather than silently defaulting to 0.5.
    """
    if raw is None:
        return float("nan")
    s = str(raw).strip().lower()
    if not s:
        return float("nan")

    words = {"high": 0.9, "very high": 0.95, "medium": 0.5, "moderate": 0.5,
             "low": 0.1, "very low": 0.05}
    if s in words:
        return words[s]
    for w, v in words.items():
        if s.startswith(w):
            return v

    pct = "%" in s
    s = s.replace("%", "").strip()
    # keep first numeric run
    num = ""
    for ch in s:
        if ch.isdigit() or ch == ".":
            num += ch
        elif num:
            break
    if not num:
        return float("nan")
    try:
        val = float(num)
    except ValueError:
        return float("nan")
    if pct or val > 1.0:
        val = val / 100.0
    return min(max(val, 0.0), 1.0)


# --------------------------------------------------------------------------
# Core metric implementations (pure Python, no numpy dependency)
# --------------------------------------------------------------------------

def expected_calibration_error(confidences: Sequence[float],
                               correct: Sequence[bool],
                               n_bins: int = 10) -> Tuple[float, List[Dict[str, float]]]:
    """Equal-width-bin ECE. Returns (ece, per-bin diagnostics)."""
    n = len(confidences)
    if n == 0:
        return float("nan"), []
    ece = 0.0
    bins: List[Dict[str, float]] = []
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [i for i in range(n)
               if (confidences[i] > lo or (b == 0 and confidences[i] == lo))
               and confidences[i] <= hi]
        if not idx:
            bins.append({"bin": b, "lo": lo, "hi": hi, "count": 0,
                         "conf": float("nan"), "acc": float("nan")})
            continue
        conf = sum(confidences[i] for i in idx) / len(idx)
        acc = sum(1.0 for i in idx if correct[i]) / len(idx)
        ece += (len(idx) / n) * abs(conf - acc)
        bins.append({"bin": b, "lo": lo, "hi": hi, "count": len(idx),
                     "conf": conf, "acc": acc})
    return ece, bins


def brier_score(confidences: Sequence[float], correct: Sequence[bool]) -> float:
    """Multi-class Brier score, averaged over items."""
    if not confidences:
        return float("nan")
    return sum((c - (1.0 if ok else 0.0)) ** 2
               for c, ok in zip(confidences, correct)) / len(confidences)


def auroc(confidences: Sequence[float], correct: Sequence[bool]) -> float:
    """AUROC for 'confidence predicts correctness', via the rank identity.

    Ties are handled with average ranks, so a constant-confidence system
    returns exactly 0.5 rather than an arbitrary value.
    """
    pos = [c for c, ok in zip(confidences, correct) if ok]
    neg = [c for c, ok in zip(confidences, correct) if not ok]
    n_pos, n_neg = len(pos), len(neg)
    if n_pos == 0 or n_neg == 0:
        return float("nan")

    order = sorted(range(len(confidences)), key=lambda i: confidences[i])
    ranks = [0.0] * len(confidences)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and confidences[order[j + 1]] == confidences[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1

    rank_sum = sum(r for r, ok in zip(ranks, correct) if ok)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def aurc(confidences: Sequence[float], correct: Sequence[bool]) -> float:
    """Area under the risk-coverage curve (lower is better).

    Items sorted by descending confidence; risk(c) = error rate among the top
    c fraction answered. AURC is the mean of risk over all coverage levels.
    """
    n = len(confidences)
    if n == 0:
        return float("nan")
    order = sorted(range(n), key=lambda i: confidences[i], reverse=True)
    errors = 0
    total = 0.0
    for k, i in enumerate(order, start=1):
        if not correct[i]:
            errors += 1
        total += errors / k
    return total / n


def optimal_aurc(confidences: Sequence[float], correct: Sequence[bool]) -> float:
    """AURC achieved by a perfect confidence oracle — the floor for comparison."""
    n = len(confidences)
    if n == 0:
        return float("nan")
    order = sorted(range(n), key=lambda i: (not correct[i],))
    errors = 0
    total = 0.0
    for k, i in enumerate(order, start=1):
        if not correct[i]:
            errors += 1
        total += errors / k
    return total / n


def random_aurc(correct: Sequence[bool]) -> float:
    """AURC of a random-confidence system — the ceiling for comparison."""
    n = len(correct)
    if n == 0:
        return float("nan")
    p = sum(1 for c in correct if c) / n
    # Expected risk at coverage c under random ordering.
    return 1.0 - (p + (1.0 - p) ** 2) / (2.0 * (1.0 - p)) if p < 1.0 else 1.0


def calibration_slope_intercept(confidences: Sequence[float],
                                correct: Sequence[bool],
                                n_bins: int = 10) -> Tuple[float, float]:
    """Logistic recalibration probe (Cox calibration).

    Refits a one-parameter logistic map p -> sigmoid(a*p + b) on the reported
    confidences. slope = 1, intercept = 0 means perfect calibration.
    slope << 1 indicates overconfidence that a simple rescale can repair;
    slope near 0 means the numbers carry almost no usable signal.
    """
    pts = [(c, 1.0 if ok else 0.0) for c, ok in zip(confidences, correct)
           if not math.isnan(c)]
    if len(pts) < 5:
        return float("nan"), float("nan")
    lo = _logit(min(p[0] for p in pts))
    hi = _logit(max(p[0] for p in pts))
    if hi - lo < 1e-6:
        return 0.0, float("nan")

    def nll(a: float, b: float) -> float:
        s = 0.0
        for p, y in pts:
            z = a * _logit(p) + b
            z = max(min(z, 30.0), -30.0)
            q = 1.0 / (1.0 + math.exp(-z))
            s -= y * math.log(max(q, 1e-12)) + (1 - y) * math.log(max(1 - q, 1e-12))
        return s

    best_a, best_b, best = 1.0, 0.0, nll(1.0, 0.0)
    # Coarse grid followed by refinement — the objective is 2-D and cheap here.
    for a in [i / 2.0 for i in range(-4, 13)]:
        for b in [i / 2.0 for i in range(-16, 17)]:
            v = nll(a, b)
            if v < best:
                best, best_a, best_b = v, a, b
    for _ in range(3):
        step_a, step_b = 0.25 / (4 ** _), 0.5 / (4 ** _)
        improved = True
        while improved:
            improved = False
            for da in (-step_a, 0.0, step_a):
                for db in (-step_b, 0.0, step_b):
                    a, b = best_a + da, best_b + db
                    v = nll(a, b)
                    if v < best - 1e-9:
                        best, best_a, best_b, improved = v, a, b, True
    return best_a, best_b


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------

@dataclass
class CalibrationReport:
    n: int
    n_parsed: int
    accuracy: float
    mean_confidence: float
    ece: float
    auroc: float
    aurc: float
    brier: float
    metacognitive_gap: float
    slope: float
    intercept: float
    overconfidence: float
    degenerate: bool
    degeneracy_reason: str
    bins: List[Dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d.pop("bins", None)
        return d

    def fmt(self) -> str:
        def f(x: float, p: int = 3) -> str:
            return "n/a" if (isinstance(x, float) and math.isnan(x)) else f"{x:.{p}f}"
        flag = " ⚠ DEGENERATE" if self.degenerate else ""
        return (
            f"n={self.n}  acc={f(self.accuracy)}  "
            f"ECE={f(self.ece)}  AUROC={f(self.auroc)}  "
            f"AURC={f(self.aurc, 4)}  Brier={f(self.brier)}  "
            f"MCG={f(self.metacognitive_gap)}{flag}"
        )


def build_report(records: Sequence[Dict[str, object]],
                 n_bins: int = 10) -> CalibrationReport:
    """Compute the full metric panel from scored records.

    Each record must carry: 'correct' (bool) and 'confidence' (float, may be nan).
    Records with nan confidence are excluded from confidence-conditioned metrics
    but still counted in accuracy — silently dropping them would flatter a model
    that refuses to answer.
    """
    n = len(records)
    if n == 0:
        nan = float("nan")
        return CalibrationReport(0, 0, nan, nan, nan, nan, nan, nan, nan, nan,
                                 nan, nan, False, "no records")

    correct = [bool(r["correct"]) for r in records]
    accuracy = sum(correct) / n

    scored = [r for r in records if not math.isnan(float(r["confidence"]))]  # type: ignore[arg-type]
    n_parsed = len(scored)
    if n_parsed == 0:
        nan = float("nan")
        return CalibrationReport(n, 0, accuracy, nan, nan, nan, nan, nan, nan,
                                 nan, nan, True, "no parseable confidence")

    conf = [float(r["confidence"]) for r in scored]  # type: ignore[arg-type]
    ok = [bool(r["correct"]) for r in scored]

    ece, bins = expected_calibration_error(conf, ok, n_bins=n_bins)
    au = auroc(conf, ok)
    ar = aurc(conf, ok)
    br = brier_score(conf, ok)
    slope, intercept = calibration_slope_intercept(conf, ok, n_bins=n_bins)
    mean_conf = sum(conf) / n_parsed

    pos = [c for c, k in zip(conf, ok) if k]
    neg = [c for c, k in zip(conf, ok) if not k]
    mcg = ((sum(pos) / len(pos)) - (sum(neg) / len(neg))) if pos and neg else float("nan")

    degenerate, reason = _degeneracy_check(conf, ok, accuracy)

    return CalibrationReport(
        n=n, n_parsed=n_parsed, accuracy=accuracy, mean_confidence=mean_conf,
        ece=ece, auroc=au, aurc=ar, brier=br, metacognitive_gap=mcg,
        slope=slope, intercept=intercept,
        overconfidence=mean_conf - accuracy,
        degenerate=degenerate, degeneracy_reason=reason, bins=bins,
    )


def _degeneracy_check(conf: Sequence[float], correct: Sequence[bool],
                      accuracy: float) -> Tuple[bool, str]:
    """Detect systems whose calibration numbers are uninformative.

    Four patterns are flagged:
      * floor / ceiling effect -> no correct (or no incorrect) answers, so the
        confidence-correctness relationship is not measurable at all
      * constant confidence  -> ECE looks perfect, AUROC carries no signal
      * low confidence diversity -> a handful of distinct values only
      * uninformative AUROC  -> confidence cannot rank right vs. wrong

    The floor case matters in practice: a chance-level system scores 0% and
    therefore reports `nan` for AUROC/MCG, which a naive report would silently
    print as "n/a" and read as "no problem".
    """
    reasons = []

    n_correct = sum(1 for c in correct if c)
    if n_correct == 0:
        reasons.append(f"floor effect: 0/{len(correct)} correct — calibration not measurable")
    elif n_correct == len(correct):
        reasons.append(f"ceiling effect: {len(correct)}/{len(correct)} correct — calibration not measurable")

    spread = max(conf) - min(conf)
    if spread < 1e-9:
        reasons.append("constant confidence (ECE uninformative)")

    uniq = len(set(round(c, 6) for c in conf))
    if uniq < max(2, 0.05 * len(conf)):
        reasons.append(f"only {uniq} distinct confidence values")

    if not reasons and n_correct > 0 and n_correct < len(correct):
        ranked = auroc(conf, correct)
        if not math.isnan(ranked) and ranked < 0.60:
            reasons.append(f"AUROC {ranked:.3f} < 0.60 (confidence does not track correctness)")

    return (len(reasons) > 0, "; ".join(reasons))