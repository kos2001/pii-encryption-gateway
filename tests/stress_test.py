#!/usr/bin/env python3
"""Large-scale + adversarial stress tests for the PII encryption gateway.

Runs fully programmatically (no LLM/subagents): fast, deterministic, repeatable.
Covers the security properties the gateway promises:

  1. No leakage      — no original sensitive value survives in the protected payload
  2. Round-trip      — every protected value decrypts back to the exact original
  3. Wrong key       — a different handler key cannot decrypt (raises, never leaks)
  4. Cross-handler   — same value yields different tokens under different keys
  5. Determinism     — same value yields the same token within one handler
  6. Token format    — every emitted token matches the reveal regex
  7. reveal()        — end-to-end protect→draft→reveal restores values verbatim
  8. Edge cases      — empty, commas, unicode, newlines, token-looking values, dupes
  9. Performance     — protect+reveal timing at scale (reported, not asserted)

Exit code is non-zero if any assertion fails, so this doubles as CI.

Usage:  python3 tests/stress_test.py [--dataset data/employees.csv]
"""

import argparse
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

import crypto_core  # noqa: E402
from pii_config import classify_field  # noqa: E402
import protect as protect_mod  # noqa: E402
import reveal as reveal_mod  # noqa: E402

TOKEN_RE = re.compile(r"\[\[[A-Z_]+:[0-9a-f]{8}\]\]")
KEY_A = "handler-hr-alice-key-001"
KEY_B = "handler-payroll-bob-key-777"

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


def load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sensitive_values(rows):
    vals = set()
    for r in rows:
        for col, v in r.items():
            if classify_field(col) and v not in (None, ""):
                vals.add(str(v))
    return vals


def test_scale(rows):
    print(f"\n[1] Scale tests on {len(rows)} records")
    with tempfile.TemporaryDirectory() as d:
        prot = os.path.join(d, "protected.json")
        vault = os.path.join(d, "vault.json")
        t0 = time.time()
        protect_mod.protect(KEY_A, _write_csv(rows, d), prot, vault)
        protect_secs = time.time() - t0

        protected = json.load(open(prot, encoding="utf-8"))
        vault_obj = json.load(open(vault, encoding="utf-8"))

        # 1. No leakage: no sensitive value survives as a READABLE cell value.
        # Substring scanning is wrong for short values — a "12" attendance count
        # trivially appears inside a token hash ([[X:6612c51d]]) or a non-sensitive
        # plaintext cell (사번 E0012, 입사일 2012-..). The real question is whether
        # any cell the LLM reads holds a sensitive value in the clear, so compare
        # whole cell values: the set of non-token plaintext cells must be disjoint
        # from the set of sensitive originals.
        sens = sensitive_values(rows)
        plaintext_cells = {str(v) for rec in protected for v in rec.values()
                           if v not in (None, "") and not TOKEN_RE.fullmatch(str(v))}
        leaked = sorted(sens & plaintext_cells)
        check("no sensitive value survives as a readable cell in the protected payload",
              not leaked, f"{len(leaked)} leaked e.g. {leaked[:3]}")

        # 6. Token format + every sensitive cell is a token
        bad_fmt, untokenized = [], []
        for orig, prot_rec in zip(rows, protected):
            for col, v in orig.items():
                if classify_field(col) and v not in (None, ""):
                    tok = prot_rec[col]
                    if not TOKEN_RE.fullmatch(tok):
                        bad_fmt.append((col, tok))
        check("every sensitive cell holds a well-formed token", not bad_fmt, str(bad_fmt[:3]))

        # 2. Round-trip: decrypt each vault entry, rebuild each record, compare
        mism = 0
        for orig, prot_rec in zip(rows, protected):
            for col, v in orig.items():
                if classify_field(col) and v not in (None, ""):
                    if crypto_core.decrypt(KEY_A, vault_obj["entries"][prot_rec[col]]) != str(v):
                        mism += 1
        check("round-trip restores every value exactly", mism == 0, f"{mism} mismatches")

        # 3. Wrong key: every entry fails to decrypt
        wrong_ok = 0
        for blob_ct in list(vault_obj["entries"].values())[:50]:  # sample 50 for speed
            try:
                crypto_core.decrypt(KEY_B, blob_ct)
                wrong_ok += 1  # should never succeed
            except ValueError:
                pass
        check("wrong key cannot decrypt any sampled entry (no silent leak)",
              wrong_ok == 0, f"{wrong_ok} decrypted with wrong key")

        t0 = time.time()
        # 7. reveal end-to-end: build a draft referencing some tokens
        sample_tokens = list(vault_obj["entries"].keys())[:20]
        draft = "보고서 초안\n" + "\n".join(f"- {t}" for t in sample_tokens)
        draft_p = os.path.join(d, "draft.txt")
        final_p = os.path.join(d, "final.txt")
        open(draft_p, "w", encoding="utf-8").write(draft)
        reveal_mod.reveal(KEY_A, vault, draft_p, final_p)
        restored = open(final_p, encoding="utf-8").read()
        reveal_secs = time.time() - t0
        check("reveal leaves no residual tokens", not TOKEN_RE.search(restored),
              "tokens remain")
        check("reveal output matches direct decryption",
              all(crypto_core.decrypt(KEY_A, vault_obj["entries"][t]) in restored
                  for t in sample_tokens), "value missing")

        print(f"  TIME  protect {len(rows)} rows: {protect_secs:.2f}s | "
              f"reveal 20 tokens: {reveal_secs:.3f}s")


def test_determinism_and_isolation(rows):
    print("\n[2] Determinism & cross-handler isolation")
    sample = [r for r in rows[:30]]
    # 5. determinism: same value -> same token (twice)
    det = all(
        crypto_core.make_token(KEY_A, "SALARY", r["연봉"])
        == crypto_core.make_token(KEY_A, "SALARY", r["연봉"]) for r in sample)
    check("same value yields identical token within a handler", det)
    # 4. cross-handler: different key -> different token for same value
    diff = all(
        crypto_core.make_token(KEY_A, "NAME", r["이름"])
        != crypto_core.make_token(KEY_B, "NAME", r["이름"]) for r in sample)
    check("different handler keys yield different tokens for same value", diff)
    # field-type separation: same string under different field types -> different tokens
    sep = crypto_core.make_token(KEY_A, "NAME", "123") != crypto_core.make_token(KEY_A, "SALARY", "123")
    check("same string under different field types yields different tokens", sep)


def test_edge_cases():
    print("\n[3] Adversarial edge cases")
    edge = [
        {"사번": "X1", "이름": "", "연봉": "3000만원", "계좌번호": "국민 1-2-3"},          # empty value
        {"사번": "X2", "이름": "오,쉼표", "연봉": "1,234만원", "계좌번호": "신한 9-9-9"},   # commas
        {"사번": "X3", "이름": "李성한자🙂", "연봉": "0만원", "계좌번호": "우리 0-0-0"},     # unicode/emoji/zero
        {"사번": "X4", "이름": "줄\n바꿈", "연봉": "9999999만원", "계좌번호": "하나 7-7-7"}, # newline + huge
        {"사번": "X5", "이름": "[[NAME:deadbeef]]", "연봉": "5000만원", "계좌번호": "농협 5-5-5"},  # token-looking value
        {"사번": "X6", "이름": "김중복", "연봉": "4000만원", "계좌번호": "국민 4-4-4"},      # duplicate name A
        {"사번": "X7", "이름": "김중복", "연봉": "4000만원", "계좌번호": "신한 8-8-8"},      # duplicate name B (same name+salary)
    ]
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "edge.json")
        json.dump(edge, open(src, "w", encoding="utf-8"), ensure_ascii=False)
        prot, vault = os.path.join(d, "p.json"), os.path.join(d, "v.json")
        protect_mod.protect(KEY_A, src, prot, vault)
        protected = json.load(open(prot, encoding="utf-8"))
        vault_obj = json.load(open(vault, encoding="utf-8"))

        # empty value stays empty (not tokenized)
        check("empty sensitive value is left untouched", protected[0]["이름"] == "")

        # every non-empty sensitive value round-trips, including weird ones
        mism = []
        for orig, pr in zip(edge, protected):
            for col, v in orig.items():
                if classify_field(col) and v not in (None, ""):
                    got = crypto_core.decrypt(KEY_A, vault_obj["entries"][pr[col]])
                    if got != v:
                        mism.append((col, repr(v), repr(got)))
        check("commas/unicode/emoji/newline/zero/huge values round-trip exactly",
              not mism, str(mism[:3]))

        # token-looking input value is protected (not passed through raw)
        check("a value that looks like a token is itself tokenized (no passthrough)",
              TOKEN_RE.fullmatch(protected[4]["이름"]) is not None
              and protected[4]["이름"] != "[[NAME:deadbeef]]",
              protected[4]["이름"])

        # reveal of a token-looking original does not get re-substituted into chaos
        draft_p, final_p = os.path.join(d, "dr.txt"), os.path.join(d, "fi.txt")
        open(draft_p, "w", encoding="utf-8").write(f"name is {protected[4]['이름']} end")
        reveal_mod.reveal(KEY_A, vault, draft_p, final_p)
        out = open(final_p, encoding="utf-8").read()
        check("restoring a token-looking value yields the literal original once",
              "name is [[NAME:deadbeef]] end" == out.strip(), repr(out))

        # duplicate name+salary collapses to the same token (documented behavior)
        check("identical (name,salary) across two people share a token (value-based)",
              protected[5]["이름"] == protected[6]["이름"]
              and protected[5]["연봉"] == protected[6]["연봉"])


def _write_csv(rows, d):
    p = os.path.join(d, "src.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=os.path.join(ROOT, "data", "employees.csv"))
    a = ap.parse_args()
    rows = load_rows(a.dataset)

    print("=" * 64)
    print("PII ENCRYPTION GATEWAY — STRESS TEST")
    print("=" * 64)
    test_scale(rows)
    test_determinism_and_isolation(rows)
    test_edge_cases()

    print("\n" + "=" * 64)
    print(f"RESULT: {_passed} passed, {_failed} failed")
    print("=" * 64)
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
