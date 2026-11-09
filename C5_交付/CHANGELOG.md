# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-09

### Added

- `promptlint` CLI with `check`, `baseline`, `rules`, `explain`, and `init`.
- 12 rules: PL001–PL012 covering empty prompts, placeholder declarations and
  syntax, secrets, personal data, output contracts, duplicate instructions,
  untrusted-input boundaries, token budget, invisible characters, and front
  matter validity.
- Text, JSON, and SARIF 2.1.0 reporters. SARIF includes rule metadata and
  partial fingerprints, so GitHub Code Scanning can deduplicate results.
- Baseline support with line-independent fingerprints, so an existing
  repository can adopt the linter without silencing new findings.
- `promptlint.json` configuration with per-rule severity overrides, token
  budget, and exclusion patterns; discovered upward from the current directory.
- Python API: `lint_text()`, `lint_files()`, `Config`, and `Finding.as_dict()`.
- 81 `unittest` tests, runnable without third-party packages.
- Examples and a `demo/` directory with real text, JSON, and SARIF output.
- CI on Python 3.9–3.13 (see `.github/workflows/ci.yml`; the monorepo uses the
  repository-level `c5-promptlint.yml` workflow).

### Notes

- Token counts are deterministic estimates (±30%), not BPE-exact counts.
- PL007/PL008/PL009 are heuristics; documented limits live in `docs/rules.md`.
- Front matter intentionally supports a small subset of YAML.

[Unreleased]: https://github.com/07Meteorain/AI/compare/c5-v1.0.0...master
[1.0.0]: https://github.com/07Meteorain/AI/tree/c5-v1.0.0
