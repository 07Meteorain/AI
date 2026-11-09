"""Configuration loading and discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

VALID_SEVERITIES = {"error", "warning", "info", "off"}
DEFAULT_MAX_TOKENS = 4000
DEFAULT_EXCLUDE = [".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache"]
CONFIG_FILENAME = "promptlint.json"


class ConfigError(ValueError):
    """Raised when promptlint.json is malformed or references unknown rules."""


@dataclass
class Config:
    rules: Dict[str, str] = field(default_factory=dict)
    max_tokens: int = DEFAULT_MAX_TOKENS
    exclude: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))

    def severity_for(self, rule_id: str, default: str) -> str:
        return self.rules.get(rule_id, default)


def default_config() -> Config:
    return Config()


def load_config(path: Path) -> Config:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc))
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ConfigError("%s is not valid JSON: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ConfigError("%s must contain a JSON object" % path)

    rules: Dict[str, str] = {}
    rules_raw = data.get("rules", {})
    if not isinstance(rules_raw, dict):
        raise ConfigError("'rules' must be an object mapping rule ids to severities")
    for rule_id, severity in rules_raw.items():
        if not isinstance(severity, str) or severity not in VALID_SEVERITIES:
            raise ConfigError(
                "severity for %s must be one of %s" % (rule_id, sorted(VALID_SEVERITIES))
            )
        rules[str(rule_id)] = severity

    max_tokens = data.get("max_tokens", DEFAULT_MAX_TOKENS)
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
        raise ConfigError("'max_tokens' must be a positive integer")

    exclude = data.get("exclude", list(DEFAULT_EXCLUDE))
    if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
        raise ConfigError("'exclude' must be a list of strings")

    return Config(rules=rules, max_tokens=max_tokens, exclude=list(exclude))


def discover_config(start: Path) -> Optional[Path]:
    """Walk upward from *start* looking for promptlint.json."""
    current = start.resolve()
    for directory in [current] + list(current.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_effective_config(explicit: Optional[str], cwd: Optional[Path] = None) -> tuple:
    """Load config, returning ``(config, path_or_None)``.

    An explicitly requested config must exist; an auto-discovered one is optional.
    """
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError("config file not found: %s" % explicit)
        return load_config(path), path
    found = discover_config(cwd or Path.cwd())
    if found:
        return load_config(found), found
    return default_config(), None
