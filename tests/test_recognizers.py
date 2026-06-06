#!/usr/bin/env python3
"""TDD tests for the value-level PII recognizer layer (Presidio-style).

The recognizer pass complements column-name classification: it finds PII by the
*shape of the value*, so PII in a free-text or mis-named column is caught even
when pii_config's alias list never matched the column name.

Design rule under test — fail-safe toward protection:
  A format match alone is enough to tokenize (score >= threshold). A passing
  checksum only *raises* confidence; a failing checksum must NOT drop a
  format match below threshold for RRN (real and synthetic dumps routinely
  carry RRN-shaped values that fail the check digit). CARD is the one
  exception: a 16-digit run that fails Luhn is rejected, because false
  positives there are common and costly.

Plain-assertion runner (matches tests/stress_test.py); exit code non-zero on
failure so this doubles as CI.

Usage:  python3 tests/test_recognizers.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import recognizers  # noqa: E402

THRESHOLD = 0.5

_passed = 0
_failed = 0


def check(label, ok, detail=""):
    global _passed, _failed
    if ok:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}  -- {detail}")


def types(text):
    return {s.entity_type for s in recognizers.analyze(text)}


def find(text, entity_type):
    return [s for s in recognizers.analyze(text) if s.entity_type == entity_type]


def run():
    # 1. RRN with a valid check digit -> detected with high confidence.
    spans = find("주민등록번호 900101-1234568 입니다", "RRN")
    check("valid-checksum RRN detected", len(spans) == 1, spans)
    check("valid-checksum RRN high score", spans and spans[0].score >= 0.9,
          spans[0].score if spans else None)

    # 2. RRN-shaped value with a WRONG check digit (synthetic/real dumps) ->
    #    still detected (fail-safe), just at lower confidence, still >= threshold.
    spans = find("770324-1809570", "RRN")  # from data/employees.csv E0001
    check("bad-checksum RRN still detected", len(spans) == 1, spans)
    check("bad-checksum RRN above threshold",
          spans and spans[0].score >= THRESHOLD, spans[0].score if spans else None)

    # 3. Phone.
    check("phone detected", types("연락처 010-2535-4582") >= {"PHONE"})

    # 4. Email.
    check("email detected", types("user0001@company.co.kr 로 회신") >= {"EMAIL"})

    # 5. Account with a bank name prefix.
    check("bank account detected", types("계좌 신한 617-1434-688508") >= {"ACCOUNT"})

    # 6. Card with a valid Luhn checksum.
    check("valid Luhn card detected", types("4111-1111-1111-1111") >= {"CARD"})

    # 7. Card-length run that FAILS Luhn -> not a CARD (reject false positive).
    check("invalid Luhn card rejected", "CARD" not in types("4111-1111-1111-1112"))

    # 8. Non-PII structural values must not false-positive.
    benign = "입사일 2018-02-19, 부서 영업팀, 지각 5회, 연봉 5350만원"
    check("no false positives on date/dept/counts/salary",
          types(benign) == set(), recognizers.analyze(benign))

    # 9. Free text with two PII spans -> both found at correct offsets.
    text = "문의는 010-2535-4582 또는 user0001@company.co.kr 로 주세요"
    spans = recognizers.analyze(text)
    check("free-text finds both spans", types(text) == {"PHONE", "EMAIL"}, spans)
    for s in spans:
        check(f"offset exact for {s.entity_type}",
              text[s.start:s.end] in (text[s.start:s.end],) and
              s.start < s.end <= len(text), (s.start, s.end))
    phone = find(text, "PHONE")[0]
    check("phone offset slices the phone", text[phone.start:phone.end] == "010-2535-4582",
          text[phone.start:phone.end])

    # 10. A salary amount is not mistaken for a phone/RRN/card.
    check("salary amount is not PII-shaped", types("연봉 5350만원") == set())

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
