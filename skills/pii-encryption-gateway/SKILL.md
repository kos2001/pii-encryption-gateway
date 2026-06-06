---
name: pii-encryption-gateway
description: >-
  Protect sensitive personal data so it is NEVER exposed to the language model
  while you still complete the task. Covers resident registration numbers
  (주민등록번호), salaries (연봉), employee IDs (사번), attendance (근태), bank
  accounts, phone numbers, emails, card and business-registration numbers, and
  IP addresses. Use this whenever a request involves any file, dataset, OR
  free-text document — an HR roster, payroll sheet, patient list, log file,
  incident memo, email draft, or meeting notes — that CONTAINS such
  personal/financial identifiers and you need to draft messages, summarize,
  build reports, classify, or transform it without leaking the raw values. Each
  handler uses their own secret key: values are tokenized before the model sees
  them and decrypted back only for the authorized handler afterward. Trigger
  this even if the user does not say "encrypt" — any task touching real
  주민번호/연봉/계좌/연락처 in a file or document should go through this gateway
  rather than reading the raw values. Not for writing privacy policies,
  explaining algorithms or checksums, generating regex/code, or
  already-anonymized data — only when actual sensitive values are present and
  must be withheld from the model.
---

# PII Encryption Gateway

You are handling data that contains sensitive personal information. The whole
point of this skill is that **you must complete the task without ever reading
the real sensitive values into your context.** If a salary or a resident
registration number appears in your reasoning or output, the protection has
failed — even if the final file is correct.

The mechanism that makes this possible: a bundled tool replaces each sensitive
value with a stable token like `[[SALARY:3f9a2c1d]]` and encrypts the originals
into a vault. You work entirely with tokens. A second tool decrypts the tokens
back into real values at the very end, for the authorized handler only.

Sensitive values are caught three ways, so PII is protected no matter where it
sits:

1. **By column name** — the schema in `pii_config.py`.
2. **By column shape** — `protect.py` value-samples each unlisted column; if its
   cells *are* a single PII entity (a renamed phone or RRN column), the whole
   column is tokenized, sealing even an odd off-format cell the per-value pass
   would miss. Auto-detected columns are listed in the protect summary so you
   can sanity-check them (names only, never values).
3. **By value shape** — the recognizers in `recognizers.py` match RRNs (dashed
   or 13-digit), phones (mobile/landline/+82, with -, ., or space separators),
   emails, accounts, cards, business registration numbers, and IPv4 addresses
   *mid-sentence* in free-text columns and tokenize just those spans.

A value-shaped match is tokenized even when its checksum is invalid; protection
is fail-safe. (Card numbers are the one exception — a 16-digit run that fails
Luhn is treated as a false positive and left alone.)

## The one rule that matters

**Never open the raw input file.** Do not `cat`, `Read`, `head`, `grep`, or
otherwise inspect the original CSV/JSON. The moment you do, real values enter
your context and the gateway is pointless. Treat the raw file as something you
can name and pass to scripts, but never look inside.

## Workflow

Work from the skill's `scripts/` directory (paths below are relative to it).

### 1. Protect

Pick the handler's key (the user provides it, or use the one already in the
task). Then tokenize:

```bash
python protect.py --key "<handler-key>" \
    --in <raw-file> --out protected.json --vault vault.json
```

`protected.json` is safe to read — every sensitive field is now a token. The
script's output reports only counts, never values. **Read `protected.json`, not
the raw file.**

**Unstructured documents.** If the input is a `.txt`/`.md` file (a memo, an
email draft, an incident report) rather than a roster, `protect.py` switches to
document mode automatically: it runs the value-shape recognizers over the whole
text, tokenizes the PII spans in place, and writes a *text* file with the prose
intact. Point `--out` at a text file and proceed the same way.

```bash
python protect.py --key "<handler-key>" \
    --in memo.md --out protected.md --vault vault.json
```

**Names in prose.** Recognizers seal patterned PII (RRN, phone, email, account,
card, business registration number) but not names, which have no value shape. When you know the names — in an
HR task they sit in the roster — pass them as a deny-list so they are sealed by
exact match too (zero false positives, still no dependency):

```bash
python protect.py --key "<handler-key>" --in memo.md --out protected.md \
    --vault vault.json --names-from employees.csv   # or --names "최민준,신다은"
```

`--names-from` reads the roster's name column; `--names` takes an explicit list.
This catches *known* names only. A third party not in the roster still won't be
detected — don't claim a document is name-safe for arbitrary names; say plainly
that only the supplied names are sealed.

### 2. Do the task on tokens

Read `protected.json` and complete the request. Refer to people and values by
their tokens. Because tokens are deterministic, the same person or value always
has the same token, so you can still group, match, and template correctly:

- "Draft a salary notice for 사번 E0023" → the employee ID is itself sensitive
  and tokenized in `protected.json`, so you cannot grep "E0023" there. Instead
  translate the reference the user gave you into its token and match that:

  ```bash
  python tokenize_value.py --key "<handler-key>" --type EMPNO --value E0023
  # -> [[EMPNO:1a2b3c4d]]   ← find this token in protected.json
  ```

  Then write the email with `[[NAME:...]]` and `[[SALARY:...]]` in place; the
  structure is yours, the values stay sealed. The same trick works for any known
  reference (a name, an account) — tokenize it, then match.
- "Per-employee attendance notice" → templatize with the `[[LATE:...]]`,
  `[[ABSENCE:...]]`, `[[LEAVE:...]]` tokens for each row.
- Non-sensitive columns (부서, 직급, 입사일) are left in clear text, so
  department- or title-level structure and grouping work normally. Employee IDs
  (사번) are sensitive and tokenized — group by them via their tokens, and use
  the lookup trick above when the user references one by its real value.

Write your output (the draft, report, or transformed file) to a file, keeping
the tokens intact. Do not invent tokens — only reuse ones that appear in
`protected.json`.

**Self-check before revealing.** Glance at your draft and confirm two things:
you never ran `cat`/`Read`/`head`/`grep` on the raw input, and every place that
should hold a sensitive value holds a `[[TYPE:hash]]` token rather than a real
name or number. If a real value somehow appears, you read something you
shouldn't have — start over from step 1.

### 3. Reveal

If your output contains no tokens at all — for example a pure aggregate report
built only from non-sensitive columns — there is nothing to restore, so skip
this step and deliver the file as-is. Otherwise:

Restore real values for the authorized handler:

```bash
python reveal.py --key "<handler-key>" --vault vault.json \
    --in <your-output-file> --out final.txt
```

`final.txt` is the deliverable with real names, salaries, and so on filled in. A
wrong key makes `reveal.py` fail rather than leak — that is the access control.

## What this gateway does and does not do

It guarantees the model never sees raw sensitive values, and that output is
fully reversible for the right handler. It is well suited to drafting
communications, per-record templating, routing, reformatting, and structural
reports.

It does **not** let the model do arithmetic on the protected values — you cannot
compute an average salary from `[[SALARY:...]]` tokens, because that is exactly
the information being withheld. If a task needs aggregate statistics over
sensitive numbers, compute them with a script over the raw file (so the numbers
never enter the model) and feed only the aggregate back in. Say so plainly
rather than pretending to analyze tokens.

One more honest limit: tokens are deterministic, so equal values produce equal
tokens. That is what makes grouping work, but it means an observer of the
protected data can tell *which records share a value* and how frequently each
recurs — never the value itself without the key, but the equality pattern is
visible. For a low-cardinality field (e.g. attendance counts 0–15) that pattern
can be informative. If even equality must be hidden for a field, it should not
be tokenized deterministically (it would need randomized per-cell tokens, which
costs you the ability to group on it).

## Files

- `scripts/protect.py` — tokenize sensitive fields, build the vault
- `scripts/reveal.py` — restore real values from the vault (key-gated)
- `scripts/tokenize_value.py` — token for a known value, to locate a record by
  a sensitive reference (e.g. a 사번) without reading the raw file
- `scripts/crypto_core.py` — stdlib-only key derivation, AEAD, tokenization
- `scripts/pii_config.py` — which columns are sensitive (edit to adapt schema)
- `scripts/recognizers.py` — value-shape PII detection (RRN/phone/email/account/
  card/business-reg-number) with checksum validation, column inference for
  renamed columns, and deny-list name matching — catches PII in free-text,
  mis-named columns, and documents
