"""
state.py - account-based world state: {address: {balance, nonce}}.

The state is *derived* from the chain by replaying blocks. Nodes never trust a
peer's claimed balances; they compute their own.
"""

from crypto_utils import hash_obj


class State:
    def __init__(self, balances=None):
        self.accounts = {}
        for addr, bal in (balances or {}).items():
            self.accounts[addr] = {"balance": bal, "nonce": 0}

    def balance(self, addr) -> int:
        return self.accounts.get(addr, {}).get("balance", 0)

    def nonce(self, addr) -> int:
        """Next expected nonce for this account."""
        return self.accounts.get(addr, {}).get("nonce", 0)

    def copy(self):
        s = State()
        s.accounts = {a: dict(v) for a, v in self.accounts.items()}
        return s

    def check_tx(self, tx):
        """Full validity of a tx against THIS state. Returns (ok, reason)."""
        ok, reason = tx.check_stateless()
        if not ok:
            return False, reason
        expected = self.nonce(tx.sender)
        if tx.nonce != expected:
            return False, f"bad nonce (expected {expected}, got {tx.nonce})"
        if self.balance(tx.sender) < tx.amount:
            return False, f"insufficient balance ({self.balance(tx.sender)} < {tx.amount})"
        return True, "ok"

    def apply_tx(self, tx):
        """Mutates state. Caller MUST have called check_tx first."""
        s = self.accounts.setdefault(tx.sender, {"balance": 0, "nonce": 0})
        s["balance"] -= tx.amount
        s["nonce"] += 1
        r = self.accounts.setdefault(tx.to, {"balance": 0, "nonce": 0})
        r["balance"] += tx.amount

    def try_apply(self, txs):
        """
        Apply a list of txs atomically: all-or-nothing.
        Returns (new_state, "ok") or (None, reason). Original state untouched.
        """
        new = self.copy()
        for tx in txs:
            ok, reason = new.check_tx(tx)
            if not ok:
                return None, f"tx {tx.tx_id()[:8]}: {reason}"
            new.apply_tx(tx)
        return new, "ok"

    def root(self) -> str:
        """Fingerprint of the whole state. Handy in the demo: all nodes must show the same one."""
        return hash_obj(sorted(self.accounts.items()))