#!/usr/bin/env python3
"""TDD tests for full-width / unicode digit & ASCII folding.

Korean documents pasted from spreadsheets or some IMEs carry full-width digits
(０１０), full-width @ ／ . / - etc. The ASCII regexes miss these, leaking PII.
A length-preserving fold to ASCII is applied for *detection* only, so span
offsets still line up with the original text and the original (full-width)
value is what gets tokenized and restored verbatim.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_recognizers_unicode.py
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import recognizers  # noqa: E402
import protect as protect_mod  # noqa: E402
import reveal as reveal_mod  # noqa: E402

KEY = "handler-hr-alice-key-001"

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
    # Full-width digit forms of each patterned type.
    fw_phone = "연락 ０１０－２５３５－４５８２"        # full-width digits + full-width hyphen
    fw_rrn = "주민 ７７０３２４-１８０９５７０"
    fw_email = "메일 ｕｓｅｒ＠ｃｏｒｐ．ｃｏ．ｋｒ"
    check("full-width phone detected", "PHONE" in types(fw_phone), recognizers.analyze(fw_phone))
    check("full-width RRN detected", "RRN" in types(fw_rrn), recognizers.analyze(fw_rrn))
    check("full-width email detected", "EMAIL" in types(fw_email), recognizers.analyze(fw_email))

    # Span offsets must still index the ORIGINAL (full-width) text correctly.
    spans = [s for s in recognizers.analyze(fw_phone) if s.entity_type == "PHONE"]
    check("full-width span slices original", spans and fw_phone[spans[0].start:spans[0].end]
          == "０１０－２５３５－４５８２", spans and fw_phone[spans[0].start:spans[0].end])

    # Precision: a full-width DATE must not become PII.
    check("full-width date not PII", types("마감 ２０１８-０２-１９ 까지") == set(),
          recognizers.analyze("마감 ２０１８-０２-１９ 까지"))

    # End-to-end: protect a document with full-width PII, then reveal it back
    # to the exact original (full-width preserved).
    doc = f"# 메모\n{fw_phone}\n{fw_email}\n부서 영업팀\n"
    with tempfile.TemporaryDirectory() as d:
        ip, pp, vp, fp = (os.path.join(d, n) for n in ("in.md", "p.md", "v.json", "f.md"))
        with open(ip, "w", encoding="utf-8") as f:
            f.write(doc)
        protect_mod.protect(KEY, ip, pp, vp)
        protected = open(pp, encoding="utf-8").read()
        check("full-width phone sealed", "０１０－２５３５－４５８２" not in protected, protected)
        check("full-width email sealed", "ｕｓｅｒ＠ｃｏｒｐ．ｃｏ．ｋｒ" not in protected)
        check("token present", "[[" in protected)
        reveal_mod.reveal(KEY, vp, pp, fp)
        check("round-trip restores full-width exactly", open(fp, encoding="utf-8").read() == doc)

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
