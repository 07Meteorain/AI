# Contributing to promptlint

Thanks for taking the time to contribute. This project is intentionally small:
**zero runtime dependencies, deterministic output, every rule documented and tested.**
Those constraints are the product, so please keep them in mind.

By participating you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a false positive** — the most valuable report. Include the prompt
  (redact secrets and personal data), the command, and the output.
- **Report a missed pattern** — a shape of broken template the rules do not catch.
- **Add a rule** — see the checklist below.
- **Improve docs** — especially the "known limits" sections.
- **Fix a bug** — please add a regression test that fails before the fix.

## Development setup

No virtual environment or dependency install is required.

```bash
git clone https://github.com/07Meteorain/AI.git
cd AI/C5_交付
python -m unittest discover -s tests -v
```

Python 3.9 or newer. To use the console entry point locally:

```bash
python -m pip install -e .
promptlint --version
```

## Before you open a pull request

Run all four commands and paste the relevant output in the PR:

```bash
python -m unittest discover -s tests -v
python -m promptlint check examples/good --fail-on info
python -m promptlint check examples --config examples/promptlint.json   # expected exit 1
python -m promptlint rules
```

The third command is expected to fail: it lints the deliberately broken examples
and should report 12 problems. CI treats a *different* number as a regression.

## Adding a rule

1. Pick the next free `PL0xx` id. Ids are never reused or renumbered.
2. Add a class in the right module:
   - `rules/structure.py` — template shape and placeholders;
   - `rules/safety.py` — secrets, personal data, injection surface, invisible chars;
   - `rules/quality.py` — output contract, duplication, budget;
   - `rules/meta.py` — the file/config itself.
3. Implement `check(self, parsed, source, config)` and build findings with
   `make_finding(...)`. Always give a 1-based `line` and `column`.
4. Register it in `promptlint/rules/__init__.py` (order controls report order).
5. Write tests in `tests/` covering:
   - the finding fires on a minimal sample;
   - it does **not** fire on a clean sample;
   - the default severity and message are stable.
6. Document it in `docs/rules.md` **and** add a `CHANGELOG.md` entry.
7. Include the rule's `summary`, `rationale`, `bad_example`, `good_example` on the
   class — `promptlint explain` and the SARIF metadata read them.

### Rule design checklist

- [ ] It catches something a reviewer would call a real defect, not a style preference.
- [ ] The message says what is wrong and where, not just which rule fired.
- [ ] The hint says what to do next.
- [ ] It skips fenced code and inline code unless the check is about content
      (secrets still matter inside code blocks).
- [ ] It does not read the filesystem, the network, or global state.
- [ ] It is deterministic: no randomness, no timestamps, no locale-dependent sorting.

## Style

- PEP 8, 4 spaces, ~100 columns, `from __future__ import annotations` at the top.
- Type hints on public functions; small pure helpers where possible.
- No new third-party dependencies. This is a hard constraint, not a preference.
- Comments explain *why*, not *what*.

## Commit messages

Conventional Commits, in the imperative mood:

```text
feat(rules): add PL013 for duplicated system/user blocks
fix(parser): keep inline-code offsets stable
test(cli): cover --fail-on none
docs: clarify baseline fingerprint semantics
```

Keep each commit focused. If a change touches rules and docs, one commit is fine.

## Pull request checklist

- [ ] Tests pass locally on Python 3.9+ (state the version you used).
- [ ] New behavior has a test; fixed bug has a regression test.
- [ ] `docs/rules.md` updated for any rule change.
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`.
- [ ] No secrets, personal data, or absolute local paths in the diff.
- [ ] The PR description explains the problem, not just the patch.

## Review process

- One maintainer approval is enough for docs and tests.
- Rule changes and CLI behavior changes need a second look and a changelog entry.
- A false-positive report may be resolved by documenting the limit and suggesting
  `off`/baseline, rather than by weakening the rule silently.

## Security

Do not report vulnerabilities in a public issue. See [SECURITY.md](SECURITY.md).
