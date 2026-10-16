"""
crypto_utils.py
Cryptographic primitives for the PoA demo chain.

- SHA-256 hashing
- Canonical (deterministic) serialization, so every node hashes identical bytes
- ECDSA keypairs on secp256k1 (same curve as Bitcoin/Ethereum)
- Sign / verify
- Address derivation from public key
"""

import hashlib
import json
from typing import Tuple

from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError

ADDRESS_PREFIX = "PC"  # "PoA Coin" - purely cosmetic, makes addresses recognizable


# ----------------------------------------------------------------------------
# Hashing & serialization
# ----------------------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    """SHA-256 of raw bytes, returned as a 64-char hex string."""
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(obj) -> bytes:
    """
    Deterministic JSON encoding: sorted keys, no whitespace, UTF-8.

    WHY: Two nodes must produce byte-identical output for the same logical
    object, otherwise they compute different hashes and reject each other's
    data. Python dicts preserve insertion order, so we sort explicitly.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_obj(obj) -> str:
    """SHA-256 of the canonical encoding of any JSON-serializable object."""
    return sha256_hex(canonical_bytes(obj))


# ----------------------------------------------------------------------------
# Keys
# ----------------------------------------------------------------------------

def generate_keypair() -> Tuple[str, str]:
    """
    Create a new ECDSA (secp256k1) keypair.
    Returns (private_key_hex, public_key_hex).
      - private key: 32 bytes -> 64 hex chars
      - public key : 64 bytes (raw X||Y) -> 128 hex chars
    """
    sk = SigningKey.generate(curve=SECP256k1)
    vk = sk.get_verifying_key()
    return sk.to_string().hex(), vk.to_string().hex()


def public_key_from_private(private_key_hex: str) -> str:
    sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    return sk.get_verifying_key().to_string().hex()


def public_key_to_address(public_key_hex: str) -> str:
    """
    Address = PREFIX + first 40 hex chars (20 bytes) of SHA-256(public key).

    WHY hash the key: shorter to type/display, and hides the public key
    until the owner actually spends (a small extra layer of protection).
    Bitcoin/Ethereum do the same idea (with RIPEMD-160 / Keccak-256).
    """
    digest = sha256_hex(bytes.fromhex(public_key_hex))
    return ADDRESS_PREFIX + digest[:40]


def private_key_to_address(private_key_hex: str) -> str:
    return public_key_to_address(public_key_from_private(private_key_hex))


# ----------------------------------------------------------------------------
# Sign / verify
# ----------------------------------------------------------------------------

def sign(private_key_hex: str, message: bytes) -> str:
    """
    ECDSA-sign `message` (SHA-256 is applied internally).
    Uses deterministic nonces (RFC 6979): same key + message -> same signature,
    and avoids the classic ECDSA disaster of a weak/reused random nonce.
    Returns 64-byte signature (r||s) as 128 hex chars.
    """
    sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    sig = sk.sign_deterministic(message, hashfunc=hashlib.sha256)
    return sig.hex()


def verify(public_key_hex: str, signature_hex: str, message: bytes) -> bool:
    """
    Verify an ECDSA signature. Never raises: any malformed input -> False.
    (Nodes receive untrusted data from the network; a bad packet must not crash us.)
    """
    try:
        vk = VerifyingKey.from_string(bytes.fromhex(public_key_hex), curve=SECP256k1)
        return vk.verify(
            bytes.fromhex(signature_hex), message, hashfunc=hashlib.sha256
        )
    except (BadSignatureError, ValueError, AssertionError, Exception):
        return False


# ----------------------------------------------------------------------------
# Quick self-demo:  python crypto_utils.py
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    priv, pub = generate_keypair()
    addr = public_key_to_address(pub)
    print("private :", priv)
    print("public  :", pub[:32] + "...")
    print("address :", addr)

    msg = canonical_bytes({"to": "PCabc", "amount": 5, "nonce": 0})
    sig = sign(priv, msg)
    print("sig     :", sig[:32] + "...")
    print("valid   :", verify(pub, sig, msg))
    print("tampered:", verify(pub, sig, msg + b"x"))