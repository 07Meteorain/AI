# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 1.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Email `2025105220114 [at] student.local` with:

- the promptlint version (`python -m promptlint --version`);
- a minimal reproduction (redact secrets and personal data);
- the impact you believe it has.

You can expect an acknowledgement within 7 days. This is a single-maintainer
student project, so please allow reasonable time for a fix before disclosure.

## Scope

In scope:

- rules that fail to detect the credential/PII shapes they claim to detect;
- report or SARIF output that reveals a secret in full;
- path handling that could read or write outside the given paths;
- a configuration that silently disables checks without saying so.

Out of scope:

- a prompt that is semantically unsafe but contains no machine-detectable pattern;
- false positives on unusual but legitimate text (report them as bugs, not
  vulnerabilities);
- the security of the model or provider you send prompts to.

## Handling secrets

If you accidentally commit a live credential, **rotate it first**, then remove it
from history. Deleting the line in a new commit is not enough: the value remains
in the git object database and in forks. promptlint masks values in its own
reports, but it cannot undo a leak that already happened.
