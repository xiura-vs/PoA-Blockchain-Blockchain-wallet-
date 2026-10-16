"""
node.py - a full node: blockchain + mempool + p2p, with independent validation
of everything received. (Step 4 adds the PoA proposer loop to this class.)
"""

import threading
import time

from block import Block
from blockchain import Blockchain
from config import VALIDATORS
from mempool import Mempool
from p2p import P2P
from transaction import Transaction

_print_lock = threading.Lock()
_NAMES = {v["addr"]: v["name"] for v in VALIDATORS}


from collections import deque

EVENTS = {}          # node name -> recent log entries, read by the dashboard
_seq = 0


def log(name, text):
    global _seq
    stamp = time.strftime("%H:%M:%S")
    with _print_lock:
        _seq += 1
        EVENTS.setdefault(name, deque(maxlen=400)).append(
            {"seq": _seq, "t": stamp, "ms": time.time(), "text": text})
        print(f"[{stamp}] {name:>4} | {text}", flush=True)


def events_since(name, since):
    with _print_lock:
        return [e for e in EVENTS.get(name, ()) if e["seq"] > since]


class Node:
    SYNC_BATCH = 50

    def __init__(self, name, port, peer_ports, validator=None):
        self.name = name
        self.validator = validator            # dict with "priv"/"addr" if this node is a validator
        self.bc = Blockchain()
        self.mempool = Mempool()
        self.lock = threading.RLock()         # guards chain + mempool together
        self.net = P2P(name, port, peer_ports, self.on_message, self.on_peer_connect)
        self._warned_genesis = set()

    # ---- lifecycle ---------------------------------------------------------
    def start(self):
        self.net.start()
        threading.Thread(target=self._status_loop, daemon=True).start()
        log(self.name, f"node started on port {self.net.port} (genesis {self.bc.genesis.hash()[:8]})")

    def stop(self):
        self.net.stop()

    def _hello_data(self):
        with self.lock:
            return {"height": self.bc.height, "genesis": self.bc.genesis.hash()}

    def _status_loop(self):
        while self.net.running:
            time.sleep(3)
            self.net.broadcast("hello", self._hello_data(), gossip=False)

    def on_peer_connect(self, addr):
        self.net.broadcast("hello", self._hello_data(), gossip=False)

    # ---- local actions (wallet / proposer call these) ---------------------
    def submit_tx(self, tx):
        with self.lock:
            ok, reason = self.mempool.add(tx, self.bc.state)
            pool = len(self.mempool)
        if ok:
            log(self.name, f"tx {tx.tx_id()[:8]} submitted locally -> mempool ({pool}), gossiping")
            self.net.broadcast("tx", tx.to_dict())
        else:
            log(self.name, f"tx {tx.tx_id()[:8]} REJECTED locally: {reason}")
        return ok, reason

    def publish_block(self, blk):
        """Commit a block we produced ourselves, then gossip it."""
        with self.lock:
            ok, reason = self.bc.add_block(blk)
            if ok:
                self.mempool.remove_confirmed(blk, self.bc.state)
        if ok:
            log(self.name, f"own block #{blk.height} {blk.hash()[:8]} committed, broadcasting")
            self.net.broadcast("block", blk.to_dict())
        else:
            log(self.name, f"own block rejected: {reason}")
        return ok, reason

    def status(self):
        with self.lock:
            return {"name": self.name, "height": self.bc.height,
                    "tip": self.bc.tip.hash()[:8], "state": self.bc.state.root()[:8],
                    "mempool": len(self.mempool), "peers": self.net.connected()}

    # ---- incoming messages -------------------------------------------------
    def on_message(self, msg):
        """Returns True if a gossip message was valid (so P2P relays it)."""
        t, data, sender = msg["type"], msg.get("data"), msg.get("from")
        if t == "tx":
            return self._on_tx(data)
        if t == "block":
            return self._on_block(data, sender)
        if t == "hello":
            return self._on_hello(data, sender)
        if t == "get_blocks":
            return self._on_get_blocks(data, sender)
        if t == "blocks":
            return self._on_blocks(data, sender)
        return False

    def _on_tx(self, data):
        try:
            tx = Transaction.from_dict(data)
        except (ValueError, TypeError) as e:
            log(self.name, f"malformed tx from network: {e}")
            return False
        with self.lock:
            ok, reason = self.mempool.add(tx, self.bc.state)
            pool = len(self.mempool)
        if ok:
            log(self.name, f"tx {tx.tx_id()[:8]} validated (sig, nonce, balance) -> mempool ({pool}), relaying")
        elif reason != "duplicate":
            log(self.name, f"tx {tx.tx_id()[:8]} REJECTED: {reason}")
        return ok

    def _on_block(self, data, sender):
        try:
            blk = Block.from_dict(data)
            bh = blk.hash()
        except (ValueError, TypeError) as e:
            log(self.name, f"malformed block from network: {e}")
            return False
        if type(blk.height) is not int:
            log(self.name, "block REJECTED: malformed height")
            return False

        with self.lock:
            if 0 <= blk.height <= self.bc.height:
                if self.bc.chain[blk.height].hash() != bh:
                    log(self.name, f"block #{blk.height} {bh[:8]} CONFLICTS with our chain "
                                   f"(demo has no fork choice, ignored)")
                return False                  # already have it (or a conflicting one)
            ok, reason = self.bc.add_block(blk)
            if ok:
                self.mempool.remove_confirmed(blk, self.bc.state)
                root = self.bc.state.root()[:8]
            my_height = self.bc.height

        if ok:
            who = _NAMES.get(blk.proposer, blk.proposer[:8])
            log(self.name, f"block #{blk.height} {bh[:8]} from {who} ACCEPTED "
                           f"(proposer turn, signature, merkle, {len(blk.txs)} txs all valid; state {root})")
            return True
        if blk.height > my_height + 1:
            log(self.name, f"block #{blk.height} is ahead of us (we are at {my_height}), syncing")
            self.net.send_to_port(sender, "get_blocks", {"from": my_height + 1})
        else:
            log(self.name, f"block #{blk.height} {bh[:8]} REJECTED: {reason}")
        return False

    def _on_hello(self, data, sender):
        if not isinstance(data, dict):
            return False
        if data.get("genesis") != self.bc.genesis.hash():
            if sender not in self._warned_genesis:
                self._warned_genesis.add(sender)
                log(self.name, f"peer {sender} has a different genesis - incompatible, ignoring")
            return False
        h = data.get("height")
        with self.lock:
            mine = self.bc.height
        if type(h) is int and h > mine:
            self.net.send_to_port(sender, "get_blocks", {"from": mine + 1})
        return False

    def _on_get_blocks(self, data, sender):
        start = data.get("from") if isinstance(data, dict) else None
        if type(start) is not int or start < 1:
            return False
        with self.lock:
            batch = [b.to_dict() for b in self.bc.chain[start:start + self.SYNC_BATCH]]
        if batch:
            self.net.send_to_port(sender, "blocks", {"blocks": batch})
        return False

    def _on_blocks(self, data, sender):
        raw = data.get("blocks") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return False
        applied = 0
        for d in raw:
            try:
                blk = Block.from_dict(d)
            except (ValueError, TypeError):
                break
            with self.lock:
                ok, reason = self.bc.add_block(blk)     # full validation, same as live blocks
                if ok:
                    self.mempool.remove_confirmed(blk, self.bc.state)
            if not ok:
                if not reason.startswith("wrong height"):
                    log(self.name, f"sync block #{blk.height} REJECTED: {reason}")
                break
            applied += 1
            log(self.name, f"synced block #{blk.height} {blk.hash()[:8]} (fully re-validated)")
        if applied and len(raw) >= self.SYNC_BATCH:
            with self.lock:
                nxt = self.bc.height + 1
            self.net.send_to_port(sender, "get_blocks", {"from": nxt})
        return False