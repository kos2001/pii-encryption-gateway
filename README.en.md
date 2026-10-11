# pii-encryption-gateway

<p><a href="README.md" lang="ko">한국어</a> · <strong lang="en">English</strong></p>

A Claude Code skill for processing sensitive personal data (employee IDs, salaries,
attendance, Korean resident registration numbers, bank accounts, phone numbers,
emails, cards, business registration numbers, IPs, ...) **without exposing it to the
LLM**, plus the synthetic data and evaluation harness that verify it.
(Former repository name: `private_protection`)

## Quick start

All you need is Python 3.10+ (standard library only; no external dependencies, no LLM calls).

```sh
# 1) Generate synthetic HR data (fixed seed -> identical to the committed data/)
python3 data/generate_data.py --count 250 --freetext

# 2) Security-invariant stress test (14 checks, all 250 employees + adversarial edges)
python3 tests/stress_test.py

# 3) De-identify -> let the LLM work -> re-identify (default mode)
python3 skills/pii-encryption-gateway/scripts/deidentify.py \
  --in data/employees.csv --out deidentified.json --map map.json \
  --names-from data/employees.csv
python3 skills/pii-encryption-gateway/scripts/reidentify.py \
  --map map.json --in draft.json --out final.json
```

The remaining deterministic tests are run file by file (for example
`python3 tests/test_recognizers.py`, `python3 tests/deid_eval.py`). To use it as a
skill, copy `skills/pii-encryption-gateway/` under `~/.claude/skills/`.

## Layout

```
skills/pii-encryption-gateway/   # the skill itself
  SKILL.md                       #   operating discipline (never read the original file)
  scripts/
    deidentify.py                #   [default] identifiers -> tokens, numbers kept raw (aggregatable), plaintext map (no key)
    reidentify.py                #   restore identifiers from the plaintext map
    deid_core.py                 #   keyless deterministic tokens (no encryption, no key)
    protect.py                   #   [secondary] keyed gateway: tokenize every value + encrypted vault
    reveal.py                    #   restore vault -> original with the handler's key (wrong key fails)
    tokenize_value.py            #   compute the token of a known value (e.g. employee ID) — keyed-mode record lookup
    crypto_core.py               #   KDF + AEAD + key-based tokens, standard library only
    pii_config.py                #   sensitive-field and direct-identifier definitions
    recognizers.py               #   value-shape PII detection, column inference, deny-list names (free text / documents)
  evals/evals.json               #   6 behavioral eval cases (incl. document mode and free-text leakage)
data/
  generate_data.py               # Korean-style synthetic HR data generator (fixed seed; --freetext variant)
  employees.csv / .json          # generated synthetic data (not real people)
  employees_freetext.csv         # PII embedded in a free-form "notes" column (for leakage evals)
  incident_memo.md               # synthetic memo for document-mode evals
tests/                           # deterministic test suite (no LLM needed) + grader
  stress_test.py                 #   14 security invariants (all 250 employees + adversarial edges)
  test_recognizers*.py           #   value-shape detection: basic / adversarial formats / IP / unicode
  test_protect_*.py              #   protect integration: free text / column inference / documents / names / fuzz / scale
  test_column_inference.py       #   column classification by value sampling
  test_denylist_names.py         #   exact-match deny-list names
  test_deid*.py                  #   keyless de-id: core / integration (identifier tokens, raw numbers, averages)
  deid_eval.py                   #   3-way check: leakage vs. computing an average (baseline / keyed / de-id)
  leakage_eval.py                #   quantified leakage before/after (column-only vs. +recognizer)
  grade_eval.py                  #   automatic grader for the behavioral evals
skills/pii-encryption-gateway-workspace/   # iteration-1..5 eval results + comparison
```

## How it works

**The default is keyless de-identification.** `deidentify.py` replaces only the
**direct identifiers** (name, resident registration number, employee ID, account,
phone, email, ...) with deterministic tokens (`[[NAME:3f9a2c1d]]`) and **leaves numeric
attributes (salary, attendance) untouched.** The LLM therefore never knows *whose*
value it is looking at, yet it can **compute aggregates and statistics directly**
(averages, sums, distributions). The original-to-token correspondence is stored in a
**plaintext map** (`map.json`), and `reidentify.py` restores the identifiers at the end
of the task. No keys, no encryption.

When **at-rest encryption and key-based access control** are also required, use the
stronger **keyed gateway** (`protect.py` / `reveal.py`). It tokenizes **every value,
numbers included**, stores them in a vault encrypted with the handler's key, and only
an authorized key can restore them (a wrong key fails). The trade-off is that the
numbers are sealed, so **aggregation is impossible** — statistics must be computed by
a separate script against the original.

Tokens are deterministic in both modes: the same value always maps to the same token,
so the model can reason about same-person / same-group relationships without ever
seeing the actual identifier values.

### What is detected, and how (the Microsoft Presidio architecture, ported to stdlib)

Sensitive values are caught through **four paths**, so they are protected wherever they appear:

1. **Column name** — alias matching in `pii_config.py` (structured CSV/JSON columns).
2. **Column shape** — columns whose names do not match are sampled; if the values form a
   single PII entity, the whole column is classified. Because it generalizes from the
   majority, individual off-format cells are sealed too.
3. **Value shape** — span-level detection of PII embedded in sentences: resident
   registration numbers (with or without dashes), phone numbers (mobile, landline, +82,
   with `-` / `.` / space separators), emails, bank accounts, cards, business
   registration numbers, IPv4. Full-width digits (`０１０...`) are recognized through a
   length-preserving fold.
4. **Deny-list names** — names have no pattern, so names from a roster the handler
   already holds are sealed by exact match (`--names-from`). Third-party names outside
   the roster are not detected (an honest limitation).

Validators follow the Presidio approach: **RRN is fail-safe** (the checksum only adds
confidence; a format match alone is sealed, because real and synthetic dumps often fail
the checksum), while **cards (Luhn) and business registration numbers (checksum) are
gating** (a failing checksum excludes the match — false positives such as ISBNs are
common and real values pass). Besides structured CSV, `.txt` / `.md` **documents**
(memos, email drafts, incident reports) are handled the same way.

## Usage examples

Default — de-identification (aggregation and statistics possible):

```sh
# 1) De-identify (identifiers -> tokens, numbers kept raw, plaintext map)
python3 skills/pii-encryption-gateway/scripts/deidentify.py \
  --in data/employees.csv --out deidentified.json --map map.json \
  --names-from data/employees.csv      # .md/.txt documents are supported the same way

# 2) The LLM works on deidentified.json — e.g. computes average salary per department directly
#    (names / RRNs / accounts are tokens, salary / attendance are raw)

# 3) If the output contains identifier tokens, restore them (skip for pure aggregate reports)
python3 skills/pii-encryption-gateway/scripts/reidentify.py \
  --map map.json --in draft.json --out final.json
```

Secondary — keyed gateway (when per-person work plus at-rest encryption is required):

```sh
python3 skills/pii-encryption-gateway/scripts/protect.py \
  --key "handler-hr-alice-key-001" --in data/employees.csv \
  --out protected.json --vault vault.json
# ... work with the tokens ...
python3 skills/pii-encryption-gateway/scripts/reveal.py \
  --key "handler-hr-alice-key-001" --vault vault.json --in draft.txt --out final.txt
```

## Limitations (honest trade-offs)

- **De-identification (the default mode) exposes the numeric values themselves**,
  de-linked from names. This is what makes aggregation possible, but if even de-linked
  numbers must not reach the model, aggregate against the original with a script and
  pass only the results. **The keyed gateway seals numbers too**, so it cannot aggregate.
- The de-identification map (`map.json`) is **plaintext** (no key, no encryption) and is
  as sensitive as the original — store it like the original file. The keyed gateway's
  vault, by contrast, is encrypted.
- Tokens are **deterministic**: the same value always yields the same token. Grouping
  works, but the protected data alone reveals *which records share a value* (identity
  and frequency).
- **Names in prose** have no value shape, so recognizers cannot catch them. The
  roster-based deny-list fills the gap, but names outside the roster would need a
  separate NER (optional, not implemented).
  Rationale and alternatives: `claudedocs/ner-integration-review.md` (Korean).

## Evaluation results

**(1) Behavioral evals** — with-skill vs. baseline (no skill) through the skill-creator eval loop.

| | Data | with-skill | baseline | Time Δ | Token Δ |
|---|---|---|---|---|---|
| iteration-1 (3 evals) | 40 employees | 100% | 50% | — | — |
| iteration-2 (4 evals) | 40 employees | 100% | 62.5% | +32s | +11.5k |
| iteration-3 (4 evals) | 250 employees | 100% | 62.5% | +28s | **−13.3k** |
| iteration-4 (4 evals, employee ID also sensitive) | 250 employees | 100% | 62.5% | +18s | **−13.4k** |
| iteration-5 (4 evals, after feature expansion) | 250 employees | 100% | 62.5% | +30s | **−10.6k** |

On tasks that need per-person sensitive values (salary notices, attendance notices,
bonus deposits) the baseline exposed real names, salaries and accounts to the model
context every time, while the gateway kept leakage at zero. Tasks that never needed PII
in the first place (a per-department aggregate report) passed on both sides
(non-discriminating). **At scale (250 employees) the gateway is not only safer but also
uses fewer tokens.** iteration-5 confirms no regression in pass rate or tokens after
this expansion (multi-layer detection, document mode, deny-list, extended entities,
unicode). Cross-comparison: `skills/pii-encryption-gateway-workspace/iteration-comparison.md` (Korean).

**(2) Deterministic test suite** — `tests/` (no LLM needed, 18 files):

- `stress_test.py` — security invariants 14/14 (all 250 employees + adversarial edges:
  duplicates, empty values, unicode, emoji, newlines, token look-alikes, cross-handler
  keys). protect of 250 rows in 0.16s.
- Value-shape detection — basic (15), adversarial formats (21), IP (6), full-width unicode (9).
- protect integration — free text (13), column inference (7), documents (15), names (9).
- **Keyless de-id** — core (7), integration (20: identifier tokens, raw numbers, direct
  average computation, map restoration).
- **Fuzz (property-based)** — 3,200 random documents (4 seeds): 0 leaks, exact round trip.
- **Scale and idempotence** — 175 KB / 3,000 records protect+reveal in ~1.3s; re-protect is a no-op.
- `leakage_eval.py` — PII recall in free text and unnamed columns **0% → 100%**,
  off-format cells **80% → 100%** (column-only vs. +recognizer/column inference).
- `deid_eval.py` — 3-way check on an aggregation task: **baseline** (average OK, 1,500
  identifiers leaked), **keyed gateway** (0 leaks, no average), **keyless de-id**
  (0 leaks + correct average = goal achieved).

**(3) Triggering accuracy** — the skill's invocation description evaluated on a 30-query
set (document-mode positives + tricky near-misses), majority vote of 3 independent
classifiers **30/30** (proxy). Record: `trigger_eval_v2_results.md` in the workspace (Korean).

Reproduce: `python3 data/generate_data.py --count 250 --freetext` → `python3 tests/stress_test.py`.
Behavioral evals are graded by `tests/grade_eval.py`. The eval viewer requires Python 3.10+.

## License

[MIT](LICENSE) — Copyright (c) 2026 kos2001
