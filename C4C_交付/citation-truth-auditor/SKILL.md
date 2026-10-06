---
name: citation-truth-auditor
description: >
  Audit every citation in a BibTeX (.bib), LaTeX (.tex) or Markdown (.md) file for
  REALITY, not just formatting — verify each reference actually exists by querying
  authoritative sources (Crossref, arXiv, OpenAlex) with DOI/arXiv-ID fast paths, and
  classify each entry as VERIFIED / PARTIAL / FABRICATED / UNCHECKED with a reason
  code and evidence URL. Detects AI-hallucinated citations (fake papers, plausible
  but non-existent titles, DOI that does not resolve, future years, generic
  word-salad titles, real-author + real-title mismatch). Outputs a Markdown audit
  report, an optional field-corrected .fixed.bib, machine-readable JSON, and a
  non-zero exit code when fabricated references are found (CI-ready).
  Use whenever the user says "check my references", "audit citations", "verify my
  bibliography", "are these references real", "find fake citations", "hallucinated
  references", "引用核查", "核查参考文献", "引用真伪", "查重引用", "编造引用",
  "references.bib 核查", "论文引用检查", "bib validation", "check citations",
  "citation audit", "reference verification", "check if my citations exist",
  or hands over a .bib / references.bib / paper.tex and asks whether the references
  are trustworthy, accurate, or real. Also trigger before submitting a paper,
  thesis, or academic report, or when a supervisor/reviewer questions a citation.
---

# Citation Truth Auditor — 引用真伪审计器

## Purpose

**The problem this skill exists to solve.**

Large Language Models fabricate citations. Fluently. A generated bibliography
looks *perfect* — plausible authors, real venues, well-formed DOIs, correct
year formatting — but a meaningful fraction of those references do not exist.
This is not a rare edge case; it is the single most common failure mode of
AI-assisted academic writing.

The failure is dangerous precisely *because* the output looks right. A student
who skim-checks their own bibliography finds nothing alarming. The damage
surfaces only later:

| When it surfaces | Consequence |
|---|---|
| A reviewer tries to look up a source | Loss of credibility |
| A supervisor asks "where is this from?" | Must retract |
| A follow-up researcher builds on a fake claim | Wasted time, propagated error |
| The paper is published | Permanent, citable record of a fabrication |

**This skill replaces eyeballing with querying.** It takes a bibliography file
and returns a per-entry verdict backed by evidence from authoritative
registries, so the question "are my references real?" gets an answer with a
receipt attached.

**Scope note — what this does and does not do.**

- ✅ Does: determine whether a cited work **exists**; flag metadata that
  contradicts the authoritative record; catch the classic AI-hallucination
  patterns.
- ❌ Does not: judge whether the real paper *supports* your claim. Verifying
  existence is a precondition for reading the paper, not a substitute for it.
  A VERIFIED citation can still be misused. Say so when reporting.
- ❌ Does not: judge writing quality, argument structure, or originality.

## Input / Output（IO 明确）

**Input (one or more):**
- `.bib` — BibTeX bibliography
- `.tex` — LaTeX source (its `\cite{...}` keys and/or embedded `thebibliography`)
- `.md` — Markdown with citations

**Output:**

| Artifact | Description |
|---|---|
| Terminal report | One block per entry: verdict, metadata, reason, suggested fix |
| `<stem>.audit.md` | Markdown report — summary table + per-entry detail + fix plan |
| `<stem>.fixed.bib` | (only with `--fix`) corrected entries; fabricated ones **commented out, never deleted** |
| `<stem>.audit.json` | (only with `--json`) machine-readable results for CI |
| Exit code | `0` = clean, `1` = fabricated references found, `2` = input unreadable |

**The four verdicts (this is the verifiable contract):**

| Verdict | Meaning | Action |
|---|---|---|
| `VERIFIED` | Found in an authoritative source; title/authors/year consistent | Keep |
| `PARTIAL` | Found, but at least one metadata field contradicts the source | Fix fields, or confirm manually |
| `FABRICATED` | No matching work exists, and/or hallucination fingerprints fired | **Remove or replace before submission** |
| `UNCHECKED` | Evidence insufficient (network down, ambiguous) | Verify manually |

## Requirements

- Python 3.8+
- **Zero third-party dependencies** — standard library only (`urllib`, `json`,
  `re`, `difflib`, `xml.etree`, `concurrent.futures`). No `pip install`.
- Network access to `api.crossref.org`, `export.arxiv.org`, `api.openalex.org`.
  All three are free and need no API key.

This matters: a skill that needs `pip install` will fail on someone else's
machine and never get used. Run it with `--offline` when there is no network.

## Workflow

### Step 1 — Locate the bibliography

Find the `.bib` file, or extract citations from `.tex`. If the user just says
"check my references", ask which file — or locate it:

```bash
find . -name "*.bib" -not -path "*/node_modules/*" 2>/dev/null
grep -rE '\\cite[a-zA-Z]*\{' --include="*.tex" -l . 2>/dev/null
```

Prefer auditing the `.bib` directly: it carries structured metadata, whereas
`.tex` gives you only cite keys.

### Step 2 — Run the auditor

```bash
python3 scripts/citation_auditor.py references.bib
```

Common variations:

```bash
# audit several files at once
python3 scripts/citation_auditor.py refs.bib paper.tex

# generate a corrected bibliography + machine-readable output
python3 scripts/citation_auditor.py refs.bib --fix --json --out ./audit_out

# slow network / rate-limited: fewer workers, longer timeout
python3 scripts/citation_auditor.py refs.bib --jobs 2 --timeout 20

# no network: static fingerprint check only
python3 scripts/citation_auditor.py refs.bib --offline

# tighten or loosen the match threshold
python3 scripts/citation_auditor.py refs.bib --threshold 0.90
```

**Exit codes are meaningful** — `1` means "fabricated references found", so this
drops into CI as a guard:

```bash
python3 scripts/citation_auditor.py refs.bib || echo "BLOCKED: fake citations — do not submit"
```

### Step 3 — Read the verdicts and act

Work in this order. Do not skip to the summary — read the per-entry reasons,
because the *reason* determines the fix.

1. **`FABRICATED`** — Do not submit with these present. Either delete the entry
   or replace it with a real source you have actually read. If the surrounding
   prose genuinely needs support and you have no real source, rewrite the claim
   as a limitation ("evidence remains scarce") rather than inventing a citation.
2. **`PARTIAL`** — Apply the suggested field values. For each field, confirm the
   suggested value is more authoritative than what you wrote before overwriting.
3. **`VERIFIED`** — Keep.
4. **`UNCHECKED`** — Check manually. Do not treat "not proven fake" as "verified".

### Step 4 — Report honestly

When presenting results to the user:

- State the counts **and** the limitation: existence is verified, *support for
  your claim is not*.
- Quote the reason codes rather than paraphrasing them into vague warnings.
- If everything is clean, say so plainly — do not manufacture concern.
- If something is flagged, give the concrete fix, not just the alarm.

## How detection works

Understanding the mechanism helps you handle edge cases correctly.

### Query strategy (fast paths first)

1. **DOI direct lookup** (`api.crossref.org/works/{doi}`) — highest confidence.
   A resolving DOI plus a matching title is nearly conclusive.
2. **arXiv ID direct lookup** (`export.arxiv.org/api/query?id_list=`) — for
   preprints identified by `eprint` / `archivePrefix`.
3. **Title search** across Crossref and OpenAlex — the fallback, and the
   ambiguous one. Requires similarity scoring.

### Matching and scoring

- **Title similarity** blends character-level ratio (`difflib`) with token-level
  Jaccard, weighted toward character similarity for short titles.
- **Author match** compares *surnames*, extracted correctly from both BibTeX
  `Last, First` and API `First Last` forms.
- **Candidate ranking** is `author match → year proximity → title similarity →
  citation count`. All four matter:
  - *Author* prevents a same-title/different-author paper from winning.
  - *Year* prevents a later reprint or re-indexed version from displacing the
    record the bibliography actually meant.
  - *Similarity and citation count* break remaining ties.

### Version drift vs. real error

A common false positive: title and authors match perfectly, but the source
reports a different year. This usually means the registry holds a reprint,
revision, or re-indexed version of the same work — **not** that you made a
mistake. The auditor reports this as `PARTIAL` with an explicit version-drift
reason and **refuses to auto-rewrite the `year` field**, because the source's
year is not automatically more authoritative than yours.

### Hallucination fingerprints

Static heuristics that flag likely fabrications before/without network results:

| Fingerprint | Typical severity |
|---|---|
| Title built from high-frequency generic words ("A Deep Intelligent Neural Network…") | High |
| Template venue ("In the Proceedings of the International Conference on…") | High |
| Impossible year (future, or before ~1600) | High |
| Malformed DOI | High |
| Inverted page range (`134--112`) | High |
| Missing author field | High |

See `references/hallucination_patterns.md` for the full catalogue, real
fabrication examples, and the reasoning behind each pattern.

### Source characteristics and known limits

| Source | Strength | Limitation |
|---|---|---|
| Crossref | Authoritative DOI registry | Not indexed for books, many CS preprints, non-DOI venues |
| arXiv | Precise ID lookup, high precision | Preprints only; no peer-review status |
| OpenAlex | Broad coverage (254 hits for a common title) | Can carry unusual `publication_year` from merged/re-indexed records |

**Known false-positive cases (do not "fix" these blindly):**
- Conference papers with no DOI, matched to a different year's proceedings.
- Chinese-language venues and books with no Crossref or OpenAlex record.
- Theses, technical reports, standards documents, and self-published works.
- Preprint → conference version pairs where both are legitimately cited.

For all of these, `UNCHECKED`/`PARTIAL` is the honest answer. Confirm by
hand and keep your metadata if the source is wrong.

## Edge Cases

The auditor handles these; you should still expect them.

| Situation | Behaviour |
|---|---|
| **No network** | `--offline`: static fingerprints only; everything else `UNCHECKED`. Never guesses. |
| **Rate limiting (HTTP 429)** | Exponential backoff with retry; degrades to remaining sources instead of failing. |
| **Empty / unreadable `.bib`** | Exits `2` with a clear message; never reports "0 fabricated". |
| **`\cite` key with no `.bib` entry** | Reported as missing — will break LaTeX compilation. |
| **`.bib` entry never cited in `.tex`** | Reported as unused (often a copy-paste leftover). |
| **Nested braces in titles** | Parser tracks brace depth; LaTeX-style `{Deep}` survives intact. |
| **Unclosed entry in a large file** | Hard scan cap prevents one malformed entry from swallowing the file. |
| **`"quoted"` vs `{braced}` values** | Both supported. |
| **Chinese / non-ASCII authors** | Unicode-safe throughout; no mojibake. |
| **Duplicate entries, same paper** | Both audited; dedupe in the `.bib` afterwards. |
| **A real paper with a misleading title** | Fingerprint heuristics may fire on a legitimate citation — reason code tells you; verify by hand. |
| **`pages` field with single page** | Only inverted ranges are flagged. |
| **Corporate author `{The Coq Team}`** | Braced institutional names handled as a single unit. |
| **`;`-separated authors** | `and`, `;`, and `others` separators all supported. |
| **DOI prefix absent from Crossref** | `10.48550/arxiv.*` routes straight to arXiv; `10.5555/...` falls back to title search. |
| **Title with version suffix** | `"…Reference Manual"` vs `"…Manual - version 8.19.0"` → recognised as the same work. |
| **Software manual / technical doc** | Not indexed by any source → `UNCHECKED` with explanation, never `FABRICATED`. |

**Never** present `UNCHECKED` as "fine". It means the auditor could not reach a
verdict. Reporting it as clean is the one failure mode that destroys the value
of the tool.

## Extending the skill

- **Add a source** — implement a `query_*(...)` returning a candidate dict
  (`source`, `title`, `year`, `authors`, `venue`, `doi`, `url`, `_sim`) and add
  it to the `candidates` list in `audit_entry`. The schema is small and stable.
- **Tune sensitivity** — `--threshold` trades recall for precision. Raise it to
  reduce false alarms on obscure venues; lower it for aggressive screening.
- **Add fingerprints** — extend `hallucination_fingerprints()` with a regex and
  a severity. Severities: `2` = near-certain problem, `1` = suspicious,
  `0` = informational.
- **CI gate** — `citation_auditor.py refs.bib || exit 1` blocks a commit or a
  submission when fabricated references appear.

## Reference files

| File | Load when |
|---|---|
| `references/hallucination_patterns.md` | You need to justify a `FABRICATED` verdict, or a fingerprint looks questionable |
| `references/data_sources.md` | You need the exact API endpoints, rate limits, and response fields to extend or debug the auditor |