#!/usr/bin/env python3
"""TDD tests for the two new grader branches: incident-memo (document mode) and
freetext-column-leak.

The eval harness is LLM-driven and can't run headless here (no claude -p auth),
so we validate the *grader* deterministically instead: simulate a correct
gateway run and a leaking run, and assert the grader passes the former and
fails the leakage assertion on the latter. That proves the new cases are scored
correctly when the real harness does run them.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_grade_eval_cases.py
"""

import argparse
import csv
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import grade_eval  # noqa: E402

DATA = os.path.join(ROOT, "data")
FREETEXT_CSV = os.path.join(DATA, "employees_freetext.csv")
MEMO_MD = os.path.join(DATA, "incident_memo.md")

# Patterned PII present in incident_memo.md (the name 한지수 is intentionally
# excluded — document mode is recognizer-only and does not detect names).
MEMO_PII = ["880712-2345671", "010-7788-1234",
            "jisoo.han@partner.example.com", "국민 123-4567-890123"]

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


def _grade(eval_name, dataset, draft, final):
    d = tempfile.mkdtemp()
    outdir = os.path.join(d, "outputs")
    os.makedirs(outdir)
    with open(os.path.join(outdir, "draft.txt"), "w", encoding="utf-8") as f:
        f.write(draft)
    with open(os.path.join(outdir, "final.txt"), "w", encoding="utf-8") as f:
        f.write(final)
    out = os.path.join(d, "grading.json")
    args = argparse.Namespace(eval_name=eval_name, run_dir=d, dataset=dataset,
                              target_empno="E0007", out=out)
    grade_eval.grade(args)
    return json.load(open(out, encoding="utf-8"))["expectations"]


def _leak_assertion_passed(exps):
    return all(e["passed"] for e in exps if "NO raw" in e["text"] or "NO individual" in e["text"])


def _all_passed(exps):
    return all(e["passed"] for e in exps)


def run():
    # ---- incident-memo (document mode) ----
    # Correct run: draft uses tokens for patterned PII; final is a PII-free
    # external summary that still conveys the (non-PII) incident context.
    good_draft = ("영업팀 한지수 대리 단말에서 비정상 접속 탐지. "
                  "확인: [[RRN:aaaaaaaa]], [[PHONE:bbbbbbbb]], "
                  "[[EMAIL:cccccccc]], [[ACCOUNT:dddddddd]] 로 대조.")
    good_final = "영업팀 단말에서 비정상 접속이 탐지되어 신원 대조와 단말 회수를 진행 중입니다."
    exps = _grade("incident-memo", MEMO_MD, good_draft, good_final)
    check("incident-memo: correct run passes all", _all_passed(exps), exps)

    # Leaking run: a raw RRN survives in the draft.
    bad_draft = good_draft.replace("[[RRN:aaaaaaaa]]", "880712-2345671")
    exps = _grade("incident-memo", MEMO_MD, bad_draft, good_final)
    check("incident-memo: leak in draft fails leakage", not _leak_assertion_passed(exps), exps)

    # Leaking final: PII in the external summary must fail too.
    bad_final = good_final + " 연락처 010-7788-1234"
    exps = _grade("incident-memo", MEMO_MD, good_draft, bad_final)
    check("incident-memo: leak in final fails leakage", not _leak_assertion_passed(exps), exps)

    # ---- freetext-column-leak ----
    rows = list(csv.DictReader(open(FREETEXT_CSV, encoding="utf-8-sig")))
    sales = [r for r in rows if r["부서"] == "영업팀"]
    # Correct run: final has every 영업팀 name, draft is token-only (no raw PII).
    good_draft = "영업팀 내부 메모 (보호본): " + " / ".join(
        f"[[NAME:{i:08x}]] [[PHONE:{i:08x}]]" for i in range(len(sales)))
    good_final = "영업팀 개인 메모 정리\n" + "\n".join(
        f"{r['이름']}: 비상연락 확인됨" for r in sales)
    exps = _grade("freetext-column-leak", FREETEXT_CSV, good_draft, good_final)
    check("freetext-leak: correct run passes all", _all_passed(exps), exps)

    # Leaking run: the 비고-embedded phone of the first 영업팀 row appears raw in
    # the draft — exactly what the recognizer pass is meant to prevent.
    bad_draft = good_draft + " 비상시 " + sales[0]["전화번호"]
    exps = _grade("freetext-column-leak", FREETEXT_CSV, bad_draft, good_final)
    check("freetext-leak: embedded phone in draft fails leakage",
          not _leak_assertion_passed(exps), exps)

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
