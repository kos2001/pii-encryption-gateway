#!/usr/bin/env python3
"""Leakage eval: column-only protection vs column + value-level recognizers.

Motivation: the existing eval set is all well-formed CSV with correctly named
columns, where column-name classification alone scores 100%. That set never
exercises the failure mode the recognizer layer was built for — PII that lives
in a free-text or mis-named column. This eval injects exactly that and measures
how much each strategy leaks.

It is deterministic (no LLM): "leak" = a known sensitive original still appears
verbatim in the protected payload the model would read.

Baseline  = tokenize only columns pii_config marks sensitive (the old behavior).
Gateway   = full protect.py, i.e. baseline + the recognizer second pass.

Usage:  python3 tests/leakage_eval.py
"""

import csv
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import crypto_core  # noqa: E402
import protect as protect_mod  # noqa: E402
from pii_config import classify_field  # noqa: E402

KEY = "handler-hr-alice-key-001"
DATASET = os.path.join(ROOT, "data", "employees.csv")


def _load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _inject_freetext(rows):
    """Add the columns column-name classification can't see, carrying each
    row's own PII in prose plus an RRN in a mis-named remarks column."""
    injected_values = set()
    for r in rows:
        memo = (f"담당자 메모: 연락처 {r['전화번호']}, 메일 {r['이메일']}, "
                f"급여 계좌 {r['계좌번호']} 로 확인 바람")
        remarks = f"신원확인용 주민번호 {r['주민등록번호']} 기재됨"
        r["관리자메모"] = memo          # free-text column, not in aliases
        r["비고"] = remarks             # mis-named remarks column
        injected_values |= {r["전화번호"], r["이메일"], r["계좌번호"], r["주민등록번호"]}
    return injected_values


def _baseline_protect(rows):
    """Old behavior: tokenize ONLY name-classified sensitive columns."""
    out = []
    for r in rows:
        nr = {}
        for col, val in r.items():
            t = classify_field(col)
            if t and val not in (None, ""):
                nr[col] = crypto_core.make_token(KEY, t, str(val))
            else:
                nr[col] = val
        out.append(nr)
    return out


def _count_leaks(protected_rows, sensitive_values):
    blob = json.dumps(protected_rows, ensure_ascii=False)
    return sum(1 for v in sensitive_values if v and v in blob)


def run():
    rows = _load_rows(DATASET)
    sensitive = _inject_freetext(rows)
    print(f"Dataset: {len(rows)} records, "
          f"{len(sensitive)} distinct PII values injected into free-text/"
          f"mis-named columns (관리자메모, 비고)\n")

    baseline = _baseline_protect([dict(r) for r in rows])
    baseline_leaks = _count_leaks(baseline, sensitive)

    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "in.json")
        prot = os.path.join(d, "protected.json")
        vault = os.path.join(d, "vault.json")
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump([dict(r) for r in rows], f, ensure_ascii=False)
        # Silence protect's summary print for a clean table.
        _stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")
        protect_mod.protect(KEY, in_path, prot, vault)
        sys.stdout = _stdout
        gateway = json.load(open(prot, encoding="utf-8"))
        gateway_leaks = _count_leaks(gateway, sensitive)

    total = len(sensitive)
    print(f"{'Strategy':<34}{'PII values leaked':>20}{'Recall':>10}")
    print("-" * 64)
    b_recall = (total - baseline_leaks) / total
    g_recall = (total - gateway_leaks) / total
    print(f"{'column-name only (baseline)':<34}{baseline_leaks:>14}/{total:<5}{b_recall:>9.0%}")
    print(f"{'column + recognizers (gateway)':<34}{gateway_leaks:>14}/{total:<5}{g_recall:>9.0%}")
    print("-" * 64)
    print(f"\nLeakage eliminated by the recognizer pass: "
          f"{baseline_leaks - gateway_leaks} of {baseline_leaks} "
          f"({(baseline_leaks - gateway_leaks) / baseline_leaks:.0%})")

    ok = gateway_leaks == 0 and baseline_leaks > 0
    print("\nRESULT:", "PASS — recognizer layer seals the free-text leak"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
