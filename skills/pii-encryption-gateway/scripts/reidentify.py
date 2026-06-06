#!/usr/bin/env python3
"""Restore identifiers from a keyless de-identification map (no key).

Counterpart to deidentify.py: scans text or a JSON file for tokens and
substitutes each back using the PLAINTEXT token->value map. Because there is no
key, anyone with the map can restore — the map is the secret, so guard it like
the originals.

Usage:
    python reidentify.py --map map.json --in deidentified.json --out restored.json
"""

import argparse
import json
import os
import re
import sys

TOKEN_RE = re.compile(r"\[\[[A-Z_]+:[0-9a-f]{8}\]\]")


def _restore_text(text, mapping):
    return TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)


def reidentify(map_path, in_path, out_path):
    with open(map_path, encoding="utf-8") as f:
        mapping = json.load(f)

    if in_path.lower().endswith(".json"):
        with open(in_path, encoding="utf-8") as f:
            data = json.load(f)

        def walk(o):
            if isinstance(o, str):
                return _restore_text(o, mapping)
            if isinstance(o, list):
                return [walk(x) for x in o]
            if isinstance(o, dict):
                return {k: walk(v) for k, v in o.items()}
            return o

        restored = walk(data)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(restored, f, ensure_ascii=False, indent=2)
        n = "json"
    else:
        with open(in_path, encoding="utf-8") as f:
            text = f.read()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(_restore_text(text, mapping))
        n = "text"

    print(f"Re-identified ({n}) -> {out_path}")


def main():
    p = argparse.ArgumentParser(description="Restore identifiers from a keyless de-id map.")
    p.add_argument("--map", dest="map_path", required=True, help="Plaintext map from deidentify.py")
    p.add_argument("--in", dest="in_path", required=True, help="De-identified text/JSON")
    p.add_argument("--out", dest="out_path", required=True, help="Restored output")
    args = p.parse_args()
    reidentify(args.map_path, args.in_path, args.out_path)


if __name__ == "__main__":
    main()
