#!/usr/bin/env python3
"""TDD tests for free-text document mode: protect.py on a .txt/.md file.

The gateway started life on structured rosters (CSV/JSON). A handler often
needs the same protection for an unstructured document — a memo, an email
draft, an incident report — before showing it to a model. In document mode
protect.py runs the value-shape recognizers over the whole text, tokenizes the
PII spans in place, and leaves the prose intact; reveal.py restores it.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_protect_document.py
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


DOC = """# 인사 메모

최민준 과장 건으로 공유드립니다. 본인 확인이 필요하면 주민번호
770324-1809570 및 등록 연락처 010-2535-4582 로 대조해 주세요.
회신은 user0001@company.co.kr 로 부탁드리며, 정산 계좌는
신한 617-1434-688508 입니다.

부서: 영업팀 / 직급: 과장 — 이 두 줄은 민감정보가 아닙니다.
"""

RAW_PII = ["770324-1809570", "010-2535-4582", "user0001@company.co.kr",
           "신한 617-1434-688508"]


def run():
    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "memo.md")
        prot = os.path.join(d, "protected.md")
        vault = os.path.join(d, "vault.json")
        with open(in_path, "w", encoding="utf-8") as f:
            f.write(DOC)

        protect_mod.protect(KEY, in_path, prot, vault)
        protected = open(prot, encoding="utf-8").read()

        # 1. Output is text (not JSON) and carries tokens.
        check("protected output has tokens", TOKEN_RE.search(protected) is not None)
        # 2. No raw PII survives in the protected document.
        for v in RAW_PII:
            check(f"raw PII sealed: {v[:14]}", v not in protected)
        # 3. Each PII type produced a token.
        for t in ("[[RRN:", "[[PHONE:", "[[EMAIL:", "[[ACCOUNT:"):
            check(f"{t}…]] present", t in protected, protected)
        # 4. Prose and non-PII structure are preserved.
        check("heading kept", "# 인사 메모" in protected)
        check("name in prose kept (no NER)", "최민준 과장" in protected)
        check("non-sensitive line kept", "이 두 줄은 민감정보가 아닙니다" in protected)
        check("department text kept", "부서: 영업팀" in protected)

        # 5. Vault was written and is non-empty.
        vobj = json.load(open(vault, encoding="utf-8"))
        check("vault has entries", vobj.get("entry_count", 0) >= 4, vobj.get("entry_count"))

        # 6. Round-trip: reveal restores the document verbatim.
        final = os.path.join(d, "final.md")
        reveal_mod.reveal(KEY, vault, prot, final)
        restored = open(final, encoding="utf-8").read()
        check("reveal reproduces the original document exactly", restored == DOC,
              "restored != original")

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
