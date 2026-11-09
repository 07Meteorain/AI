# Demo output

These files are real output from `promptlint 1.0.0`, not screenshots or mockups.
Regenerate them from the project root:

```bash
python -m promptlint check examples --config examples/promptlint.json --output demo/check_text.txt
python -m promptlint check examples --config examples/promptlint.json --format json --output demo/check.json
python -m promptlint check examples --config examples/promptlint.json --format sarif --output demo/check.sarif
python -m promptlint rules > demo/rules.txt
```

The first three commands exit `1` because the example set deliberately contains
findings; that is the expected behavior, not a failure of the demo.

| File | What it shows |
| --- | --- |
| `check_text.txt` | human-readable report with file, line, column, severity, rule |
| `check.json` | machine-readable report with summary and per-file findings |
| `check.sarif` | SARIF 2.1.0 with rule metadata and partial fingerprints, ready for GitHub Code Scanning |
| `rules.txt` | the rule table printed by `promptlint rules` |

`check.json` and `check.sarif` are generated from the same run as `check_text.txt`,
so their counts must agree: 12 findings, 5 errors, 7 warnings.
