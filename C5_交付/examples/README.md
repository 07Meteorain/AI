# Examples

Every rule is exercised by at least one file here. The `good/` directory is the
CI gate: it must produce **zero** findings. The `bad/` directory is a fixed
regression sample: with [`promptlint.json`](promptlint.json) it must produce
**12 findings** across 4 files.

```bash
# Expected: "No problems found in 2 files", exit 0
python -m promptlint check examples/good --fail-on info

# Expected: 12 problems, exit 1
python -m promptlint check examples --config examples/promptlint.json
```

| File | Demonstrates |
| --- | --- |
| `good/support_reply.prompt` | declared vars, wrapped user input, JSON output contract |
| `good/code_review.prompt` | XML-delimited code diff, Markdown output contract |
| `bad/leaky.prompt` | PL005 secret, PL006 email/phone, PL007 contract, PL008 duplicate |
| `bad/malformed.prompt` | PL003 unused var, four PL004 syntax errors |
| `bad/unsafe_context.prompt` | PL009 undelimited user input |
| `bad/bloated.prompt` | PL010 token budget (with the demo config's 120-token limit) |

The demo config sets `max_tokens` to 120 so a short file can demonstrate PL010
without shipping a 4000-token prompt. In a real project keep the default 4000 or
set your own budget.

If you change a rule deliberately, update the expected count in both this file
and `.github/workflows/ci.yml`.
