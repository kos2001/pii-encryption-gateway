#!/usr/bin/env python3
"""Capability/performance verification for the keyless de-identification mode.

The new mode's reason to exist: let the model compute aggregates (e.g. average
salary) WITHOUT exposing raw identifiers. This compares three ways of preparing
the LLM-visible file on an aggregate task ("부서별 평균 연봉"), measuring two
things that matter together:

  1. identifier leakage  — how many raw direct-identifier values remain readable
  2. aggregate computable — can per-department average salary be computed from
     the file, and is it correct vs ground truth?

Only a method that scores 0 leaks AND a correct average satisfies the goal.
Deterministic (no LLM); also reports timing. Non-zero exit if the keyless mode
fails to uniquely satisfy both.

Usage:  python3 tests/deid_eval.py
"""

import csv
import json
import os
import re
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pii-encryption-gateway", "scripts")
sys.path.insert(0, SCRIPTS)

import protect as keyed          # noqa: E402
import deidentify as deid        # noqa: E402
from pii_config import classify_identifier  # noqa: E402

DATASET = os.path.join(ROOT, "data", "employees.csv")
KEY = "handler-hr-alice-key-001"


_TOKEN_RE = re.compile(r"\[\[[A-Z_]+:[0-9a-f]{8}\]\]")


def _won(s):
    s = str(s)
    if _TOKEN_RE.search(s):
        return None  # tokenized -> not a real number, can't aggregate
    digits = re.sub(r"[^0-9]", "", s)
    return int(digits) if digits else None


def _rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _identifier_values(rows):
    vals = set()
    for r in rows:
        for col, v in r.items():
            if classify_identifier(col) and str(v).strip():
                vals.add(str(v).strip())
    return vals


def _leaks(records, id_values):
    blob = json.dumps(records, ensure_ascii=False)
    return sum(1 for v in id_values if v in blob)


def _dept_avg(records):
    """Try to compute per-dept average salary from the records. Returns dict or
    None if salaries aren't numeric (i.e. tokenized -> not computable)."""
    acc = {}
    for r in records:
        val = _won(r.get("연봉", ""))
        if val is None:
            return None  # salary not numeric here (tokenized) -> can't aggregate
        acc.setdefault(r["부서"], []).append(val)
    return {d: round(sum(v) / len(v)) for d, v in acc.items()}


def run():
    raw = _rows(DATASET)
    id_values = _identifier_values(raw)
    truth = _dept_avg(raw)

    results = {}
    with tempfile.TemporaryDirectory() as d:
        # Baseline: the raw file is what the LLM would read.
        results["baseline (raw file)"] = {
            "records": raw, "secs": 0.0,
        }
        # Keyed gateway: protect.py -> protected.json (salary tokenized).
        prot = os.path.join(d, "p.json"); vault = os.path.join(d, "v.json")
        t0 = time.time()
        _so = sys.stdout; sys.stdout = open(os.devnull, "w")
        keyed.protect(KEY, DATASET, prot, vault)
        sys.stdout = _so
        results["keyed gateway (protect.py)"] = {
            "records": json.load(open(prot, encoding="utf-8")), "secs": time.time() - t0,
        }
        # Keyless de-id: deidentify.py -> deidentified.json (salary raw).
        out = os.path.join(d, "deid.json"); mp = os.path.join(d, "map.json")
        t0 = time.time()
        _so = sys.stdout; sys.stdout = open(os.devnull, "w")
        deid.deidentify(DATASET, out, mp)
        sys.stdout = _so
        results["keyless de-id (deidentify.py)"] = {
            "records": json.load(open(out, encoding="utf-8")), "secs": time.time() - t0,
        }

    total_ids = len(id_values)
    print(f"Dataset: {len(raw)} records · {total_ids} distinct identifier values · "
          f"task = 부서별 평균 연봉\n")
    print(f"{'method':<32}{'id leaks':>12}{'avg computable':>16}{'avg correct':>13}{'secs':>8}")
    print("-" * 81)
    summary = {}
    for name, r in results.items():
        leaks = _leaks(r["records"], id_values)
        avg = _dept_avg(r["records"])
        computable = avg is not None
        correct = computable and avg == truth
        summary[name] = (leaks, computable, correct)
        print(f"{name:<32}{f'{leaks}/{total_ids}':>12}"
              f"{('yes' if computable else 'no'):>16}{('yes' if correct else '—'):>13}"
              f"{r['secs']:>8.2f}")
    print("-" * 81)

    base = summary["baseline (raw file)"]
    keyed_s = summary["keyed gateway (protect.py)"]
    deid_s = summary["keyless de-id (deidentify.py)"]
    print("\nReading:")
    print(f"  · baseline      → avg works but leaks {base[0]} identifiers (unsafe)")
    print(f"  · keyed gateway → 0 leaks but avg NOT computable (salary sealed)")
    print(f"  · keyless de-id → 0 leaks AND avg computable & correct ✓ (the goal)")

    ok = (deid_s == (0, True, True) and keyed_s[0] == 0 and not keyed_s[1] and base[0] > 0)
    print("\nRESULT:", "PASS — keyless de-id uniquely satisfies (no id leak + correct average)"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
