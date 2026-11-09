## Summary

<!-- What problem does this PR solve? One paragraph. -->

## Related issue

<!-- Fixes #123. If there is no issue, explain why the change is small enough to skip one. -->

## Type of change

- [ ] Bug fix (with a regression test)
- [ ] New rule
- [ ] Rule change (documented in docs/rules.md)
- [ ] CLI / output change
- [ ] Documentation only
- [ ] Refactor (no behavior change)

## Verification

```text
python -m unittest discover -s tests -v
python -m promptlint check examples/good --fail-on info
python -m promptlint check examples --config examples/promptlint.json
```

<!-- Paste the summary lines of the test run and both check commands. -->

## Checklist

- [ ] Tests pass on Python 3.9+ (version used: ____).
- [ ] New behavior is covered by a test; bug fix has a failing-then-passing test.
- [ ] `docs/rules.md` and `CHANGELOG.md` updated when rules change.
- [ ] No new third-party dependency.
- [ ] No secrets, personal data, or absolute local paths in the diff.
- [ ] Output remains deterministic (no timestamps, randomness, or locale-dependent sorting).
