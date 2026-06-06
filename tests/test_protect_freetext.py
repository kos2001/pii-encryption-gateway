#!/usr/bin/env python3
"""TDD tests for protect.py's value-level recognizer pass.

These cover exactly the inputs the column-name classifier misses:
  - PII sitting in a mis-named column (not in pii_config's alias list)
  - PII embedded inside a free-text sentence
The recognizer second pass must tokenize those in place, leave non-PII
structure untouched, and stay round-trippable through reveal.py.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_protect_freetext.py
"""

import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import protect as protect_mod  # noqa: E402
import reveal as reveal_mod  # noqa: E402

TOKEN_RE = re.compile(r"\[\[[A-Z_]+:[0-9a-f]{8}\]\]")
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


def run():
    # A dataset whose PII hides where the column-name classifier can't see it:
    # "비고" (remarks) and "메모" (note) are NOT in pii_config aliases.
    records = [
        {
            "사번": "E0001",
            "부서": "영업팀",
            "비고": "본인 주민번호 770324-1809570 확인 요망",
            "메모": "연락은 010-2535-4582 또는 user0001@company.co.kr 로",
        }
    ]

    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "in.json")
        prot = os.path.join(d, "protected.json")
        vault = os.path.join(d, "vault.json")
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)

        protect_mod.protect(KEY, in_path, prot, vault)
        protected = json.load(open(prot, encoding="utf-8"))[0]
        blob = json.dumps(protected, ensure_ascii=False)

        # 1. The mis-named "비고" column's RRN is gone from the protected payload.
        check("RRN in mis-named column not exposed", "770324-1809570" not in blob)
        # 2. Embedded phone + email gone too.
        check("embedded phone not exposed", "010-2535-4582" not in blob)
        check("embedded email not exposed", "user0001@company.co.kr" not in blob)

        # 3. Tokens actually appear (PII was replaced, not just dropped).
        check("RRN token present", "[[RRN:" in protected["비고"], protected["비고"])
        check("PHONE token present", "[[PHONE:" in protected["메모"], protected["메모"])
        check("EMAIL token present", "[[EMAIL:" in protected["메모"], protected["메모"])

        # 4. Surrounding free text is preserved (only PII spans replaced).
        check("free-text context kept", "확인 요망" in protected["비고"], protected["비고"])
        check("non-PII structural column untouched", protected["부서"] == "영업팀")
        # 사번 is sensitive by column name -> tokenized by the existing pass.
        check("사번 still tokenized by column pass",
              TOKEN_RE.fullmatch(protected["사번"]) is not None, protected["사번"])

        # 5. Round-trip: reveal restores every embedded value verbatim.
        draft = os.path.join(d, "draft.txt")
        final = os.path.join(d, "final.txt")
        with open(draft, "w", encoding="utf-8") as f:
            f.write(protected["비고"] + "\n" + protected["메모"])
        reveal_mod.reveal(KEY, vault, draft, final)
        restored = open(final, encoding="utf-8").read()
        check("reveal restores RRN", "770324-1809570" in restored)
        check("reveal restores phone", "010-2535-4582" in restored)
        check("reveal restores email", "user0001@company.co.kr" in restored)
        check("reveal keeps context", "확인 요망" in restored, restored)

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
