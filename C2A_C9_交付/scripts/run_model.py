"""
Run NovCal against any LLM endpoint.

The benchmark core is model-agnostic: it only needs a function that maps a
prompt string to a completion string. This script wires that contract to
whichever provider you have, records every raw response for auditability, and
writes scored records in NovCal's standard JSONL format.

Providers
---------
    openai      OPENAI_API_KEY        (GPT-4o, o4-mini, ...)
    anthropic   ANTHROPIC_API_KEY     (Claude Opus / Sonnet)
    gemini      GEMINI_API_KEY        (Gemini 2.5 Pro / Flash)
    openai-compat  OPENAI_BASE_URL    (vLLM, Ollama, DeepSeek, Qwen, ...)

Usage
-----
    python scripts/run_model.py --provider openai --model gpt-4o \
        --n-universes 40 --out results/gpt-4o.jsonl

    # local model through an OpenAI-compatible server
    python scripts/run_model.py --provider openai-compat \
        --model qwen2.5:7b --base-url http://localhost:11434/v1 \
        --n-universes 40 --out results/qwen.jsonl

    # dry run: print one prompt and exit (no API call)
    python scripts/run_model.py --dry-run

Every raw model response is written verbatim to <out>.raw.jsonl so that the
scoring can be re-verified independently — a benchmark you cannot re-audit is
not evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from novcal.harness import (  # noqa: E402
    ProtocolConfig,
    build_interactions,
    run_benchmark,
    save_records,
    summarise,
)
from novcal.models import make_llm_solver  # noqa: E402
from novcal.cli import _fmt_table  # noqa: E402


def build_client(provider: str, model: str, base_url: str | None):
    """Return a completion function for the requested provider."""
    if provider in ("openai", "openai-compat"):
        from openai import OpenAI
        client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
        )

        def ask(prompt: str) -> str:
            r = client.chat.completions.create(
                model=model, temperature=0.0, max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return r.choices[0].message.content or ""
        return ask

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"])

        def ask(prompt: str) -> str:
            r = client.messages.create(
                model=model, temperature=0.0, max_tokens=256,
                system="You are a careful reasoner. Follow the requested "
                       "output format exactly.",
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in r.content if b.type == "text")
        return ask

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])

        def ask(prompt: str) -> str:
            m = genai.GenerativeModel(model)
            r = m.generate_content(prompt)
            return r.text or ""
        return ask

    raise SystemExit(f"unsupported provider: {provider}")


def main() -> int:
    p = argparse.ArgumentParser(description="Run NovCal against an LLM")
    p.add_argument("--provider", default="openai",
                   choices=["openai", "openai-compat", "anthropic", "gemini"])
    p.add_argument("--model", required=False, default="gpt-4o")
    p.add_argument("--base-url", default=None)
    p.add_argument("--n-universes", type=int, default=40)
    p.add_argument("--n-demos", type=int, default=3)
    p.add_argument("--n-test", type=int, default=6)
    p.add_argument("--n-feedback", type=int, default=3)
    p.add_argument("--seed", type=int, default=20260909)
    p.add_argument("--out", default="results/model.jsonl")
    p.add_argument("--limit", type=int, default=None,
                   help="only run the first N items (for smoke tests)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the first prompt and exit")
    args = p.parse_args()

    cfg = ProtocolConfig(n_universes=args.n_universes, n_demos=args.n_demos,
                          n_test=args.n_test, n_feedback=args.n_feedback,
                          seed=args.seed)
    inter = build_interactions(cfg)
    if args.limit:
        inter = inter[:args.limit]

    if args.dry_run:
        print(f"interactions: {len(inter)}\n")
        print("=" * 72)
        print(inter[0].prompt)
        print("=" * 72)
        return 0

    ask = build_client(args.provider, args.model, args.base_url)
    solver, meta = make_llm_solver(ask, model=args.model, temperature=0.0)

    t0 = time.time()
    records = run_benchmark(inter, solver, seed=args.seed)
    dt = time.time() - t0

    save_records(records, args.out)
    with open(args.out + ".raw.jsonl", "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = summarise(records)
    summary["_run"] = {**{k: v for k, v in meta.items()},
                       "elapsed_sec": round(dt, 1),
                       "items": len(records),
                       "seed": args.seed}
    with open(args.out.replace(".jsonl", "_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(f"model={args.model}  items={len(records)}  "
          f"api_calls={meta['calls']['n']}  failures={meta['calls']['failures']}  "
          f"{dt:.1f}s")
    print(_fmt_table(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())