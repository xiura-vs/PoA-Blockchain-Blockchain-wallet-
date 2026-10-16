import json
from config import VALIDATORS, USERS, GENESIS_TIME, BLOCK_TIME
from block import Block
from blockchain import Blockchain
from merkle import merkle_root
from transaction import Transaction
from crypto_utils import public_key_to_address

alice, bob, carol = USERS["alice"], USERS["bob"], USERS["carol"]


def ts(slot):
    return GENESIS_TIME + slot * BLOCK_TIME


def prod(slot):
    """The validator whose turn it is in this slot."""
    return Blockchain.proposer_for_slot(slot)


def pay(frm, to, amt, nonce):
    return Transaction.create(frm["priv"], to["addr"], amt, nonce)


def expect_reject(bc, blk, fragment, now):
    ok, reason = bc.add_block(blk, now=now)
    assert not ok, "block should have been rejected!"
    assert fragment in reason, f"expected '{fragment}' in '{reason}'"
    print(f"   rejected as expected -> {reason}")


def test_merkle():
    a, b, c = "aa" * 32, "bb" * 32, "cc" * 32
    assert merkle_root([a, b]) != merkle_root([b, a])          # order matters
    assert merkle_root([a, b, c]) != merkle_root([a, b])       # content matters
    assert merkle_root([]) == merkle_root([])                  # deterministic
    assert len(merkle_root([a])) == 64


def test_happy_path():
    bc = Blockchain()
    assert bc.state.balance(alice["addr"]) == 1000
    v = prod(1)
    blk = bc.create_block(v["priv"], [pay(alice, bob, 100, 0)], ts(1))
    ok, reason = bc.add_block(blk, now=ts(1))
    assert ok, reason
    assert bc.height == 1
    assert bc.state.balance(alice["addr"]) == 900
    assert bc.state.balance(bob["addr"]) == 600
    assert bc.state.nonce(alice["addr"]) == 1
    print(f"   slot 1 -> {v['name']} proposed {blk}")


def test_round_robin():
    bc = Blockchain()
    names = []
    for slot in (1, 2, 3, 4):
        v = prod(slot)
        blk = bc.create_block(v["priv"], [pay(alice, bob, 1, slot - 1)], ts(slot))
        ok, r = bc.add_block(blk, now=ts(slot))
        assert ok, r
        names.append(v["name"])
    assert names == ["V2", "V3", "V1", "V2"], names
    print("   proposer order:", names)


def test_skipped_slot():
    """Validator for slot 1 is 'offline': chain jumps to slot 2 and still works."""
    bc = Blockchain()
    blk = bc.create_block(prod(2)["priv"], [pay(alice, bob, 5, 0)], ts(2))
    ok, r = bc.add_block(blk, now=ts(2))
    assert ok, r
    assert bc.tip.slot == 2 and bc.height == 1


def test_wrong_validator_rejected():
    bc = Blockchain()
    wrong = prod(2)                                   # slot 1 belongs to prod(1)
    blk = bc.create_block(wrong["priv"], [pay(alice, bob, 5, 0)], ts(1))
    expect_reject(bc, blk, "not this validator's slot", ts(1))


def test_forged_validator_signature_rejected():
    """Attacker claims to be the right validator but doesn't have its key."""
    bc = Blockchain()
    blk = bc.create_block(carol["priv"], [pay(alice, bob, 5, 0)], ts(1))
    blk.proposer = prod(1)["addr"]                    # lie about who proposed
    blk.sign(carol["priv"])                           # sign with the wrong key
    expect_reject(bc, blk, "bad validator signature", ts(1))


def test_tampered_tx_rejected():
    bc = Blockchain()
    blk = bc.create_block(prod(1)["priv"], [pay(alice, bob, 10, 0)], ts(1))
    blk.txs[0].amount = 999                           # change amount after signing
    expect_reject(bc, blk, "merkle root mismatch", ts(1))


def test_tampered_tx_with_fixed_merkle_rejected():
    """Smarter attacker also fixes the merkle root, but can't re-sign as validator."""
    bc = Blockchain()
    blk = bc.create_block(prod(1)["priv"], [pay(alice, bob, 10, 0)], ts(1))
    blk.txs[0].amount = 999
    blk.merkle_root = blk.compute_merkle_root()
    expect_reject(bc, blk, "bad validator signature", ts(1))


def test_forged_tx_signature_rejected():
    """Validator (or anyone) includes a tx 'from alice' signed by bob's key."""
    bc = Blockchain()
    fake = Transaction(alice["addr"], alice["pub"], bob["addr"], 50, 0)
    fake.sign(bob["priv"])
    blk = bc.create_block(prod(1)["priv"], [fake], ts(1), filter_invalid=False)
    expect_reject(bc, blk, "bad tx signature", ts(1))


def test_overspend_rejected():
    bc = Blockchain()
    blk = bc.create_block(prod(1)["priv"], [pay(alice, bob, 5000, 0)], ts(1), filter_invalid=False)
    expect_reject(bc, blk, "insufficient balance", ts(1))


def test_replay_rejected():
    bc = Blockchain()
    tx = pay(alice, bob, 10, 0)
    ok, r = bc.add_block(bc.create_block(prod(1)["priv"], [tx], ts(1)), now=ts(1))
    assert ok, r
    replay = bc.create_block(prod(2)["priv"], [tx], ts(2), filter_invalid=False)
    expect_reject(bc, replay, "bad nonce", ts(2))


def test_bad_prev_hash_rejected():
    bc = Blockchain()
    v = prod(1)
    blk = bc.create_block(v["priv"], [], ts(1))
    blk.prev_hash = "00" * 32
    blk.sign(v["priv"])                               # validly signed, still wrong parent
    expect_reject(bc, blk, "prev_hash", ts(1))


def test_future_block_rejected():
    bc = Blockchain()
    blk = bc.create_block(prod(100)["priv"], [], ts(100))
    expect_reject(bc, blk, "future", ts(1))


def test_serialization_roundtrip():
    bc = Blockchain()
    blk = bc.create_block(prod(1)["priv"], [pay(alice, bob, 10, 0)], ts(1))
    wire = json.dumps(blk.to_dict())                  # what would go over a socket
    blk2 = Block.from_dict(json.loads(wire))
    assert blk2.hash() == blk.hash()
    ok, r = bc.add_block(blk2, now=ts(1))
    assert ok, r


def test_full_chain_replay():
    """A fresh node re-validates the whole chain from genesis and reaches the same state."""
    bc = Blockchain()
    for slot in (1, 2, 3):
        blk = bc.create_block(prod(slot)["priv"], [pay(alice, bob, 7, slot - 1)], ts(slot))
        ok, r = bc.add_block(blk, now=ts(slot))
        assert ok, r
    fresh, reason = Blockchain.from_blocks(bc.chain)
    assert fresh is not None, reason
    assert fresh.state.root() == bc.state.root()
    assert fresh.tip.hash() == bc.tip.hash()
    print("   state root:", fresh.state.root()[:16] + "...")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)