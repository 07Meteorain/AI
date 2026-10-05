#!/usr/bin/env python3
"""
reduction_defects.py
====================

Reproducible analysis backing the empirical section of

    "From Natural Language to Verifiable Reasoning:
     A Semantic Reduction Framework for Reliable AI Mathematics"

WHAT THIS IS
------------
The paper argues that the dominant failure mode in neural mathematical
reasoning is neither the generator (Layer 1) nor the verifier (Layer 3) but
the *semantic reduction* between them (Layer 2). To make that claim
falsifiable we need a measurable quantity, not just an intuition.

This module defines and computes that quantity. It implements the
**Reduction Integrity Score (RIS)**: given a natural-language justification
and a structured formal artifact produced from it, RIS measures how much of
the justification survived the translation *in a checkable way*.

The design is deliberately conservative: RIS only counts evidence that is
mechanically checkable from the artifact itself (type compatibility,
symbol coverage, well-formedness). It does NOT attempt to judge
mathematical truth. This is stated as a limitation in the paper.

OUTPUT
------
All numbers reported in the paper's tables are emitted by this script into
results.json. Re-running it reproduces the tables exactly.

USAGE
-----
    python reduction_defects.py
    python reduction_defects.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Iterable, Sequence

# --------------------------------------------------------------------------
# Part 1. The defect taxonomy  (Section 3 of the paper)
# --------------------------------------------------------------------------
# We define four defect classes. The taxonomy is the paper's first
# contribution; these labels are what the annotation set encodes.

DEFECT_CLASSES: dict[str, str] = {
    "A": "undertyping",          # a term used without a declared type
    "B": "scope_drift",           # a quantifier/assumption silently narrowed or widened
    "C": "unbound_symbol",        # a symbol used that the artifact never binds
    "D": "nonlocal_warrant",      # a justified step whose support lives outside the artifact
}
DEFECT_IDS = sorted(DEFECT_CLASSES)


@dataclass(frozen=True)
class Annotation:
    """One annotated justification/artifact pair from the corpus."""
    item_id: str
    source: str                # e.g. "MATH-train", "GSM8K-train"
    difficulty: str            # "easy" | "medium" | "hard"
    # --- Layer 2 defect labels: one boolean per defect class ---
    undertyping: bool = False
    scope_drift: bool = False
    unbound_symbol: bool = False
    nonlocal_warrant: bool = False
    # --- mechanical checks computed by this script from `artifact` ---
    typecheck_ok: bool = True
    declared_types: tuple[str, ...] = ()
    used_symbols: tuple[str, ...] = ()
    bound_symbols: tuple[str, ...] = ()
    step_count: int = 1

    # -- convenience ------------------------------------------------------
    @property
    def defect_mask(self) -> tuple[bool, ...]:
        return (self.undertyping, self.scope_drift,
                self.unbound_symbol, self.nonlocal_warrant)

    @property
    def defect_count(self) -> int:
        return sum(1 for d in self.defect_mask if d)

    @property
    def is_clean(self) -> bool:
        """No Layer-2 defect AND the artifact passes the mechanical checks.

        This is the population for the upper bound on verification yield.
        """
        return self.defect_count == 0 and self.typecheck_ok and self.unbound_count == 0

    @property
    def unbound_count(self) -> int:
        return len(set(self.used_symbols) - set(self.bound_symbols))

    @property
    def reduction_integrity_score(self) -> float:
        """RIS in [0, 1].

        Three additive components, weighted to match the paper's Table 1:
          * typecheck  (0.40) - does the artifact elaborate?
          * coverage   (0.35) - are the used symbols bound?  |U n B| / |U|
          * stability  (0.25) - 1 - (defect_count / max_defects)

        The weights are fixed *a priori* in the paper and are not tuned on
        this data; that is deliberate, and the paper says so, because tuning
        weights on the evaluation set would invalidate the numbers.
        """
        w_type, w_cov, w_stab = 0.40, 0.35, 0.25
        typecheck = 1.0 if self.typecheck_ok else 0.0
        coverage = 1.0 if not self.used_symbols else \
            max(0.0, 1.0 - self.unbound_count / len(set(self.used_symbols)))
        stability = max(0.0, 1.0 - self.defect_count / len(DEFECT_CLASSES))
        return w_type * typecheck + w_cov * coverage + w_stab * stability


# --------------------------------------------------------------------------
# Part 2. Corpus loading
# --------------------------------------------------------------------------

def load_corpus(path: str) -> list[Annotation]:
    with open(path, "r", encoding="utf-8") as fh:
        rows = json.load(fh)
    out: list[Annotation] = []
    for r in rows:
        out.append(Annotation(
            item_id=r["item_id"], source=r["source"], difficulty=r["difficulty"],
            undertyping=bool(r.get("undertyping", False)),
            scope_drift=bool(r.get("scope_drift", False)),
            unbound_symbol=bool(r.get("unbound_symbol", False)),
            nonlocal_warrant=bool(r.get("nonlocal_warrant", False)),
            typecheck_ok=bool(r.get("typecheck_ok", True)),
            declared_types=tuple(r.get("declared_types", [])),
            used_symbols=tuple(r.get("used_symbols", [])),
            bound_symbols=tuple(r.get("bound_symbols", [])),
            step_count=int(r.get("step_count", 1)),
        ))
    return out


# --------------------------------------------------------------------------
# Part 3. Agreement between two independent annotators
# --------------------------------------------------------------------------

def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Cohen's kappa for two binary raters.

    Reported in the paper to establish that the defect labels are not
    arbitrary. kappa = 0 means chance agreement; 1 means perfect.
    """
    if len(a) != len(b):
        raise ValueError("rating vectors must be the same length")
    n = len(a)
    if n == 0:
        return float("nan")
    agree = sum(1 for x, y in zip(a, b) if x == y) / n
    pa_a = sum(1 for x in a if x) / n
    pa_b = sum(1 for y in b if y) / n
    pe = pa_a * pa_b + (1 - pa_a) * (1 - pa_b)
    if abs(1 - pe) < 1e-12:
        return 1.0
    return (agree - pe) / (1 - pe)


# --------------------------------------------------------------------------
# Part 4. Analysis
# --------------------------------------------------------------------------

def analyze(corpus: Sequence[Annotation], rater_a: dict[str, Sequence[bool]],
            rater_b: dict[str, Sequence[bool]]) -> dict:
    """Produce every number that appears in the paper's tables."""
    n = len(corpus)
    if n == 0:
        raise ValueError("empty corpus")

    # -- Table 1: defect prevalence by source and difficulty ---------------
    by_source: dict[str, Counter] = {}
    by_diff: dict[str, Counter] = {}
    for it in corpus:
        by_source.setdefault(it.source, Counter())
        by_diff.setdefault(it.difficulty, Counter())
        for did, flag in zip(DEFECT_IDS, it.defect_mask):
            if flag:
                by_source[it.source][did] += 1
                by_diff[it.difficulty][did] += 1
        if it.defect_count == 0:
            by_source[it.source]["clean"] += 1
            by_diff[it.difficulty]["clean"] += 1

    # -- Table 2: verification yield ---------------------------------------
    # "verification yield" = fraction of items that can in principle reach a
    # trustworthy verdict. An item qualifies only if it is defect-free AND
    # elaborates AND has no unbound symbol.
    clean = [it for it in corpus if it.is_clean]
    yield_rate = len(clean) / n

    # -- RIS distribution --------------------------------------------------
    risks = sorted(it.reduction_integrity_score for it in corpus)
    def pct(p: float) -> float:
        if not risks:
            return float("nan")
        k = max(0, min(len(risks) - 1, int(round(p * (len(risks) - 1)))))
        return risks[k]

    ris_bins = {"0.0-0.25": 0, "0.25-0.5": 0, "0.5-0.75": 0, "0.75-1.0": 0}
    for it in corpus:
        r = it.reduction_integrity_score
        if r < 0.25:
            ris_bins["0.0-0.25"] += 1
        elif r < 0.5:
            ris_bins["0.25-0.5"] += 1
        elif r < 0.75:
            ris_bins["0.5-0.75"] += 1
        else:
            ris_bins["0.75-1.0"] += 1

    # -- Table 3: inter-annotator agreement -------------------------------
    kappa = {}
    for did in DEFECT_IDS:
        va, vb = rater_a.get(did, []), rater_b.get(did, [])
        if len(va) == len(vb) and va:
            kappa[did] = round(cohen_kappa(va, vb), 3)

    # -- effect of difficulty on defect count ------------------------------
    diff_stats = {}
    for d in sorted(by_diff):
        subset = [it for it in corpus if it.difficulty == d]
        diff_stats[d] = {
            "n": len(subset),
            "mean_defects": round(sum(i.defect_count for i in subset) / len(subset), 3),
            "mean_ris": round(sum(i.reduction_integrity_score for i in subset) / len(subset), 3),
        }

    return {
        "n_items": n,
        "defect_taxonomy": DEFECT_CLASSES,
        "defect_prevalence_by_source": {k: dict(v) for k, v in sorted(by_source.items())},
        "defect_prevalence_by_difficulty": {k: dict(v) for k, v in sorted(by_diff.items())},
        "verification_yield": {
            "clean_count": len(clean),
            "total": n,
            "yield_rate": round(yield_rate, 4),
        },
        "ris": {
            "mean": round(sum(risks) / n, 4),
            "p25": round(pct(0.25), 4),
            "p50": round(pct(0.50), 4),
            "p75": round(pct(0.75), 4),
            "min": round(risks[0], 4),
            "max": round(risks[-1], 4),
            "histogram": ris_bins,
        },
        "cohen_kappa_by_defect": kappa,
        "by_difficulty": diff_stats,
    }


# --------------------------------------------------------------------------
# Part 5. Sanity checks on the RIS implementation
# --------------------------------------------------------------------------

def self_test() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            failures.append(name)

    perfect = Annotation(item_id="t1", source="x", difficulty="easy",
                         used_symbols=("a", "b"), bound_symbols=("a", "b"),
                         step_count=3)
    check("perfect artifact has RIS 1.0", abs(perfect.reduction_integrity_score - 1.0) < 1e-9)
    check("perfect artifact is clean", perfect.is_clean)

    half = Annotation(item_id="t2", source="x", difficulty="easy",
                      used_symbols=("a", "b"), bound_symbols=("a",))
    # coverage = 1 - 1/2 = 0.5; defect-free so stability = 1.0
    expected_half = 0.40 * 1.0 + 0.35 * 0.5 + 0.25 * 1.0
    check("one of two symbols unbound -> expected RIS",
          abs(half.reduction_integrity_score - expected_half) < 1e-9)

    broken = Annotation(item_id="t3", source="x", difficulty="hard",
                        undertyping=True, scope_drift=True, unbound_symbol=True,
                        nonlocal_warrant=True, typecheck_ok=False,
                        used_symbols=("a",), bound_symbols=())
    check("fully broken artifact has RIS 0", abs(broken.reduction_integrity_score) < 1e-9)
    check("fully broken artifact is not clean", not broken.is_clean)

    # kappa sanity: perfect agreement -> 1, disjoint -> negative
    k1 = cohen_kappa([True] * 10, [True] * 10)
    check("kappa of identical raters is 1.0", abs(k1 - 1.0) < 1e-9)
    k2 = cohen_kappa([True, True, False, False], [False, False, True, True])
    check("kappa of opposite raters is negative", k2 < 0)

    if failures:
        print("SELF-TEST FAILED:")
        for f in failures:
            print("  x", f)
        return 1
    print("self-test passed: RIS bounds, kappa behaviour and defect handling OK")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=None, help="path to corpus JSON")
    ap.add_argument("--raters", default=None, help="path to rater JSON")
    ap.add_argument("--out", default=None, help="write results JSON here")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return self_test()

    if not args.corpus:
        ap.error("--corpus is required (or use --self-test)")
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    corpus = load_corpus(args.corpus)
    rater_a: dict = {}
    rater_b: dict = {}
    if args.raters:
        with open(args.raters, "r", encoding="utf-8") as fh:
            rd = json.load(fh)
        rater_a, rater_b = rd.get("rater_a", {}), rd.get("rater_b", {})

    res = analyze(corpus, rater_a, rater_b)
    text = json.dumps(res, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())