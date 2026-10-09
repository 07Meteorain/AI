"""
Score a frontier-model run that was performed by an agent acting as the model.

The model's answers and pre-registered confidences live in a JSON file; this
script joins them against the benchmark ground truth and produces the standard
NovCal scored records. Keeping the transcription separate from the scoring means
the ground truth never influenced the reported confidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from novcal.harness import (  # noqa: E402
    ProtocolConfig,
    build_interactions,
    save_records,
    score_response,
    summarise,
)
from novcal.cli import _fmt_table  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--responses", default="results/frontier_responses.json")
    p.add_argument("--n-universes", type=int, default=6)
    p.add_argument("--n-demos", type=int, default=3)
    p.add_argument("--n-test", type=int, default=2)
    p.add_argument("--n-feedback", type=int, default=2)
    p.add_argument("--seed", type=int, default=20260909)
    p.add_argument("--out", default="results/frontier.jsonl")
    args = p.parse_args()

    cfg = ProtocolConfig(n_universes=args.n_universes, n_demos=args.n_demos,
                          n_test=args.n_test, n_feedback=args.n_feedback,
                          seed=args.seed)
    inter = build_interactions(cfg)

    payload = json.loads(Path(args.responses).read_text(encoding="utf-8"))
    by_idx = {int(e["idx"]): e for e in payload["items"]}

    if len(inter) != len(by_idx):
        print(f"ERROR: {len(inter)} interactions but {len(by_idx)} responses")
        return 2

    records = []
    for idx, it in enumerate(inter):
        e = by_idx.get(idx)
        if e is None:
            print(f"ERROR: no response for index {idx}")
            return 2
        r = score_response(it.item, e["answer"], str(e["confidence"]))
        r["response_index"] = idx
        records.append(r)

    save_records(records, args.out)
    summary = summarise(records)
    summary["_meta"] = payload.get("note", "")
    with open(args.out.replace(".jsonl", "_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(f"frontier model: items={len(records)} -> {args.out}\n")
    print(_fmt_table(summary))

    # Per-item view: where was confidence misallocated?
    print("\nper-item:")
    for r in records:
        mark = "OK " if r["correct"] else "ERR"
        print(f"  {mark} {r['universe_id']} t{r['difficulty']} ph{r['phase']} "
              f"conf={r['confidence']:.2f}  "
              f"in={r['input']}  got={r['response']}  want={r['target']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())