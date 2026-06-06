#!/usr/bin/env python3
"""TDD tests for deny-list name protection wired into protect.py.

Document mode (and any free-text pass) tokenizes known names supplied by the
handler — typically the roster's 이름 column — so the in-prose names that the
value-shape recognizers cannot detect are sealed too, with no dependency.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_protect_names.py
"""

import csv
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
DATASET = os.path.join(ROOT, "data", "employees.csv")

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
    # _load_names pulls the 이름 column out of the roster as the deny-list.
    names = protect_mod._load_names(DATASET)
    check("_load_names reads roster names", "최민준" in names and len(names) >= 100,
          len(names))

    # A real roster name + an off-list phone in prose. Document mode should seal
    # BOTH: the phone via recognizers, the name via the deny-list.
    doc = ("인사 메모: 최민준 과장 건은 신다은 대리가 인계합니다. "
           "연락은 010-2535-4582 로 주세요. (외부 인물 홍길동은 명부에 없음)")
    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "memo.md")
        prot = os.path.join(d, "protected.md")
        vault = os.path.join(d, "vault.json")
        with open(in_path, "w", encoding="utf-8") as f:
            f.write(doc)

        protect_mod.protect(KEY, in_path, prot, vault, names=names)
        protected = open(prot, encoding="utf-8").read()

        check("roster name 1 sealed", "최민준" not in protected, protected)
        check("roster name 2 sealed", "신다은" not in protected, protected)
        check("NAME token present", "[[NAME:" in protected, protected)
        check("embedded phone still sealed", "010-2535-4582" not in protected)
        # A name NOT in the roster is out of deny-list scope (Tier 1 territory) —
        # documented limit, asserted so the boundary is explicit.
        check("off-roster name left as-is (documented limit)", "홍길동" in protected)
        # Non-name prose preserved.
        check("prose preserved", "인계합니다" in protected and "인사 메모" in protected)

        # Round-trip restores names and phone verbatim.
        final = os.path.join(d, "final.md")
        reveal_mod.reveal(KEY, vault, prot, final)
        restored = open(final, encoding="utf-8").read()
        check("reveal restores document exactly", restored == doc, "restored != original")

    # Back-compat: protect() with no names still works (structured path).
    with tempfile.TemporaryDirectory() as d:
        prot = os.path.join(d, "p.json")
        vault = os.path.join(d, "v.json")
        protect_mod.protect(KEY, DATASET, prot, vault)
        rows = json.load(open(prot, encoding="utf-8"))
        check("structured path unchanged without names", len(rows) == 250, len(rows))

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
