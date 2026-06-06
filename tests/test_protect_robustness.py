#!/usr/bin/env python3
"""Robustness tests: scale/performance and idempotency.

SCALE: a large document with thousands of PII spans must protect+reveal
correctly and in reasonable time (timing reported; correctness asserted, with a
generous wall-clock ceiling to stay non-flaky).

IDEMPOTENCY: protecting an already-protected document is a no-op — tokens must
not be re-tokenized (no recognizer pattern should match inside a [[TYPE:hash]]
token), so a second pass reproduces the same text and adds nothing to the vault.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_protect_robustness.py
"""

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import protect as protect_mod  # noqa: E402
import reveal as reveal_mod  # noqa: E402

KEY = "handler-hr-alice-key-001"
SCALE_CEILING_SECONDS = 30.0

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


def _quiet(fn, *a, **k):
    so = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        return fn(*a, **k)
    finally:
        sys.stdout = so


def test_scale():
    n = 3000
    vals = []
    parts = ["# 대용량 문서\n"]
    for i in range(n):
        v = f"010-{1000 + (i % 9000):04d}-{2000 + (i % 8000):04d}"
        vals.append(v)
        parts.append(f"- 항목 {i}: 연락처 {v}, 메일 user{i}@corp.co.kr 확인 요망\n")
    doc = "".join(parts)

    with tempfile.TemporaryDirectory() as d:
        ip, pp, vp, fp = (os.path.join(d, x) for x in ("in.md", "p.md", "v.json", "f.md"))
        with open(ip, "w", encoding="utf-8") as f:
            f.write(doc)
        t0 = time.time()
        _quiet(protect_mod.protect, KEY, ip, pp, vp)
        _quiet(reveal_mod.reveal, KEY, vp, pp, fp)
        elapsed = time.time() - t0

        protected = open(pp, encoding="utf-8").read()
        restored = open(fp, encoding="utf-8").read()
        sample_leaks = [v for v in vals[:200] if v in protected]
        print(f"  [scale] {n} items, {len(doc)} chars, protect+reveal {elapsed:.2f}s")
        check("scale: no leaks (sampled)", sample_leaks == [], sample_leaks[:3])
        check("scale: round-trip exact", restored == doc)
        check(f"scale: under {SCALE_CEILING_SECONDS:.0f}s", elapsed < SCALE_CEILING_SECONDS, elapsed)


def test_idempotent():
    doc = ("# 메모\n최민준 과장 연락 010-2535-4582, 메일 user1@corp.co.kr, "
           "계좌 신한 617-1434-688508, 사업자 220-81-62517, 서버 192.168.0.1\n")
    names = {"최민준"}
    with tempfile.TemporaryDirectory() as d:
        ip, p1, v1, p2, v2 = (os.path.join(d, x) for x in
                              ("in.md", "p1.md", "v1.json", "p2.md", "v2.json"))
        with open(ip, "w", encoding="utf-8") as f:
            f.write(doc)
        _quiet(protect_mod.protect, KEY, ip, p1, v1, names=names)
        once = open(p1, encoding="utf-8").read()
        # Protect the already-protected output again.
        _quiet(protect_mod.protect, KEY, p1, p2, v2, names=names)
        twice = open(p2, encoding="utf-8").read()
        vault2 = json.load(open(v2, encoding="utf-8"))

        check("idempotent: second pass unchanged", twice == once, (once[:80], twice[:80]))
        check("idempotent: nothing new tokenized", vault2.get("entry_count", -1) == 0,
              vault2.get("entry_count"))


def run():
    test_scale()
    test_idempotent()
    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
