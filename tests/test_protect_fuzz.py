#!/usr/bin/env python3
"""Property-based fuzz test for the protect -> reveal invariants on documents.

Generates many random documents — valid PII of every detectable type, plus
roster names, interleaved with Korean filler and markdown — then asserts, for
each, two properties the gateway must always hold:

  P1 (no leak):     no raw PII value survives verbatim in the protected text.
  P2 (round-trip):  reveal(protect(doc)) reproduces the original document exactly.

Randomized but seeded, so failures are reproducible. This stresses span
overlap resolution, right-to-left replacement, deny-list/recognizer
interaction, and vault round-tripping in combinations the example-based tests
don't reach.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_protect_fuzz.py [--iterations N] [--seed S]
"""

import argparse
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import protect as protect_mod  # noqa: E402
import reveal as reveal_mod  # noqa: E402

KEY = "handler-hr-alice-key-001"
BANKS = ["국민", "신한", "우리", "하나", "농협"]
SURNAMES = list("김이박최정강조윤장임한오서신권황안송류전")
GIVEN = ["민준", "서연", "도윤", "예은", "하준", "수아", "지민", "현우", "다은", "준서"]
# Filler: digit-free Korean words + markup, so it can never be mistaken for PII.
FILLER = ["회의", "보고", "확인", "요망", "검토", "처리", "일정", "공유", "담당", "전달",
          "참고", "긴급", "대외비", "메모", "정리", "승인", "반려", "초안", "최종", "첨부",
          "\n", "\n## 항목\n", " - ", ", ", ". ", " / ", "(", ")", "—"]


def _luhn(num13):
    digits = [int(c) for c in num13][::-1]
    s = 0
    for i, d in enumerate(digits):
        d = d * 2 if i % 2 == 0 else d
        if d > 9:
            d -= 9
        s += d
    return num13 + str((10 - s % 10) % 10)


def _brn(rng):
    d = [rng.randint(0, 9) for _ in range(9)]
    w = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(a * b for a, b in zip(d, w)) + (d[8] * 5) // 10
    chk = (10 - total % 10) % 10
    s = "".join(map(str, d + [chk]))
    return f"{s[:3]}-{s[3:5]}-{s[5:]}"


def _gen_pii(rng):
    """Return (value, kind) where kind is 'name' (deny-list) or 'pattern'."""
    t = rng.choice(["phone", "rrn", "email", "account", "card", "brn", "ip", "name"])
    if t == "phone":
        sep = rng.choice(["-", ".", " ", ""])
        return f"010{sep}{rng.randint(1000,9999)}{sep}{rng.randint(1000,9999)}", "pattern"
    if t == "rrn":
        return f"{rng.randint(10,99):02d}{rng.randint(1,12):02d}{rng.randint(1,28):02d}-{rng.choice('1234')}{rng.randint(100000,999999)}", "pattern"
    if t == "email":
        return f"user{rng.randint(1,9999)}@corp{rng.randint(1,9)}.co.kr", "pattern"
    if t == "account":
        return f"{rng.choice(BANKS)} {rng.randint(100,999)}-{rng.randint(1000,9999)}-{rng.randint(100000,999999)}", "pattern"
    if t == "card":
        return _luhn("".join(str(rng.randint(0, 9)) for _ in range(15))), "pattern"
    if t == "brn":
        return _brn(rng), "pattern"
    if t == "ip":
        return ".".join(str(rng.randint(0, 255)) for _ in range(4)), "pattern"
    return rng.choice(SURNAMES) + rng.choice(GIVEN), "name"


def _build_doc(rng):
    pii_vals, names = [], set()
    parts = ["# 문서\n"]
    for _ in range(rng.randint(3, 12)):
        if rng.random() < 0.55:
            val, kind = _gen_pii(rng)
            pii_vals.append(val)
            if kind == "name":
                names.add(val)
            parts.append(val)
        else:
            parts.append(rng.choice(FILLER))
        parts.append(rng.choice([" ", "  ", "\n", ", "]))
    return "".join(parts), pii_vals, names


def run(iterations, seed):
    rng = random.Random(seed)
    leak_fail = roundtrip_fail = 0
    examples = []
    with tempfile.TemporaryDirectory() as d:
        for n in range(iterations):
            doc, pii_vals, names = _build_doc(rng)
            in_path = os.path.join(d, "in.md")
            prot = os.path.join(d, "prot.md")
            vault = os.path.join(d, "v.json")
            final = os.path.join(d, "final.md")
            with open(in_path, "w", encoding="utf-8") as f:
                f.write(doc)

            _so = sys.stdout
            sys.stdout = open(os.devnull, "w")
            protect_mod.protect(KEY, in_path, prot, vault, names=names)
            protected = open(prot, encoding="utf-8").read()
            reveal_mod.reveal(KEY, vault, prot, final)
            sys.stdout = _so
            restored = open(final, encoding="utf-8").read()

            leaked = [v for v in pii_vals if v in protected]
            if leaked:
                leak_fail += 1
                if len(examples) < 5:
                    examples.append(("LEAK", leaked[:3], repr(doc[:120])))
            if restored != doc:
                roundtrip_fail += 1
                if len(examples) < 5:
                    examples.append(("ROUNDTRIP", repr(doc[:80]), repr(restored[:80])))

    print(f"iterations={iterations} seed={seed}")
    print(f"  P1 no-leak   failures: {leak_fail}")
    print(f"  P2 round-trip failures: {roundtrip_fail}")
    for tag, a, b in examples:
        print(f"  {tag}: {a} :: {b}")
    ok = leak_fail == 0 and roundtrip_fail == 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--iterations", type=int, default=300)
    p.add_argument("--seed", type=int, default=20260606)
    a = p.parse_args()
    sys.exit(run(a.iterations, a.seed))
