"""
block.py - block = header + transactions + validator signature.

block hash = SHA-256(header). The header commits to the transactions through the
Merkle root, and to history through prev_hash. The validator signs the block hash.
"""

from crypto_utils import hash_obj, sign, verify
from merkle import merkle_root
from transaction import Transaction


class Block:
    def __init__(self, height, prev_hash, timestamp, slot, proposer, txs,
                 merkle_root_hex=None, signature=""):
        self.height = height
        self.prev_hash = prev_hash
        self.timestamp = timestamp
        self.slot = slot
        self.proposer = proposer          # validator ADDRESS
        self.txs = txs                    # list[Transaction]
        # If given (e.g. received from the network) we keep it as-is so that
        # validation can detect a mismatch. If not, compute it.
        self.merkle_root = merkle_root_hex or self.compute_merkle_root()
        self.signature = signature

    def compute_merkle_root(self) -> str:
        return merkle_root([t.tx_id() for t in self.txs])

    def header(self) -> dict:
        return {
            "height": self.height,
            "prev_hash": self.prev_hash,
            "merkle_root": self.merkle_root,
            "timestamp": self.timestamp,
            "slot": self.slot,
            "proposer": self.proposer,
        }

    def hash(self) -> str:
        return hash_obj(self.header())

    def sign(self, private_key_hex: str):
        self.signature = sign(private_key_hex, self.hash().encode())

    def verify_signature(self, public_key_hex: str) -> bool:
        return verify(public_key_hex, self.signature, self.hash().encode())

    def to_dict(self) -> dict:
        return {
            "header": self.header(),
            "hash": self.hash(),
            "signature": self.signature,
            "txs": [t.to_dict() for t in self.txs],
        }

    @classmethod
    def from_dict(cls, d: dict):
        try:
            h = d["header"]
            return cls(
                h["height"], h["prev_hash"], h["timestamp"], h["slot"], h["proposer"],
                [Transaction.from_dict(t) for t in d["txs"]],
                merkle_root_hex=h["merkle_root"],
                signature=d.get("signature", ""),
            )
        except (KeyError, TypeError, AttributeError) as e:
            raise ValueError(f"malformed block: {e}")

    def __repr__(self):
        return f"Block(#{self.height} {self.hash()[:8]}.. slot={self.slot} txs={len(self.txs)})"