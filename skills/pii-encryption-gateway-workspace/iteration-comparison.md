# Benchmark comparison across iterations (1 → 5)

Same 4 LLM-driven evals (salary-notice, attendance-notices, dept-structure-report,
bonus-deposit), with-skill vs no-skill baseline, scored by `grade_eval.py`.
Iterations 1–4 ran before this session; **iteration-5 was run after all of this
session's work (PRs #1–#6)** to confirm the much-expanded skill still holds up on
the original tasks.

| Iter | When | With-skill pass | Baseline pass | With tokens | Baseline tokens | Token delta |
|------|------|-----------------|---------------|-------------|-----------------|-------------|
| 1 | pre-session | 100% ± 0% | 50% ± 50% | 48,983 | 38,679 | +10,304 |
| 2 | pre-session | 100% ± 0% | 62% ± 25% | 50,225 | 38,641 | +11,584 |
| 3 | pre-session | 100% ± 0% | 62% ± 25% | 41,507 | 54,840 | −13,334 |
| 4 | pre-session | 100% ± 0% | 62% ± 25% | 42,360 | 55,714 | −13,354 |
| **5** | **post-session** | **100% ± 0%** | **62% ± 23%** | **42,512** | **53,111** | **−10,599** |

Time (with / baseline, seconds): 1: 72.7/42.0 · 2: 69.8/37.6 · 3: 77.5/49.5 ·
4: 69.6/51.1 · **5: 74.6/44.5**.

## Reading

- **With-skill pass rate is rock-stable at 100% across all five iterations.**
  iteration-5 is the key result: every capability added this session
  (value-shape recognizers, column inference, document mode, deny-list names,
  expanded entities, unicode folding) left the original-task pass rate
  untouched — no regression from the added surface area.
- **With-skill token cost stayed flat (~42.5K), in line with iter-3/4** and
  *below* iter-1/2 (~49–50K). The skill got materially more capable without
  getting more token-hungry on these tasks; it still uses ~10.6K **fewer**
  tokens than the baseline, because it works on tokenized `protected.json`
  instead of reading the full 250-row raw CSV into context.
- **Baseline still leaks (62%).** The 38-point gap is entirely the draft-leakage
  assertions on salary/attendance/bonus: the no-skill arm reads raw PII into the
  model's working copy; the dept-report eval is the one task with no individual
  PII, so the baseline passes it (hence 62%, not 0%).

## Caveats (honest)

- iteration-5 used **2 runs/config** (iters 1–4 used 3) to bound cost; the
  `benchmark.md` "3 runs" line is a template artifact of the aggregator.
- Only the **4 original evals** were re-run, for apples-to-apples comparison.
  The 2 new evals added this session (incident-memo document mode,
  freetext-column-leak) are new coverage with no prior iteration to compare —
  they're validated separately in `tests/` and the deterministic leakage eval.
- LLM-driven runs via subagents on the same model; small N, so treat
  time/token figures as estimates, pass-rate as the reliable signal.
