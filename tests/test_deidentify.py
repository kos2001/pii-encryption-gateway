#!/usr/bin/env python3
"""TDD tests for keyless de-identification (identifiers tokenized, numbers raw).

Goal of this mode: the LLM's working copy must not contain raw direct
identifiers (name, RRN, account, phone, email, employee id), but numeric
attributes (salary, attendance) stay RAW so the model can compute aggregates
like averages directly. No key, plaintext map, reversible.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_deidentify.py
"""

import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import deidentify as deid  # noqa: E402
import reidentify as reid  # noqa: E402

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


ROWS = [
    {"사번": "E0001", "이름": "최민준", "주민등록번호": "770324-1809570", "부서": "영업팀",
     "직급": "과장", "연봉": "5000만원", "지각횟수": 4, "전화번호": "010-1111-2222",
     "이메일": "a@corp.co.kr", "계좌번호": "신한 111-1111-111111"},
    {"사번": "E0002", "이름": "신다은", "주민등록번호": "880712-2345671", "부서": "영업팀",
     "직급": "대리", "연봉": "3000만원", "지각횟수": 2, "전화번호": "010-3333-4444",
     "이메일": "b@corp.co.kr", "계좌번호": "국민 222-2222-222222"},
    {"사번": "E0003", "이름": "최민준", "주민등록번호": "900101-1234568", "부서": "개발팀",
     "직급": "부장", "연봉": "7000만원", "지각횟수": 0, "전화번호": "010-5555-6666",
     "이메일": "c@corp.co.kr", "계좌번호": "우리 333-3333-333333"},
]
IDENTIFIER_COLS = ["사번", "이름", "주민등록번호", "전화번호", "이메일", "계좌번호"]
RAW_COLS = ["부서", "직급", "연봉", "지각횟수"]


def run():
    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "in.json")
        out_path = os.path.join(d, "deidentified.json")
        map_path = os.path.join(d, "map.json")
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(ROWS, f, ensure_ascii=False)

        # No key argument — keyless.
        deid.deidentify(in_path, out_path, map_path)
        out = json.load(open(out_path, encoding="utf-8"))
        mp = json.load(open(map_path, encoding="utf-8"))

        # 1. Identifiers are tokenized.
        for col in IDENTIFIER_COLS:
            check(f"identifier tokenized: {col}",
                  all(TOKEN_RE.fullmatch(str(r[col])) for r in out), [r[col] for r in out][:2])
        # 2. Numeric / non-sensitive columns stay RAW (unchanged).
        for col in RAW_COLS:
            check(f"raw kept: {col}", [r[col] for r in out] == [r[col] for r in ROWS],
                  [r[col] for r in out])
        # 3. No raw identifier value survives in the de-identified file.
        blob = json.dumps(out, ensure_ascii=False)
        for v in ["최민준", "신다은", "770324-1809570", "신한 111-1111-111111", "a@corp.co.kr"]:
            check(f"no raw id leaked: {v[:10]}", v not in blob)
        # 4. The map is PLAINTEXT token->value (real values readable, no encryption blob).
        check("map is plaintext", "최민준" in json.dumps(mp, ensure_ascii=False))
        check("map has no key/vault wrapper", "entries" not in mp and "version" not in mp)
        # 5. Determinism: same name in rows 0 and 2 -> same token (grouping works).
        check("deterministic grouping", out[0]["이름"] == out[2]["이름"], (out[0]["이름"], out[2]["이름"]))

        # 6. THE POINT: average salary is computable directly from the de-id file,
        #    because salaries stayed raw.
        def won(s):
            return int(re.sub(r"[^0-9]", "", s))
        avg_out = sum(won(r["연봉"]) for r in out) / len(out)
        avg_raw = sum(won(r["연봉"]) for r in ROWS) / len(ROWS)
        check("average computable & correct", avg_out == avg_raw == 5000, (avg_out, avg_raw))

        # 7. Reversible via the plaintext map (no key).
        re_path = os.path.join(d, "restored.json")
        reid.reidentify(map_path, out_path, re_path)
        restored = json.load(open(re_path, encoding="utf-8"))
        check("reidentify restores identifiers", restored == ROWS, "restored != original")

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
