#!/usr/bin/env python3
"""Restore real values into LLM output, for the authorized handler only.

Scans text (or a JSON file) for tokens, decrypts the matching vault entries
with the handler's key, and substitutes the originals back in. Decryption is
authenticated: a wrong key raises before anything is written, so a handler can
only reveal data they hold the key for.

Usage:
    python reveal.py --key "<handler-key>" --vault vault.json \
        --in llm_output.txt --out final.txt
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crypto_core  # noqa: E402

TOKEN_RE = re.compile(r"\[\[[A-Z_]+:[0-9a-f]{8}\]\]")


def reveal(handler_key, vault_path, in_path, out_path):
    with open(vault_path, encoding="utf-8") as f:
        vault = json.load(f)
    entries = vault.get("entries", {})

    with open(in_path, encoding="utf-8") as f:
        text = f.read()

    tokens = set(TOKEN_RE.findall(text))
    resolved, unknown = {}, []
    for token in tokens:
        if token in entries:
            resolved[token] = crypto_core.decrypt(handler_key, entries[token])
        else:
            unknown.append(token)

    def _sub(match):
        return resolved.get(match.group(0), match.group(0))

    restored = TOKEN_RE.sub(_sub, text)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(restored)

    print(f"Revealed {len(resolved)} token(s) -> {out_path}")
    if unknown:
        print(f"WARNING: {len(unknown)} token(s) not in vault (left as-is): "
              + ", ".join(sorted(unknown)))


def main():
    p = argparse.ArgumentParser(description="Restore real values into protected output.")
    p.add_argument("--key", required=True, help="Handler's secret key")
    p.add_argument("--vault", dest="vault_path", required=True, help="Vault from protect.py")
    p.add_argument("--in", dest="in_path", required=True, help="LLM output (text/JSON)")
    p.add_argument("--out", dest="out_path", required=True, help="Restored output")
    args = p.parse_args()
    reveal(args.key, args.vault_path, args.in_path, args.out_path)


if __name__ == "__main__":
    main()
