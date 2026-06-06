# Trigger-accuracy optimization v2 (description)

## Method

The automated `skill-creator/scripts/run_loop.py` drives triggering via `claude -p`
subprocesses, which fail to authenticate in this environment ("Invalid API key").
As in the prior round, the same logic was reproduced with the authenticated
subagent harness: 3 independent classifier agents judged all 30 queries against
the skill's **name + description only** (the signal Claude uses to decide whether
to consult a skill), with the instruction that Claude consults a skill only for
non-trivial, in-scope tasks. Majority of 3 = the verdict. Strong proxy, not the
real CLI harness; treat scores as well-calibrated on this set, not provably
perfect.

Eval set: `trigger_eval_v2.json` — 30 queries, harder than the prior 20:
16 should-trigger (incl. **document-mode** cases: incident memo `.md`, email
draft, `.txt` meeting notes, free-text `비고` column, log file with email/IP,
extracted-PDF text) and 14 should-not-trigger near-misses (RRN-checksum
*explanation*, regex-writing, privacy-policy doc, anonymized survey, name-only
casual request, DB-encryption *design* advice, sentiment on no-PII reviews,
security-training PPT, …).

## Results (majority of 3 runs)

| | should-trigger (1–16) | should-not (17–30) | total |
|---|---|---|---|
| **current description** | 15/16 — missed **#14** (log file w/ email+IP) | 14/14 ✅ | 29/30 |
| **candidate v2** | **16/16** (#14 now unanimous) | 14/14 ✅ | **30/30** |

The only gap in the current description was #14: a log file carrying emails and
IPs, for an incident report — under-triggered (2/3 said no) because the
description named neither IP addresses nor logs/documents. v2 closes it with
zero regression on the 14 tricky negatives (unanimous across all 3 runs).

## Change applied

Broadened the description to (a) name free-text documents/logs/memos/emails as
trigger contexts and (b) list the full detected entity set (email, card,
business-registration number, IP) — aligning the description with capabilities
the skill actually gained (document mode, expanded recognizers), not
overfitting. Added an explicit precision guard ("Not for writing privacy
policies, explaining algorithms/checksums, generating regex/code, or
already-anonymized data") which held all near-miss negatives.

This is a proxy improvement on one 30-query set. If a future harness run (real
`claude -p`) or a larger set surfaces mis-triggers, revisit with those as the
signal.
