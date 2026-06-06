#!/usr/bin/env python3
"""TDD tests for deny-list name detection (Presidio PatternRecognizer deny_list).

Names have no value-shape pattern, so the recognizers miss them in prose. But
in an HR context the names are not unknown — they sit in the roster the handler
already holds. find_names() tokenizes exactly those known names by exact
string match: zero false positives, no model, no dependency. Korean
agglutination is handled by substring match — "장지민" is sealed inside
"장지민이" while the trailing particle 이 stays.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_denylist_names.py
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


def slices(text, names):
    return [text[s.start:s.end] for s in recognizers.find_names(text, names)]


def run():
    # 1. A known name in prose is found, and ONLY the name (not the particle).
    out = slices("이번 건은 장지민이 처리합니다.", {"장지민"})
    check("known name found", out == ["장지민"], out)

    # 2. Every returned span is typed NAME.
    spans = recognizers.find_names("장지민 대리", {"장지민"})
    check("span typed NAME", all(s.entity_type == "NAME" for s in spans), spans)

    # 3. Longest match wins: with both '민준' and '김민준', '김민준' is one span.
    out = slices("담당자 김민준 확인", {"민준", "김민준"})
    check("longest name wins", out == ["김민준"], out)

    # 4. A name not in the deny-list is never flagged (zero false positives).
    check("unknown name not flagged", slices("정보를 정리한다", {"정수민"}) == [])
    check("common word not flagged", slices("최대 매출 강조", {"최민준"}) == [])

    # 5. Multiple distinct names in one text.
    out = slices("최민준 과장과 신다은 대리가 회의했다.", {"최민준", "신다은"})
    check("multiple names found", set(out) == {"최민준", "신다은"}, out)

    # 6. Empty deny-list -> nothing.
    check("empty deny-list", recognizers.find_names("최민준 과장", set()) == [])

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
