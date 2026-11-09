"""Baseline support: suppress accepted findings without hiding new ones.

A fingerprint is built from the project-relative path, the rule id, the
message, and the source line. Line numbers are deliberately excluded so moving
code around does not resurrect every accepted finding.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, List, Set, Tuple

from .model import Finding

BASELINE_FILENAME = ".promptlint-baseline.json"
BASELINE_VERSION = 1


def fingerprint(rel_path: str, finding: Finding, occurrence: int = 0) -> str:
    payload = "\x00".join(
        [
            rel_path.replace("\\", "/"),
            finding.rule_id,
            finding.message,
            finding.snippet.strip(),
            str(occurrence),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def load_baseline(path: Path) -> Set[str]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("baseline must be a JSON object")
    fingerprints = data.get("fingerprints", [])
    if not isinstance(fingerprints, list) or not all(isinstance(item, str) for item in fingerprints):
        raise ValueError("'fingerprints' must be a list of strings")
    return set(fingerprints)


def collect_fingerprints(results: Iterable[Tuple[object, List[Finding]]]) -> List[str]:
    values = []
    counts = {}
    for source, findings in results:
        for finding in findings:
            rel_path = source.rel_path.replace("\\", "/")
            key = (rel_path, finding.rule_id, finding.message, finding.snippet.strip())
            occurrence = counts.get(key, 0)
            counts[key] = occurrence + 1
            values.append(fingerprint(source.rel_path, finding, occurrence))
    return sorted(set(values))


def save_baseline(path: Path, fingerprints: Iterable[str]) -> int:
    values = sorted(set(fingerprints))
    payload = {"version": BASELINE_VERSION, "fingerprints": values}
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return len(values)
