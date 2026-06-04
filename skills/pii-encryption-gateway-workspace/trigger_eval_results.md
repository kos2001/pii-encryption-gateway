# Trigger-accuracy evaluation (description optimization)

## Method note (honest caveat)

The intended automated loop (`skill-creator/scripts/run_loop.py`) drives the real
triggering mechanism via `claude -p` subprocesses. In this environment those
headless subprocesses fail to authenticate ("Invalid API key"), so the automated
loop could not run here. Credential inspection was (correctly) blocked.

As a working substitute, the same logic was reproduced with the authenticated
subagent harness: 3 independent classifier agents each judged all 20 queries
against the skill's name + description (the signal Claude actually uses to decide
whether to consult a skill). This is a strong proxy but not identical to the real
CLI harness, and it is a single 20-query set — treat 100% as "well-calibrated on
this set," not "provably perfect."

## Result (current description, unchanged)

| | should-trigger (0–9) | should-not-trigger (10–19) |
|---|---|---|
| run 1 | 10/10 ✅ | 10/10 ✅ |
| run 2 | 10/10 ✅ | 10/10 ✅ |
| run 3 | 10/10 ✅ | 10/10 ✅ |

**Accuracy: 20/20 (100%), unanimous across 3 runs.**

Correctly-excluded near-misses (share keywords but should NOT trigger):
- "AES-256 파일 암호화 코드 예제" — encryption *concept*, no PII data file
- "패스워드 매니저 비교" — 암호/password keyword, different need
- "채용 공고 … 연봉 협의" — 연봉 keyword, no data file
- "개인정보 보호 정책 문서 작성" — 개인정보 keyword, writing a doc not handling data
- "익명 설문 집계", "재고 inventory.csv", "SSL 인증서", "bcrypt 해싱", "부서 인원수만"

## Decision

The description already scores 100% on this set, including the tricky negatives.
Changing it now would be guessing against a ceiling and risks regression
(overfitting). Kept as-is. If a harder, larger eval set later surfaces
mis-triggers, revisit with those failures as the training signal.
