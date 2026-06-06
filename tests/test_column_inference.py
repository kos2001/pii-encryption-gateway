#!/usr/bin/env python3
"""TDD tests for value-sampling column inference (presidio-structured idea).

Per-cell recognition (priority 1) misses a cell that doesn't match its pattern
even when the column is obviously PII. Column inference generalizes from the
majority of a column's values: if most non-empty samples ARE a single PII
entity (the match covers ~the whole cell, not a fragment of prose), the whole
column is classified — so the odd malformed or off-format cell is sealed too.

The "covers the whole cell" test is what separates a dedicated PII column
(every cell IS a phone) from a free-text column (a cell CONTAINS a phone in a
sentence). The latter must stay span-level, so it must NOT be column-classified.

Plain-assertion runner; non-zero exit on failure.

Usage:  python3 tests/test_column_inference.py
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


def typ(values):
    r = recognizers.infer_column_type(values)
    return r[0] if r else None


def run():
    phones = [f"010-{1000+i}-{2000+i}" for i in range(30)]
    rrns = [f"7703{10+i}-180957{i%10}" for i in range(30)]
    emails = [f"user{i:04d}@company.co.kr" for i in range(30)]
    accounts = [f"신한 {100+i}-{1000+i}-{100000+i}" for i in range(30)]

    # 1. Homogeneous PII columns are classified by value shape.
    check("phone column inferred", typ(phones) == "PHONE", typ(phones))
    check("rrn column inferred", typ(rrns) == "RRN", typ(rrns))
    check("email column inferred", typ(emails) == "EMAIL", typ(emails))
    check("account column inferred", typ(accounts) == "ACCOUNT", typ(accounts))

    # 2. A free-text column (PII embedded in a sentence) is NOT column-classified
    #    — it stays span-level so surrounding prose is preserved.
    memos = [f"연락은 010-{1000+i}-{2000+i} 로 부탁드립니다 확인 요망" for i in range(30)]
    check("free-text column not column-classified", typ(memos) is None, typ(memos))

    # 3. Benign structural columns must not be misclassified.
    check("date column not classified", typ([f"2018-02-{1+i%27:02d}" for i in range(30)]) is None)
    check("dept column not classified", typ(["영업팀", "인사팀", "개발팀"] * 10) is None)
    check("count column not classified", typ([str(i % 16) for i in range(30)]) is None)
    check("salary-as-text not classified", typ([f"{3200+i}만원" for i in range(30)]) is None)

    # 4. A majority-phone column with a few malformed/blank cells still classifies
    #    as PHONE — this is the cell the per-cell pass would have leaked.
    messy = phones[:27] + ["010-12-34567", "", "n/a"]
    check("majority-phone column survives a few bad cells", typ(messy) == "PHONE", typ(messy))

    # 5. No dominant type -> not classified.
    mixed = ["영업팀", "2018-02-19", "5350만원", "과장", "10"] * 6
    check("mixed column not classified", typ(mixed) is None, typ(mixed))

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(run())
