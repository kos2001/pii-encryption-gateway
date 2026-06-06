---
name: pii-encryption-gateway
description: >-
  De-identify sensitive personal data so the language model never sees raw
  identifiers, while you still complete the task — including computing
  statistics. By default, direct identifiers (names/이름, 주민등록번호, 사번,
  bank accounts, phones, emails, cards, business-registration numbers, IPs) are
  replaced with stable tokens, and numeric attributes (연봉, 근태) are kept raw
  so you can still compute averages, sums, counts, and distributions. Use
  whenever a request involves an HR roster, payroll sheet, patient list, log
  file, incident memo, email draft, or any file/document containing personal
  identifiers and you need to analyze, aggregate, draft messages, summarize,
  build reports, classify, or transform it without leaking identities. A
  stronger keyed mode additionally encrypts every value (identifiers AND
  numbers) into a vault for per-person, key-gated, at-rest protection. Trigger
  this even if the user does not say "encrypt" or "de-identify" — any task
  touching real 이름/주민번호/연봉/계좌/연락처 in a file or document should go
  through this rather than reading the raw values. Not for writing privacy
  policies, explaining algorithms or checksums, generating regex/code, or
  already-anonymized data.
---

# PII De-identification Gateway

You are handling data that contains sensitive personal information. The point of
this skill is that **you complete the task without ever reading raw identifiers
into your context.** If a name, a resident registration number, or an account
number appears in your reasoning or output, the protection has failed — even if
the final file is correct.

The **default approach is keyless de-identification**: a bundled tool replaces
each direct identifier with a stable token like `[[NAME:3f9a2c1d]]` and keeps
the originals in a plaintext map for later restoration. Crucially, **numeric
attributes (salary, attendance) are left raw**, so you can still compute
averages, sums, and distributions directly — the model sees the numbers but not
*whose* they are. A second tool restores the identifiers at the very end.

For tasks that also need **at-rest encryption and per-person, key-gated access
control**, there is a stronger **keyed gateway** (see the bottom section) that
encrypts *every* value — including the numbers — into a vault. It is more
protective but seals the numbers, so it cannot compute statistics.

## The one rule that matters

**Never open the raw input file, and never open the map/vault.** Do not `cat`,
`Read`, `head`, or `grep` the original CSV/JSON/document, nor `map.json` /
`vault.json`. The moment you do, real identifiers enter your context and the
gateway is pointless. Treat those files as things you can name and pass to
scripts, but never look inside. Work only from the de-identified output.

## How PII is detected (shared by both modes)

Identifiers are caught three ways, so they are protected no matter where they sit:

1. **By column name** — the schema in `pii_config.py`.
2. **By column shape** — value-sampling classifies a renamed column (e.g. a
   phone column not named "전화") from its values, sealing even an odd off-format
   cell the per-value pass would miss.
3. **By value shape** — the recognizers in `recognizers.py` match RRNs (dashed
   or 13-digit), phones (mobile/landline/+82, with -, ., or space separators),
   emails, accounts, cards, business registration numbers, and IPv4 addresses
   *mid-sentence* in free text (full-width digits included). A format match is
   sealed even if its checksum is invalid (fail-safe); CARD/BRN are the
   exception — a checksum failure is treated as a false positive.

**Names in prose** have no value shape. When you know them — in an HR task they
sit in the roster — pass them as a deny-list (`--names-from roster.csv` or
`--names "최민준,신다은"`) so they are sealed by exact match (zero false
positives). Only the supplied names are sealed; a third party not in the roster
is not detected — say so plainly rather than claiming a document is name-safe.

## Default workflow: de-identify

Work from the skill's `scripts/` directory.

### 1. De-identify

```bash
python deidentify.py --in <raw-file> --out deidentified.json --map map.json \
    [--names-from <roster.csv>]
```

Direct identifiers (이름·주민번호·사번·계좌·전화·이메일, plus card/BRN/IP in free
text) become tokens; numeric and non-sensitive columns (연봉·근태·부서·직급) stay
**raw**. `.txt`/`.md` documents are supported too — only identifier spans are
tokenized, prose stays intact. The summary reports counts only, never values.
**Read `deidentified.json`, not the raw file.**

### 2. Work on the de-identified file (analysis included)

Read `deidentified.json` and complete the request:

- **Statistics / aggregation** — because numbers stayed raw, compute averages,
  sums, counts, group-bys directly (e.g. "부서별 평균 연봉": group by the
  clear-text 부서, average the raw 연봉). Identities never enter the result.
- **Per-record templating** — refer to people by their tokens (`[[NAME:...]]`).
  Tokens are deterministic, so the same person always has the same token —
  grouping, matching, and templating still work.
- Non-sensitive columns (부서, 직급, 입사일) are clear text; use them freely for
  structure and grouping.

Write your output to a file. If it is a pure aggregate (no identifier tokens),
it contains no PII and is ready as-is.

**Self-check.** Confirm you never read the raw file or the map, and that every
identifier slot holds a `[[TYPE:hash]]` token, not a real name/number. A raw
identifier appearing means you read something you shouldn't have — start over.

### 3. Re-identify (only if your output contains identifier tokens)

```bash
python reidentify.py --map map.json --in <your-output> --out final.json
```

Restores identifiers from the plaintext map. A pure statistics report has no
tokens, so skip this step and deliver it directly.

## Stronger option: keyed gateway (per-person + at-rest encryption)

Use this **instead** of de-identify when the task needs the originals encrypted
at rest and restorable only by a key holder — e.g. drafting per-person notices
from data that must stay sealed on disk. It tokenizes **every** sensitive value
(identifiers *and* numbers) and encrypts the originals into a key-gated vault;
a wrong key fails rather than leaks. Because the numbers are sealed too, it
**cannot compute statistics** — do aggregates with a script over the raw file
and feed only the result back in.

```bash
python protect.py --key "<handler-key>" --in <raw-file> \
    --out protected.json --vault vault.json [--names-from roster.csv]
# ... work on protected.json (tokens only) ...
python reveal.py --key "<handler-key>" --vault vault.json \
    --in <your-output> --out final.txt          # wrong key fails, never leaks
```

`tokenize_value.py --key … --type EMPNO --value E0023` gives the token for a
known reference, to locate a record in `protected.json` without reading the raw
file.

## Choosing between them

| Goal | Use |
|------|-----|
| Statistics / aggregation, reports, analysis | **de-identify** (numbers raw) |
| Hide identities but keep numbers usable | **de-identify** |
| Per-person output + at-rest encryption + key access control | **keyed gateway** |
| Even the de-linked numbers must not reach the model | script-computed aggregates only |

## Honest limits

- **De-identify exposes the numbers themselves** (de-linked from names). That is
  what makes statistics possible; if even de-linked salaries must not reach the
  model, compute aggregates with a script and pass only the result.
- **The map is plaintext** (de-identify mode has no key/encryption) — `map.json`
  is as sensitive as the originals; guard it like the raw file. The keyed
  gateway's vault is encrypted instead.
- **Deterministic tokens**: equal values produce equal tokens, which enables
  grouping but reveals *which records share a value* (equality/frequency) — never
  the value itself. For a low-cardinality field this pattern can be informative.
- **Keyed gateway cannot aggregate** sealed numbers (by design).

## Files

- `scripts/deidentify.py` — **default**: identifiers→tokens, numbers kept raw
  (analyzable/averageable), plaintext map (no key); CSV/JSON and .txt/.md
- `scripts/reidentify.py` — restore identifiers from the plaintext map
- `scripts/deid_core.py` — keyless deterministic token (no key, no encryption)
- `scripts/protect.py` — keyed gateway: tokenize every value, build encrypted vault
- `scripts/reveal.py` — restore from the vault (key-gated)
- `scripts/tokenize_value.py` — token for a known value (keyed mode record lookup)
- `scripts/crypto_core.py` — stdlib-only key derivation, AEAD, keyed tokenization
- `scripts/pii_config.py` — sensitive fields + which are direct identifiers
- `scripts/recognizers.py` — value-shape detection, column inference, deny-list names
