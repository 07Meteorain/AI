"""Command line interface for promptlint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .baseline import (
    BASELINE_FILENAME,
    collect_fingerprints,
    load_baseline,
    save_baseline,
)
from .config import ConfigError, load_effective_config
from .engine import CheckResult, apply_baseline, lint_files
from .report import format_json, format_text
from .rules import RULE_INDEX, RULES
from .sarif import build_sarif
from .version import __version__

THRESHOLD = {"none": 0, "info": 1, "warning": 2, "error": 3}
SEVERITY_RANK = {"info": 1, "warning": 2, "error": 3}

INIT_TEMPLATE = {
    "_comment": "promptlint configuration. See docs/rules.md for every rule id.",
    "rules": {
        "PL006": "warning",
        "PL010": "warning",
    },
    "max_tokens": 4000,
    "exclude": [".git", "node_modules", ".venv", "venv", "__pycache__"],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promptlint",
        description="Static analysis for LLM prompt templates.",
    )
    parser.add_argument(
        "--version", action="version", version="promptlint %s" % __version__
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    check = subparsers.add_parser("check", help="lint prompt files")
    check.add_argument("paths", nargs="*", default=["."], help="files or directories")
    check.add_argument("--config", help="path to promptlint.json")
    check.add_argument(
        "--format", choices=["text", "json", "sarif"], default="text"
    )
    check.add_argument("--output", help="write the report to a file")
    check.add_argument("--baseline", help="suppress findings in this baseline file")
    check.add_argument(
        "--no-baseline", action="store_true", help="ignore auto-discovered baseline"
    )
    check.add_argument(
        "--fail-on",
        choices=["error", "warning", "info", "none"],
        default="warning",
        help="lowest severity that makes the command exit 1",
    )
    check.add_argument("--max-tokens", type=int, help="override the token budget")

    baseline = subparsers.add_parser(
        "baseline", help="record current findings as accepted"
    )
    baseline.add_argument("paths", nargs="*", default=["."], help="files or directories")
    baseline.add_argument("--config", help="path to promptlint.json")
    baseline.add_argument("--output", default=BASELINE_FILENAME)

    rules = subparsers.add_parser("rules", help="list every rule")
    rules.add_argument("--format", choices=["text", "json"], default="text")

    explain = subparsers.add_parser("explain", help="explain one rule")
    explain.add_argument("rule_id")

    init = subparsers.add_parser("init", help="write a starter configuration")
    init.add_argument("--output", default="promptlint.json")
    init.add_argument("--force", action="store_true")

    return parser


def _config(args) -> tuple:
    return load_effective_config(getattr(args, "config", None))


def _cmd_check(args) -> int:
    config, config_path = _config(args)
    if args.max_tokens is not None:
        if args.max_tokens <= 0:
            raise ConfigError("--max-tokens must be positive")
        config.max_tokens = args.max_tokens

    results = lint_files(args.paths, config)

    known = set()
    if not args.no_baseline:
        if args.baseline:
            baseline_path = Path(args.baseline)
            if not baseline_path.is_file():
                raise FileNotFoundError("baseline not found: %s" % args.baseline)
            known = load_baseline(baseline_path)
        else:
            candidates = [Path.cwd() / BASELINE_FILENAME]
            if config_path is not None:
                candidates.append(config_path.parent / BASELINE_FILENAME)
            for candidate in candidates:
                if candidate.is_file():
                    known = load_baseline(candidate)
                    break

    filtered, suppressed = apply_baseline(results, known)
    result = CheckResult(filtered, suppressed)

    if args.format == "text":
        text = format_text(result)
    elif args.format == "json":
        text = format_json(result)
    else:
        text = json.dumps(build_sarif(result), indent=2, ensure_ascii=False) + "\n"

    if args.output:
        output = Path(args.output)
        if output.parent != Path("."):
            output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("promptlint: wrote %s" % output, file=sys.stderr)
    else:
        sys.stdout.write(text)

    threshold = THRESHOLD[args.fail_on]
    highest = max(
        [SEVERITY_RANK.get(finding.severity, 0) for finding in result.findings] or [0]
    )
    return 1 if threshold and highest >= threshold else 0


def _cmd_baseline(args) -> int:
    config, _ = _config(args)
    results = lint_files(args.paths, config)
    fingerprints = collect_fingerprints(results)
    output = Path(args.output)
    if output.parent != Path("."):
        output.parent.mkdir(parents=True, exist_ok=True)
    written = save_baseline(output, fingerprints)
    print("Wrote %d fingerprint(s) to %s" % (written, args.output))
    return 0


def _cmd_rules(args) -> int:
    if args.format == "json":
        payload = {"rules": [rule.metadata() for rule in RULES]}
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0
    name_width = max(len(rule.name) for rule in RULES)
    sys.stdout.write("%-5s  %-8s  %-*s  %s\n" % ("ID", "SEVERITY", name_width, "NAME", "SUMMARY"))
    for rule in RULES:
        sys.stdout.write(
            "%-5s  %-8s  %-*s  %s\n"
            % (rule.id, rule.default_severity, name_width, rule.name, rule.summary)
        )
    return 0


def _cmd_explain(args) -> int:
    rule_id = args.rule_id.strip().upper()
    rule = RULE_INDEX.get(rule_id)
    if rule is None:
        sys.stderr.write("promptlint: unknown rule %s\n" % args.rule_id)
        sys.stderr.write("available: %s\n" % ", ".join(sorted(RULE_INDEX)))
        return 1
    lines = [
        "%s  %s  (%s)" % (rule.id, rule.name, rule.default_severity),
        "",
        "Summary: %s" % rule.summary,
        "",
        "Why: %s" % rule.rationale,
        "",
        "Bad example:",
    ]
    lines.extend("    " + line for line in rule.bad_example.rstrip("\n").splitlines())
    lines.append("")
    lines.append("Good example:")
    lines.extend("    " + line for line in rule.good_example.rstrip("\n").splitlines())
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _cmd_init(args) -> int:
    output = Path(args.output)
    if output.exists() and not args.force:
        sys.stderr.write(
            "promptlint: %s already exists (use --force to overwrite)\n" % output
        )
        return 1
    if output.parent != Path("."):
        output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(INIT_TEMPLATE, indent=2, ensure_ascii=False) + "\n")
    print("Created %s" % output)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    handlers = {
        "check": _cmd_check,
        "baseline": _cmd_baseline,
        "rules": _cmd_rules,
        "explain": _cmd_explain,
        "init": _cmd_init,
    }
    try:
        return handlers[args.command](args)
    except BrokenPipeError:  # pragma: no cover - depends on the consuming pipe
        return 0
    except (ConfigError, FileNotFoundError, ValueError, OSError) as exc:
        sys.stderr.write("promptlint: error: %s\n" % exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
