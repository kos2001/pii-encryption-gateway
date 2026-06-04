#!/usr/bin/env python3
"""Compute the deterministic token for a value you already know.

Use this to locate a record in protected.json by a sensitive reference the user
gave you — e.g. a 사번 (employee ID) like "E0007" or a name — WITHOUT reading the
raw file. Tokens are deterministic, so tokenizing the known value with the same
handler key yields exactly the token that sits in the protected dataset; you
then match that token instead of grepping plaintext.

Usage:
    python tokenize_value.py --key "<handler-key>" --type EMPNO --value E0007
    # -> [[EMPNO:1a2b3c4d]]   then grep that token in protected.json

Valid types: EMPNO, NAME, RRN, SALARY, LATE, ABSENCE, LEAVE, PHONE, EMAIL, ACCOUNT
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crypto_core  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Print the token for a known value.")
    p.add_argument("--key", required=True, help="Handler's secret key")
    p.add_argument("--type", dest="field_type", required=True, help="Token type, e.g. EMPNO")
    p.add_argument("--value", required=True, help="The known value to tokenize")
    args = p.parse_args()
    print(crypto_core.make_token(args.key, args.field_type.upper(), args.value))


if __name__ == "__main__":
    main()
