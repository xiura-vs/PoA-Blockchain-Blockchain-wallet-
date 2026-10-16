"""
transaction.py - signed, nonce-based account transfer.

Fields: from (address), pubkey, to (address), amount, nonce, chain_id, signature.
tx_id = SHA-256 of everything EXCEPT the signature.
"""

import re

from config import CHAIN_ID
from crypto_utils import (
    hash_obj, sign, verify, canonical_bytes,
    public_key_from_private, public_key_to_address,
)

ADDR_RE = re.compile(r"PC[0-9a-f]{40}")
MAX_AMOUNT = 2**63 - 1


class Transaction:
    def __init__(self, sender, pubkey, to, amount, nonce, signature="", chain_id=CHAIN_ID):
        self.sender = sender
        self.pubkey = pubkey
        self.to = to
        self.amount = amount
        self.nonce = nonce
        self.signature = signature
        self.chain_id = chain_id

    # ---- identity / signing ------------------------------------------------
    def payload(self) -> dict:
        """The exact data that is hashed and signed (no signature in it)."""
        return {
            "chain_id": self.chain_id,
            "from": self.sender,
            "pubkey": self.pubkey,
            "to": self.to,
            "amount": self.amount,
            "nonce": self.nonce,
        }

    def tx_id(self) -> str:
        return hash_obj(self.payload())

    def sign(self, private_key_hex: str):
        self.signature = sign(private_key_hex, self.tx_id().encode())

    @classmethod
    def create(cls, private_key_hex, to, amount, nonce):
        """Convenience: build and sign a transaction from a private key."""
        pub = public_key_from_private(private_key_hex)
        tx = cls(public_key_to_address(pub), pub, to, amount, nonce)
        tx.sign(private_key_hex)
        return tx

    # ---- validation that needs NO chain state ------------------------------
    def check_stateless(self):
        """Returns (ok, reason). Safe against garbage from the network."""
        try:
            if self.chain_id != CHAIN_ID:
                return False, "wrong chain id"
            for f in (self.sender, self.to, self.pubkey, self.signature):
                if not isinstance(f, str):
                    return False, "malformed field type"
            if not ADDR_RE.fullmatch(self.to):
                return False, "invalid recipient address"
            if type(self.amount) is not int or not (0 < self.amount <= MAX_AMOUNT):
                return False, "invalid amount"
            if type(self.nonce) is not int or self.nonce < 0:
                return False, "invalid nonce"
            if public_key_to_address(self.pubkey) != self.sender:
                return False, "pubkey does not match sender address"
            if not verify(self.pubkey, self.signature, self.tx_id().encode()):
                return False, "bad tx signature"
            return True, "ok"
        except Exception as e:  # never crash on untrusted input
            return False, f"malformed tx ({type(e).__name__})"

    # ---- (de)serialization for the network --------------------------------
    def to_dict(self) -> dict:
        d = self.payload()
        d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, d: dict):
        try:
            return cls(
                d["from"], d["pubkey"], d["to"], d["amount"], d["nonce"],
                d.get("signature", ""), d.get("chain_id", CHAIN_ID),
            )
        except (KeyError, TypeError, AttributeError) as e:
            raise ValueError(f"malformed transaction: {e}")

    def __repr__(self):
        return f"Tx({self.tx_id()[:8]}.. {self.sender[:8]}..->{self.to[:8]}.. amt={self.amount} n={self.nonce})"