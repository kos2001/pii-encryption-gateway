#!/usr/bin/env python3
"""TDD test: protect.py uses column inference to seal cells the per-value
recognizer misses.

The scenario the per-cell pass (priority 1) leaks: a clearly-PII column whose
name is not in pii_config aliases AND which contains a cell that doesn't match
the recognizer's pattern (a malformed phone). Column inference classifies the
whole column from its majority, so even the malformed cell is tokenized.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_protect_inference.py
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
    # "비상연락처코드" is not in pii_config aliases. The column is plainly phones,
    # except one malformed cell that the PHONE regex cannot match on its own.
    malformed = "010-12-34567"
    rows = [{"부서": "영업팀", "비상연락처코드": f"010-{1000+i}-{2000+i}"} for i in range(20)]
    rows.append({"부서": "인사팀", "비상연락처코드": malformed})

    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "in.json")
        prot = os.path.join(d, "protected.json")
        vault = os.path.join(d, "vault.json")
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)

        protect_mod.protect(KEY, in_path, prot, vault)
        protected = json.load(open(prot, encoding="utf-8"))
        blob = json.dumps(protected, ensure_ascii=False)

        # 1. Every valid phone is sealed.
        check("valid phones sealed", "010-1000-2000" not in blob and "010-1019-2019" not in blob)
        # 2. The malformed cell — which the per-cell recognizer can't match — is
        #    sealed too, because the column was inferred PHONE from the majority.
        check("malformed cell sealed by column inference", malformed not in blob, blob[:200])
        # 3. The inferred column's cells are whole-cell PHONE tokens.
        toks = [r["비상연락처코드"] for r in protected]
        check("inferred column cells are whole-cell tokens",
              all(TOKEN_RE.fullmatch(t) for t in toks), toks[:3])
        check("inferred tokens are PHONE type", all(t.startswith("[[PHONE:") for t in toks), toks[:3])
        # 4. Non-PII structural column untouched.
        check("dept untouched", all(r["부서"] in ("영업팀", "인사팀") for r in protected))

        # 5. Round-trip restores even the malformed value verbatim.
        out_in = os.path.join(d, "draft.txt")
        final = os.path.join(d, "final.txt")
        with open(out_in, "w", encoding="utf-8") as f:
            f.write("\n".join(toks))
        reveal_mod.reveal(KEY, vault, out_in, final)
        restored = open(final, encoding="utf-8").read()
        check("reveal restores malformed value", malformed in restored)
        check("reveal restores a valid phone", "010-1000-2000" in restored)

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
