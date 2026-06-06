"""Keyless de-identification token (lightweight model).

The keyed gateway (crypto_core) encrypts originals into a vault so only the
handler key can restore them. This module is the opposite trade-off: NO key,
NO encryption — a direct identifier becomes a deterministic content-hash token
and the original is kept in a PLAINTEXT map. The only thing it buys is that the
LLM's working copy holds tokens instead of raw identifiers; reversibility is via
the plaintext map, not a key. Use when the goal is simply "don't put raw
identifiers in the model's context" AND numeric attributes must stay raw for
analysis (averages, sums) — see deidentify.py.

Deterministic so equal values collapse to equal tokens (grouping still works).
Stdlib only.
"""

import hashlib

_DOMAIN = b"pii-deidentify/v1"  # domain-separates these tokens from any other hash use


def token(field_type: str, value: str) -> str:
    """Deterministic, keyless placeholder, e.g. [[NAME:3f9a2c1d]].

    Keyed only by field_type + value (no secret), so the same value always maps
    to the same token within and across runs. Type-scoped so the same string
    under two field types yields different tokens.
    """
    normalized = str(value).strip()
    digest = hashlib.sha256(
        _DOMAIN + (field_type + "\x00" + normalized).encode("utf-8")
    ).hexdigest()
    return f"[[{field_type}:{digest[:8]}]]"
