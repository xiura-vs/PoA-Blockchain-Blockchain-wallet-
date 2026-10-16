"""
bip32.py - hierarchical deterministic (HD) key derivation (BIP-32).

One seed -> a tree of private keys. A path like m/44'/60'/0'/0/1 names one
branch. An apostrophe means "hardened": the child can't be computed from the
parent's PUBLIC key, so leaking a child key never exposes its siblings.
"""

import hashlib
import hmac

from ecdsa import SigningKey, SECP256k1

N = SECP256k1.order
HARDENED = 0x80000000
HD_PATH = "m/44'/60'/0'/0/{}"      # the path MetaMask uses; {} = account index


def _compressed_pub(k: int) -> bytes:
    sk = SigningKey.from_string(k.to_bytes(32, "big"), curve=SECP256k1)
    return sk.get_verifying_key().to_string("compressed")


def master_key(seed: bytes):
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    k = int.from_bytes(I[:32], "big")
    if k == 0 or k >= N:
        raise ValueError("invalid master key (astronomically unlikely)")
    return k, I[32:]


def child_key(k: int, chain: bytes, index: int):
    if index >= HARDENED:
        data = b"\x00" + k.to_bytes(32, "big") + index.to_bytes(4, "big")
    else:
        data = _compressed_pub(k) + index.to_bytes(4, "big")
    I = hmac.new(chain, data, hashlib.sha512).digest()
    il = int.from_bytes(I[:32], "big")
    child = (il + k) % N
    if il >= N or child == 0:
        raise ValueError("invalid child key (astronomically unlikely)")
    return child, I[32:]


def parse_path(path: str):
    parts = path.split("/")
    if parts[0] != "m":
        raise ValueError("path must start with 'm'")
    out = []
    for p in parts[1:]:
        hard = p.endswith("'")
        n = int(p[:-1] if hard else p)
        if not 0 <= n < HARDENED:
            raise ValueError("bad path index")
        out.append(n + HARDENED if hard else n)
    return out


def derive_private_key(seed: bytes, path: str) -> str:
    """Returns the 32-byte private key as 64 hex chars (what crypto_utils expects)."""
    k, c = master_key(seed)
    for idx in parse_path(path):
        k, c = child_key(k, c, idx)
    return k.to_bytes(32, "big").hex()


def account_private_key(seed: bytes, index: int) -> str:
    return derive_private_key(seed, HD_PATH.format(index))