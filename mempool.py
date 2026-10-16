"""
mempool.py - pool of valid-but-unconfirmed transactions.

Rules for admission (all checked independently by every node):
  1. stateless checks (signature, format, chain id)
  2. not a duplicate
  3. nonce must be the sender's NEXT nonce, counting txs already pending
  4. balance must cover all pending spends + this one
"""

import threading
from collections import OrderedDict

from config import MAX_TXS_PER_BLOCK

MAX_POOL = 5000


class Mempool:
    def __init__(self):
        self.txs = OrderedDict()          # tx_id -> Transaction, in arrival order
        self.lock = threading.RLock()

    def __len__(self):
        return len(self.txs)

    def __contains__(self, tx_id):
        return tx_id in self.txs

    def add(self, tx, state):
        """Returns (ok, reason). `state` is the current confirmed State."""
        with self.lock:
            ok, reason = tx.check_stateless()
            if not ok:
                return False, reason
            tid = tx.tx_id()
            if tid in self.txs:
                return False, "duplicate"
            if len(self.txs) >= MAX_POOL:
                return False, "mempool full"

            pending = [t for t in self.txs.values() if t.sender == tx.sender]
            expected = state.nonce(tx.sender) + len(pending)
            if tx.nonce != expected:
                return False, f"bad nonce (expected {expected}, got {tx.nonce})"

            committed = sum(t.amount for t in pending)
            if state.balance(tx.sender) < committed + tx.amount:
                return False, (f"insufficient balance "
                               f"({state.balance(tx.sender)} < {committed} pending + {tx.amount})")

            self.txs[tid] = tx
            return True, "ok"

    def get_pending(self, limit=MAX_TXS_PER_BLOCK):
        """Txs for the next block, oldest first (keeps per-sender nonce order)."""
        with self.lock:
            return list(self.txs.values())[:limit]

    def remove_confirmed(self, block, state):
        """
        Call after a block is committed. Removes its txs, then re-validates
        everything left against the NEW state (a block from another validator
        may have made some pending txs stale). Returns number dropped.
        """
        with self.lock:
            confirmed = {t.tx_id() for t in block.txs}
            remaining = [t for tid, t in self.txs.items() if tid not in confirmed]
            self.txs = OrderedDict()
            dropped = 0
            for t in remaining:
                ok, _ = self.add(t, state)
                if not ok:
                    dropped += 1
            return dropped