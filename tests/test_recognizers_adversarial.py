#!/usr/bin/env python3
"""Adversarial recognizer tests: realistic PII format variations the first-pass
regexes miss, plus precision negatives that must NOT trigger.

These encode the desired behavior; failures here are the detection gaps to
close. Two design rules carried over:
  - fail-safe RRN: any RRN-SHAPED value is sealed (checksum only adjusts score);
  - gating validators (CARD/Luhn, BRN/checksum): reject on failure, because
    false positives there are common (a 16-digit run, an ISBN) and real values
    reliably pass.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_recognizers_adversarial.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import recognizers  # noqa: E402

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


def run():
    # ---- Phone format variations (all should be PHONE) ----
    phone_variants = {
        "dot-separated mobile": "연락 010.2535.4582",
        "space-separated mobile": "연락 010 2535 4582",
        "international +82": "call +82-10-2535-4582",
        "international +82 spaces": "call +82 10 2535 4582",
        "seoul landline": "사무실 02-1234-5678",
        "gyeonggi landline": "지점 031-123-4567",
        "voip 070": "대표번호 070-1234-5678",
    }
    for label, text in phone_variants.items():
        check(f"phone: {label}", "PHONE" in types(text), (text, recognizers.analyze(text)))

    # plain hyphen mobile still works (regression)
    check("phone: plain hyphen (regression)", "PHONE" in types("010-2535-4582"))

    # ---- RRN without the dash (13 consecutive digits, valid date part) ----
    check("rrn: no-dash 13 digits", "RRN" in types("주민번호 7703241809570 확인"),
          recognizers.analyze("주민번호 7703241809570 확인"))
    check("rrn: dashed still works (regression)", "RRN" in types("770324-1809570"))

    # ---- Business registration number (사업자등록번호), checksum-gated ----
    check("brn: valid checksum detected", "BRN" in types("사업자 220-81-62517"),
          recognizers.analyze("사업자 220-81-62517"))
    check("brn: another valid", "BRN" in types("등록번호 123-45-67891"))
    check("brn: invalid checksum rejected", "BRN" not in types("123-45-67890"))

    # ---- Precision negatives: none of these may produce ANY detection ----
    negatives = {
        "iso date": "마감 2018-02-19 까지",
        "semver": "버전 1.2.3 배포",
        "long semver": "릴리스 v10.4.2 적용",
        "time": "오후 12:34:56 시작",
        "price with commas": "총액 1,234,567원",
        "percent": "증가율 12.5% 기록",
        "isbn-13": "도서 978-89-12345-67-8 입고",
        "plain integer id": "주문 4582 처리",
    }
    for label, text in negatives.items():
        check(f"negative: {label}", types(text) == set(), (text, recognizers.analyze(text)))

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
