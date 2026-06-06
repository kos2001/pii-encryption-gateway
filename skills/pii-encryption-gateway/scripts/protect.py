#!/usr/bin/env python3
"""Replace sensitive values with deterministic tokens before LLM processing.

Reads a CSV or JSON dataset, swaps every sensitive field value for a token,
encrypts the originals into a vault under the handler's key, and writes a
protected dataset that is safe to show an LLM.

Critically, this script NEVER prints a raw sensitive value — its stdout carries
only counts and token examples. That is what makes it safe to run inside an
agent loop: the protected output and the summary are all the agent ever sees.

Usage:
    python protect.py --key "<handler-key>" --in data.csv \
        --out protected.json --vault vault.json
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crypto_core  # noqa: E402
import recognizers  # noqa: E402
from pii_config import classify_field  # noqa: E402


def _tokenize_spans(handler_key, text, vault_entries, type_counts):
    """Replace any PII spans the value-level recognizers find inside `text`.

    Used for columns the name-based classifier does NOT mark sensitive — a
    free-text or mis-named column may still carry an RRN, phone, or email.
    Returns the text with each detected span swapped for its token; non-PII
    surrounding text is left intact. Replaces right-to-left so earlier offsets
    stay valid.
    """
    spans = recognizers.analyze(text)
    if not spans:
        return text
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        original = text[span.start:span.end]
        token = crypto_core.make_token(handler_key, span.entity_type, original)
        if token not in vault_entries:
            vault_entries[token] = crypto_core.encrypt(handler_key, original)
        text = text[:span.start] + token + text[span.end:]
        type_counts[span.entity_type] = type_counts.get(span.entity_type, 0) + 1
    return text


def _load_records(path: str):
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _infer_columns(records):
    """Value-sample each column the name-classifier missed and, where the
    column's values ARE a single PII entity, return column -> inferred type.

    Classifying at the column level (not just per cell) lets us seal an odd
    malformed cell that the per-value recognizers can't match on its own.
    """
    if not records:
        return {}
    columns = {}
    for record in records:
        for column, value in record.items():
            columns.setdefault(column, []).append(value)
    inferred = {}
    for column, values in columns.items():
        if classify_field(column) is not None:
            continue
        result = recognizers.infer_column_type(values)
        if result is not None:
            inferred[column] = result[0]
    return inferred


def protect(handler_key, in_path, out_path, vault_path):
    records = _load_records(in_path)
    vault_entries = {}  # token -> ciphertext(original value)
    type_counts = {}
    protected = []

    inferred_columns = _infer_columns(records)

    for record in records:
        new_record = {}
        for column, value in record.items():
            token_type = classify_field(column) or inferred_columns.get(column)
            if token_type is None or value in (None, ""):
                # Column neither name-classified nor value-inferred — still scan
                # the value itself, so PII embedded in free text is caught.
                if isinstance(value, str) and value:
                    new_record[column] = _tokenize_spans(
                        handler_key, value, vault_entries, type_counts)
                else:
                    new_record[column] = value
                continue
            token = crypto_core.make_token(handler_key, token_type, str(value))
            if token not in vault_entries:
                vault_entries[token] = crypto_core.encrypt(handler_key, str(value))
            new_record[column] = token
            type_counts[token_type] = type_counts.get(token_type, 0) + 1
        protected.append(new_record)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(protected, f, ensure_ascii=False, indent=2)

    vault = {"version": 1, "entry_count": len(vault_entries), "entries": vault_entries}
    with open(vault_path, "w", encoding="utf-8") as f:
        json.dump(vault, f, ensure_ascii=False, indent=2)

    # Summary only — no raw values cross this boundary.
    print(f"Protected {len(protected)} records -> {out_path}")
    print(f"Vault: {len(vault_entries)} unique values encrypted -> {vault_path}")
    print("Tokenized fields: " + ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items())))
    if inferred_columns:
        # Surface columns protected by value shape rather than name, so the
        # handler can sanity-check the auto-detection (column names only — never
        # values).
        print("Auto-detected by value shape: "
              + ", ".join(f"{c}={t}" for c, t in sorted(inferred_columns.items())))


def main():
    p = argparse.ArgumentParser(description="Tokenize sensitive fields before LLM use.")
    p.add_argument("--key", required=True, help="Handler's secret key")
    p.add_argument("--in", dest="in_path", required=True, help="Input CSV or JSON")
    p.add_argument("--out", dest="out_path", required=True, help="Protected JSON output")
    p.add_argument("--vault", dest="vault_path", required=True, help="Encrypted vault output")
    args = p.parse_args()
    protect(args.key, args.in_path, args.out_path, args.vault_path)


if __name__ == "__main__":
    main()
