"""promptlint: static analysis for LLM prompt templates."""

from __future__ import annotations

from .config import Config, ConfigError, discover_config, load_config
from .engine import lint_files, lint_text
from .version import __version__

__all__ = [
    "Config",
    "ConfigError",
    "__version__",
    "discover_config",
    "lint_files",
    "lint_text",
    "load_config",
]
