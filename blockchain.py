"""
blockchain.py - the chain, genesis block, and ALL block validation rules.

Every node runs validate_block() on every block it receives. A block is only
accepted if EVERY rule passes; nobody is trusted, including validators.
"""

import time

from config import (
    CHAIN_ID, BLOCK_TIME, GENESIS_TIME, MAX_FUTURE_DRIFT, MAX_TXS_PER_BLOCK,
    VALIDATORS, GENESIS_ALLOC,
)
from crypto_utils import hash_obj, public_key_from_private, public_key_to_address
from block import Block
from state import State


def make_genesis() -> Block:
    # prev_hash commits to the chain config, so nodes with different chain IDs
    # or different premine get a different genesis hash and can't talk to each other.
    prev = hash_obj({"chain_id": CHAIN_ID, "alloc": sorted(GENESIS_ALLOC.items())})
    return Block(0, prev, GENESIS_TIME, 0, "GENESIS", [], signature="")


class Blockchain:
    def __init__(self):
        self.genesis = make_genesis()
        self.chain = [self.genesis]
        self.state = State(GENESIS_ALLOC)
        self._validators_by_addr = {v["addr"]: v for v in VALIDATORS}

    # ---- accessors ---------------------------------------------------------
    @property
    def tip(self) -> Block:
        return self.chain[-1]

    @property
    def height(self) -> int:
        return self.tip.height

    # ---- PoA schedule ------------------------------------------------------
    @staticmethod
    def slot_for_time(ts: int) -> int:
        return (ts - GENESIS_TIME) // BLOCK_TIME

    @staticmethod
    def proposer_for_slot(slot: int) -> dict:
        """Round-robin: slot 1 -> V2, slot 2 -> V3, slot 3 -> V1, ..."""
        return VALIDATORS[slot % len(VALIDATORS)]

    # ---- block production (used by a validator) ---------------------------
    def create_block(self, proposer_priv, txs, timestamp, filter_invalid=True) -> Block:
        """
        Assemble + sign a block on top of the current tip.
        filter_invalid=True drops txs that don't apply cleanly (what an honest
        validator does). Tests set it False to craft deliberately bad blocks.
        """
        pub = public_key_from_private(proposer_priv)
        addr = public_key_to_address(pub)

        if filter_invalid:
            sim, chosen = self.state.copy(), []
            for tx in txs:
                if len(chosen) >= MAX_TXS_PER_BLOCK:
                    break
                ok, _ = sim.check_tx(tx)
                if ok:
                    sim.apply_tx(tx)
                    chosen.append(tx)
        else:
            chosen = list(txs)

        blk = Block(
            height=self.tip.height + 1,
            prev_hash=self.tip.hash(),
            timestamp=timestamp,
            slot=self.slot_for_time(timestamp),
            proposer=addr,
            txs=chosen,
        )
        blk.sign(proposer_priv)
        return blk

    # ---- validation --------------------------------------------------------
    def _validate(self, block: Block, now=None):
        """Returns (new_state, 'ok') or (None, reason). Does not mutate the chain."""
        try:
            now = time.time() if now is None else now
            tip = self.tip

            # 1. Links to our tip
            if block.height != tip.height + 1:
                return None, f"wrong height (expected {tip.height + 1}, got {block.height})"
            if block.prev_hash != tip.hash():
                return None, "prev_hash does not match our chain tip"

            # 2. Timing / slot
            if type(block.timestamp) is not int or type(block.slot) is not int:
                return None, "malformed timestamp/slot"
            if block.slot != self.slot_for_time(block.timestamp):
                return None, "slot does not match timestamp"
            if block.slot <= tip.slot:
                return None, "slot not after parent's slot"
            if block.timestamp > now + MAX_FUTURE_DRIFT:
                return None, "block timestamp too far in the future"

            # 3. PoA: right validator for this slot?
            expected = self.proposer_for_slot(block.slot)
            if block.proposer != expected["addr"]:
                return None, f"not this validator's slot (slot {block.slot} belongs to {expected['name']})"

            # 4. Validator signature
            if not block.verify_signature(expected["pub"]):
                return None, "bad validator signature"

            # 5. Body integrity
            if len(block.txs) > MAX_TXS_PER_BLOCK:
                return None, "too many transactions"
            if block.merkle_root != block.compute_merkle_root():
                return None, "merkle root mismatch (transactions were altered)"

            # 6. Every transaction valid, applied in order
            new_state, reason = self.state.try_apply(block.txs)
            if new_state is None:
                return None, reason
            return new_state, "ok"
        except Exception as e:
            return None, f"malformed block ({type(e).__name__}: {e})"

    def validate_block(self, block: Block, now=None):
        ns, reason = self._validate(block, now)
        return ns is not None, reason

    def add_block(self, block: Block, now=None):
        """Validate, then commit. Returns (ok, reason)."""
        new_state, reason = self._validate(block, now)
        if new_state is None:
            return False, reason
        self.chain.append(block)
        self.state = new_state
        return True, "ok"

    # ---- rebuild from a list of blocks (used for peer sync later) ---------
    @classmethod
    def from_blocks(cls, blocks):
        bc = cls()
        if not blocks or blocks[0].hash() != bc.genesis.hash():
            return None, "genesis mismatch"
        for b in blocks[1:]:
            # Historical replay: judge the block as of its own timestamp.
            ok, reason = bc.add_block(b, now=b.timestamp)
            if not ok:
                return None, f"block #{b.height}: {reason}"
        return bc, "ok"