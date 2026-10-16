"""
bip39.py - Secret Recovery Phrase (BIP-39), stdlib only.

entropy (128 bits) + checksum (first 4 bits of SHA-256) = 132 bits
132 bits / 11 = 12 words, each word indexes a 2048-word list.
The checksum lets us detect a mistyped phrase before it creates a wrong wallet.
"""

import hashlib
import os
import secrets
import unicodedata

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wordlist_english.txt")
with open(_PATH, encoding="utf-8") as _f:
    WORDS = _f.read().split()
if len(WORDS) != 2048:
    raise RuntimeError(f"wordlist must have 2048 words, found {len(WORDS)}")
INDEX = {w: i for i, w in enumerate(WORDS)}

VALID_WORD_COUNTS = (12, 15, 18, 21, 24)


def normalize(mnemonic: str) -> str:
    """Lowercase, collapse whitespace, Unicode NFKD (as the spec requires)."""
    return " ".join(unicodedata.normalize("NFKD", mnemonic).lower().split())


def entropy_to_mnemonic(entropy: bytes) -> str:
    if len(entropy) not in (16, 20, 24, 28, 32):
        raise ValueError("entropy must be 16, 20, 24, 28 or 32 bytes")
    cs_bits = len(entropy) * 8 // 32
    bits = bin(int.from_bytes(entropy, "big"))[2:].zfill(len(entropy) * 8)
    bits += bin(hashlib.sha256(entropy).digest()[0])[2:].zfill(8)[:cs_bits]
    return " ".join(WORDS[int(bits[i:i + 11], 2)] for i in range(0, len(bits), 11))


def generate_mnemonic(words: int = 12) -> str:
    if words not in VALID_WORD_COUNTS:
        raise ValueError("word count must be one of 12, 15, 18, 21, 24")
    return entropy_to_mnemonic(secrets.token_bytes(words * 4 // 3))   # OS randomness


def mnemonic_to_entropy(mnemonic: str) -> bytes:
    """Validates word count, dictionary membership and checksum. Raises ValueError."""
    words = normalize(mnemonic).split()
    if len(words) not in VALID_WORD_COUNTS:
        raise ValueError(f"recovery phrase must have 12, 15, 18, 21 or 24 words (got {len(words)})")
    bad = [w for w in words if w not in INDEX]
    if bad:
        raise ValueError(f"not in the word list: {', '.join(bad[:3])}")
    bits = "".join(bin(INDEX[w])[2:].zfill(11) for w in words)
    cs_bits = len(bits) // 33
    ent_bits, checksum = bits[:-cs_bits], bits[-cs_bits:]
    entropy = int(ent_bits, 2).to_bytes(len(ent_bits) // 8, "big")
    expected = bin(hashlib.sha256(entropy).digest()[0])[2:].zfill(8)[:cs_bits]
    if checksum != expected:
        raise ValueError("invalid recovery phrase (checksum mismatch - a word is wrong or out of order)")
    return entropy


def is_valid(mnemonic: str) -> bool:
    try:
        mnemonic_to_entropy(mnemonic)
        return True
    except ValueError:
        return False


def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    """64-byte master seed. PBKDF2 makes brute-forcing a phrase slower."""
    m = unicodedata.normalize("NFKD", normalize(mnemonic)).encode()
    salt = ("mnemonic" + unicodedata.normalize("NFKD", passphrase)).encode()
    return hashlib.pbkdf2_hmac("sha512", m, salt, 2048, 64)