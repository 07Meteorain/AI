"""Lint orchestration: discover files, run rules, apply configuration."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .baseline import fingerprint
from .config import Config
from .model import Finding, SourceFile
from .parser import parse_prompt
from .rules import RULES

PROMPT_EXTENSIONS = {".prompt", ".tpl", ".tmpl", ".md", ".txt"}


class CheckResult:
    def __init__(self, files: List[Tuple[SourceFile, List[Finding]]], suppressed: int):
        self.files = files
        self.suppressed = suppressed

    @property
    def findings(self) -> List[Finding]:
        return [finding for _, findings in self.files for finding in findings]

    @property
    def file_count(self) -> int:
        return len(self.files)


def lint_source(source: SourceFile, config: Config) -> List[Finding]:
    parsed = parse_prompt(source.text)
    findings: List[Finding] = []
    for rule in RULES:
        severity = config.severity_for(rule.id, rule.default_severity)
        if severity == "off":
            continue
        for finding in rule.check(parsed, source, config):
            finding.severity = severity
            findings.append(finding)
    findings.sort(key=lambda item: (item.line, item.column, item.rule_id))
    return findings


def make_source(text: str, path: str, rel_path: Optional[str] = None) -> SourceFile:
    return SourceFile(
        path=path,
        rel_path=rel_path or path,
        text=text,
        lines=text.splitlines(),
    )


def lint_text(
    text: str,
    *,
    path: str = "<stdin>",
    rel_path: Optional[str] = None,
    config: Optional[Config] = None,
) -> List[Finding]:
    return lint_source(make_source(text, path, rel_path), config or Config())


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _excluded(rel_path: str, parts: Sequence[str], patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        if any(char in pattern for char in "*?["):
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, pattern.rstrip("/") + "/**"):
                return True
        elif pattern in parts:
            return True
    return False


def collect_files(paths: Sequence[str], config: Config) -> List[Path]:
    selected: Dict[str, Path] = {}
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            selected[str(path.resolve())] = path
            continue
        if not path.is_dir():
            raise FileNotFoundError("no such file or directory: %s" % raw)
        for candidate in sorted(path.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in PROMPT_EXTENSIONS:
                continue
            try:
                rel = candidate.relative_to(path).as_posix()
            except ValueError:
                rel = candidate.name
            if _excluded(rel, candidate.relative_to(path).parts, config.exclude):
                continue
            selected[str(candidate.resolve())] = candidate
    return sorted(selected.values(), key=lambda item: _relative(item))


def lint_files(paths: Sequence[str], config: Config) -> List[Tuple[SourceFile, List[Finding]]]:
    results: List[Tuple[SourceFile, List[Finding]]] = []
    for path in collect_files(paths, config):
        text = path.read_text(encoding="utf-8", errors="replace")
        source = make_source(text, str(path), _relative(path))
        results.append((source, lint_source(source, config)))
    return results


def apply_baseline(
    results: List[Tuple[SourceFile, List[Finding]]], known: set
) -> Tuple[List[Tuple[SourceFile, List[Finding]]], int]:
    if not known:
        return results, 0
    filtered: List[Tuple[SourceFile, List[Finding]]] = []
    suppressed = 0
    counts = {}
    for source, findings in results:
        kept = []
        for finding in findings:
            rel_path = source.rel_path.replace("\\", "/")
            key = (rel_path, finding.rule_id, finding.message, finding.snippet.strip())
            occurrence = counts.get(key, 0)
            counts[key] = occurrence + 1
            if fingerprint(source.rel_path, finding, occurrence) in known:
                suppressed += 1
            else:
                kept.append(finding)
        filtered.append((source, kept))
    return filtered, suppressed
