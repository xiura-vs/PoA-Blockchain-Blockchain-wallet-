"""
consensus.py - Proof of Authority engine (Aura-style round-robin by time slot).

PoANode = Node + a proposer loop. Only nodes started with a `validator`
(name/priv/addr) propose; every node, validator or not, still independently
validates everything it receives (that logic lives in Node/Blockchain).
"""

import threading
import time

from blockchain import Blockchain
from config import GENESIS_TIME, BLOCK_TIME
from node import Node, log

PEER_HEIGHT_TTL = 10      # seconds a peer's claimed height is considered fresh


class PoANode(Node):
    SLOT_LOG = True       # print one line per slot ("V2's turn"); handy for demos

    def __init__(self, name, port, peer_ports, validator=None):
        super().__init__(name, port, peer_ports, validator)
        self.peer_heights = {}            # peer port -> (height, time seen)
        self._empty_logged_slot = -1
        self._attempted_slot = -1

    # ---- lifecycle ---------------------------------------------------------
    def start(self):
        super().start()
        if self.validator:
            log(self.name, f"validator engine ON (address {self.validator['addr'][:10]}..)")
            threading.Thread(target=self._engine_loop, daemon=True).start()

    # ---- helpers -----------------------------------------------------------
    def next_nonce(self, addr):
        """Confirmed nonce + number of this sender's txs already pending."""
        with self.lock:
            return self.bc.state.nonce(addr) + sum(
                1 for t in self.mempool.txs.values() if t.sender == addr)

    def _on_hello(self, data, sender):
        if (isinstance(data, dict) and type(data.get("height")) is int
                and data.get("genesis") == self.bc.genesis.hash()):
            self.peer_heights[sender] = (data["height"], time.time())
        return super()._on_hello(data, sender)

    def _behind_peers(self):
        """True if a recently-heard peer has a taller chain: we should sync, not propose."""
        cutoff = time.time() - PEER_HEIGHT_TTL
        with self.lock:
            mine = self.bc.height
        return any(h > mine and seen > cutoff
                   for h, seen in list(self.peer_heights.values()))

    # ---- the PoA loop ------------------------------------------------------
    def _engine_loop(self):
        last_logged = -1
        while self.net.running:
            time.sleep(0.2)
            slot = Blockchain.slot_for_time(int(time.time()))
            who = Blockchain.proposer_for_slot(slot)
            mine = who["addr"] == self.validator["addr"]

            if slot != last_logged:
                last_logged = slot
                if self.SLOT_LOG:
                    log(self.name, f"slot {slot}: {who['name']}'s turn" + ("  <-- ME" if mine else ""))
            if mine:
                self._try_propose(slot)

    def _try_propose(self, slot):
        if self._attempted_slot == slot or self._behind_peers():
            return
        ts = GENESIS_TIME + slot * BLOCK_TIME     # slot start time

        with self.lock:
            if slot <= self.bc.tip.slot:
                return                             # this slot (or a later one) already has a block
            pending = self.mempool.get_pending()
            if not pending:
                if self._empty_logged_slot != slot:
                    self._empty_logged_slot = slot
                    log(self.name, f"slot {slot} is mine but mempool is empty -> skipping (no empty blocks)")
                return
            blk = self.bc.create_block(self.validator["priv"], pending, ts)

        if not blk.txs:
            return                                 # nothing valid to include
        self._attempted_slot = slot                # one attempt per slot

        log(self.name, f"slot {slot} is MINE -> pulled {len(pending)} tx(s) from mempool, "
                       f"{len(blk.txs)} valid")
        log(self.name, f"built block #{blk.height}: merkle root {blk.merkle_root[:8]}, "
                       f"signed with {self.name}'s private key (sig {blk.signature[:8]}..)")
        self.publish_block(blk)