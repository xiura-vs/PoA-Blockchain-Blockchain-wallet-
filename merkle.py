"""
merkle.py - Merkle root over transaction IDs.

Lets a light client later prove "tx X is in block B" with ~log2(n) hashes
without downloading the whole block. Here we just compute the root.
"""

from typing import List
from crypto_utils import sha256_hex


def merkle_root(tx_ids: List[str]) -> str:
    # Empty block: well-defined constant (hash of empty string).
    if not tx_ids:
        return sha256_hex(b"")

    # Domain separation: 0x00 prefix for leaves, 0x01 for inner nodes.
    # Prevents a leaf from being confused with an inner node (2nd-preimage attack).
    level = [sha256_hex(b"\x00" + bytes.fromhex(t)) for t in tx_ids]

    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(
                    sha256_hex(b"\x01" + bytes.fromhex(level[i]) + bytes.fromhex(level[i + 1]))
                )
            else:
                # Odd node is promoted unchanged. (Bitcoin duplicates it, which
                # allowed a real vulnerability, CVE-2012-2459. Promotion avoids it.)
                nxt.append(level[i])
        level = nxt
    return level[0]