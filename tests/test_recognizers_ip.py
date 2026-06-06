#!/usr/bin/env python3
"""TDD tests for IPv4 address detection (Presidio default entity).

Incident/log memos routinely carry IP addresses; the incident-memo use case
makes this worth detecting. Octets are bounded 0-255 so 3-part versions and
out-of-range quads don't match.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_recognizers_ip.py
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
    check("private IP detected", "IP" in types("접속 192.168.0.1 에서"))
    check("public IP detected", "IP" in types("출처 8.8.8.8"))
    check("loopback detected", "IP" in types("127.0.0.1 로컬"))
    # 3-part version is not an IP.
    check("semver not IP", "IP" not in types("버전 1.2.3 배포"))
    # Out-of-range octet is not an IP.
    check("out-of-range quad not IP", "IP" not in types("코드 999.1.1.1 참고"))
    # Exact span.
    spans = [s for s in recognizers.analyze("접속 10.0.12.255 확인") if s.entity_type == "IP"]
    check("IP span exact", spans and "접속 10.0.12.255 확인"[spans[0].start:spans[0].end] == "10.0.12.255",
          spans)

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
