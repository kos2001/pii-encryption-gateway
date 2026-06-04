"""Pure-stdlib reversible protection primitives for sensitive personal data.

No third-party dependencies — works on any Python 3.8+ install, which keeps the
skill portable to whatever machine a handler happens to run it on.

Three primitives:
- derive_subkeys: turn a handler's secret key string into independent
  encryption / MAC / tokenization subkeys via PBKDF2-HMAC-SHA256.
- encrypt / decrypt: authenticated encryption (HMAC-SHA256 CTR-mode stream
  cipher with encrypt-then-MAC). A wrong key fails the MAC check and raises
  instead of returning garbage, so a mismatched handler can never reveal data.
- make_token: a *deterministic* typed placeholder for a (field_type, value)
  pair. Equal values collapse to equal tokens, which lets a downstream LLM
  reason about identity and grouping without ever seeing the real value.
"""

import base64
import hashlib
import hmac
import os
import struct
from functools import lru_cache

# Fixed application salt. The real secret is the per-handler key passed in;
# the salt only domain-separates this app's keys from other PBKDF2 uses.
_KDF_SALT = b"pii-encryption-gateway/v1"
_KDF_ITERATIONS = 200_000


@lru_cache(maxsize=64)
def derive_subkeys(handler_key: str):
    """Stretch a handler key into (enc, mac, tok) 32-byte subkeys.

    Cached because PBKDF2 at 200k iterations is deliberately slow and a single
    protect/reveal run touches the same key thousands of times.
    """
    material = hashlib.pbkdf2_hmac(
        "sha256", handler_key.encode("utf-8"), _KDF_SALT, _KDF_ITERATIONS, dklen=96
    )
    return material[0:32], material[32:64], material[64:96]


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    """HMAC-SHA256 in counter mode produces an arbitrary-length keystream."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(
            enc_key, nonce + struct.pack(">Q", counter), hashlib.sha256
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt(handler_key: str, plaintext: str) -> str:
    """Authenticated-encrypt a value. Output is urlsafe-base64(nonce|ct|tag)."""
    enc_key, mac_key, _ = derive_subkeys(handler_key)
    nonce = os.urandom(16)
    pt = plaintext.encode("utf-8")
    ks = _keystream(enc_key, nonce, len(pt))
    ct = bytes(a ^ b for a, b in zip(pt, ks))
    tag = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + ct + tag).decode("ascii")


def decrypt(handler_key: str, blob: str) -> str:
    """Verify and decrypt. Raises ValueError on wrong key or tampering."""
    enc_key, mac_key, _ = derive_subkeys(handler_key)
    raw = base64.urlsafe_b64decode(blob.encode("ascii"))
    nonce, ct, tag = raw[:16], raw[16:-32], raw[-32:]
    expected = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("authentication failed: wrong handler key or tampered vault")
    ks = _keystream(enc_key, nonce, len(ct))
    pt = bytes(a ^ b for a, b in zip(ct, ks))
    return pt.decode("utf-8")


def make_token(handler_key: str, field_type: str, value: str) -> str:
    """Deterministic placeholder for a value, e.g. [[SALARY:3f9a2c1d]].

    Keyed by the handler so the same value yields different tokens for
    different handlers — preventing cross-handler correlation of protected
    payloads — while staying stable within one handler's dataset.
    """
    _, _, tok_key = derive_subkeys(handler_key)
    normalized = str(value).strip()
    digest = hmac.new(
        tok_key, (field_type + "\x00" + normalized).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"[[{field_type}:{digest[:8]}]]"
