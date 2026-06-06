#!/usr/bin/env python3
"""TDD tests for the keyless de-identification token core.

This is the lightweight model: no handler key, no encryption. A direct
identifier is replaced by a deterministic content-hash token and the
original is kept in a PLAINTEXT map for restoration. The only guarantee is
"the LLM's working copy never contains the raw identifier" — the protection
is the discipline of not opening the map, exactly like the keyed model's
"never open the raw file" rule, minus the at-rest encryption.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_deid_core.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import deid_core  # noqa: E402

TOKEN_RE = re.compile(r"\[\[[A-Z_]+:[0-9a-f]{8}\]\]")

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
    t1 = deid_core.token("NAME", "최민준")
    t2 = deid_core.token("NAME", "최민준")
    # 1. Deterministic — same (type,value) -> same token (so grouping works).
    check("deterministic", t1 == t2, (t1, t2))
    # 2. Token format matches the shared reveal/reidentify regex.
    check("token format", TOKEN_RE.fullmatch(t1) is not None, t1)
    check("type embedded", t1.startswith("[[NAME:"), t1)
    # 3. Keyless — token() takes no key argument (different signature from crypto_core).
    import inspect
    params = list(inspect.signature(deid_core.token).parameters)
    check("no key parameter", params == ["field_type", "value"], params)
    # 4. Different value -> different token.
    check("distinct values", deid_core.token("NAME", "신다은") != t1)
    # 5. Same value, different type -> different token (no cross-type collision).
    check("type-scoped", deid_core.token("EMAIL", "최민준") != t1)
    # 6. No handler-key dependence: there is no PBKDF2/derive step to call.
    check("no derive_subkeys", not hasattr(deid_core, "derive_subkeys"))

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
