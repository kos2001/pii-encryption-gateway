#!/usr/bin/env python3
"""Keyless de-identification: tokenize direct identifiers, keep numbers raw.

The lightweight alternative to the keyed gateway (protect.py). It replaces only
DIRECT IDENTIFIERS (name, RRN, account, phone, email, employee id — plus
value-shape matches like card/BRN/IP in free text) with deterministic, keyless
tokens, and leaves everything else — including numeric attributes like salary
and attendance — RAW. So the model never sees raw identifiers, yet can still
compute averages/sums over the numbers directly.

Reversibility is a PLAINTEXT map (token -> original), not an encrypted vault.
The protection is the same discipline as the keyed mode — never open the map —
minus at-rest encryption. Choose this only when that trade-off is acceptable.

Usage:
    python deidentify.py --in data.csv --out deidentified.json --map map.json
        [--names-from roster.csv] [--names "a,b"]
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deid_core  # noqa: E402
import recognizers  # noqa: E402
from pii_config import classify_identifier, IDENTIFIER_TYPES  # noqa: E402

TEXT_EXTENSIONS = (".txt", ".md", ".markdown", ".text")


def _load_records(path):
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _load_names(path):
    names = set()
    for record in _load_records(path):
        for column, value in record.items():
            if classify_identifier(column) == "NAME" and isinstance(value, str) and value.strip():
                names.add(value.strip())
    return names


def _tok(field_type, value, mapping):
    t = deid_core.token(field_type, str(value))
    mapping[t] = str(value)        # plaintext map (token -> original)
    return t


def _deid_spans(text, mapping, names):
    """Tokenize identifier-type spans (and known names) inside free text;
    numbers/other text are left untouched."""
    spans = list(recognizers.analyze(text))          # all recognizer types are identifiers
    if names:
        spans = recognizers._resolve_overlaps(spans + recognizers.find_names(text, names))
    spans = [s for s in spans if s.entity_type in IDENTIFIER_TYPES]
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        original = text[span.start:span.end]
        text = text[:span.start] + _tok(span.entity_type, original, mapping) + text[span.end:]
    return text


def _deidentify_document(in_path, out_path, map_path, names):
    with open(in_path, encoding="utf-8") as f:
        text = f.read()
    mapping = {}
    out = _deid_spans(text, mapping, names)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    _write_map(map_path, mapping)
    print(f"De-identified document ({len(text)} chars) -> {out_path}")
    print(f"Map: {len(mapping)} identifier value(s) -> {map_path} (PLAINTEXT, no key)")


def _write_map(map_path, mapping):
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def deidentify(in_path, out_path, map_path, names=frozenset()):
    if in_path.lower().endswith(TEXT_EXTENSIONS):
        return _deidentify_document(in_path, out_path, map_path, names)

    records = _load_records(in_path)
    mapping = {}
    type_counts = {}
    out = []
    for record in records:
        new = {}
        for column, value in record.items():
            t = classify_identifier(column)
            if t is not None and value not in (None, ""):
                new[column] = _tok(t, value, mapping)
                type_counts[t] = type_counts.get(t, 0) + 1
            elif isinstance(value, str) and value:
                # non-identifier text column may still embed an identifier (free text)
                new[column] = _deid_spans(value, mapping, names)
            else:
                new[column] = value          # numbers / non-sensitive -> RAW
        out.append(new)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    _write_map(map_path, mapping)

    print(f"De-identified {len(out)} records -> {out_path}")
    print(f"Map: {len(mapping)} identifier value(s) -> {map_path} (PLAINTEXT, no key)")
    print("Tokenized identifiers: "
          + (", ".join(f"{k}={v}" for k, v in sorted(type_counts.items())) or "none"))
    print("Numeric/other fields kept RAW for analysis (e.g. averages).")


def main():
    p = argparse.ArgumentParser(description="Keyless de-identification (identifiers->tokens, numbers raw).")
    p.add_argument("--in", dest="in_path", required=True, help="Input CSV/JSON or TXT/MD")
    p.add_argument("--out", dest="out_path", required=True, help="De-identified output")
    p.add_argument("--map", dest="map_path", required=True, help="Plaintext token->value map")
    p.add_argument("--names-from", dest="names_from", help="Roster whose name column seeds a name deny-list")
    p.add_argument("--names", help="Comma-separated names to also tokenize")
    args = p.parse_args()
    names = set()
    if args.names_from:
        names |= _load_names(args.names_from)
    if args.names:
        names |= {n.strip() for n in args.names.split(",") if n.strip()}
    deidentify(args.in_path, args.out_path, args.map_path, names)


if __name__ == "__main__":
    main()
