import time

from blockchain import Blockchain
from config import VALIDATORS, USERS
from node import Node, log
from transaction import Transaction

PORTS = [v["port"] for v in VALIDATORS]
alice, bob, carol = USERS["alice"], USERS["bob"], USERS["carol"]


def make(i):
    return Node(VALIDATORS[i]["name"], PORTS[i], PORTS)


def wait_until(cond, timeout=10, what=""):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for: {what}")


def wait_next_slot(node):
    target = node.bc.tip.slot
    while Blockchain.slot_for_time(int(time.time())) <= target:
        time.sleep(0.2)


def propose(node):
    """Stand-in for the PoA engine: build a block as whichever validator owns this slot."""
    now = int(time.time())
    v = Blockchain.proposer_for_slot(Blockchain.slot_for_time(now))
    with node.lock:
        blk = node.bc.create_block(v["priv"], node.mempool.get_pending(), now)
    ok, reason = node.publish_block(blk)
    assert ok, reason
    return blk


def banner(s):
    print(f"\n===== {s} =====", flush=True)


def main():
    nodes = [make(i) for i in range(3)]
    n1, n2, n3 = nodes
    for n in nodes:
        n.start()

    banner("1. Mesh forms")
    wait_until(lambda: all(n.net.connected() == 2 for n in nodes), what="full mesh")

    banner("2. Valid tx submitted at V1 gossips to everyone")
    tx = Transaction.create(alice["priv"], bob["addr"], 100, 0)
    assert n1.submit_tx(tx)[0]
    wait_until(lambda: all(tx.tx_id() in n.mempool for n in nodes), what="tx in all mempools")

    banner("3. Invalid txs are refused (locally, and independently by peers)")
    ok, _ = n2.submit_tx(Transaction.create(alice["priv"], bob["addr"], 5000, 1))   # overspend
    assert not ok
    fake = Transaction(alice["addr"], alice["pub"], bob["addr"], 50, 1)
    fake.sign(bob["priv"])                                                          # forged signature
    n1.net.broadcast("tx", fake.to_dict())      # bypass V1's own checks: attacker-style raw broadcast
    time.sleep(1.5)
    assert all(fake.tx_id() not in n.mempool for n in nodes)
    assert all(len(n.mempool) == 1 for n in nodes)

    banner("4. Block from the WRONG validator is rejected by peers")
    now = int(time.time())
    slot = Blockchain.slot_for_time(now)
    wrong = VALIDATORS[(slot + 1) % 3]
    with n1.lock:
        bad = n1.bc.create_block(wrong["priv"], [], now)
    n1.net.broadcast("block", bad.to_dict())    # raw broadcast, n1 never committed it
    time.sleep(1.5)
    assert n2.bc.height == 0 and n3.bc.height == 0

    banner("5. Correct block is accepted by every node independently")
    propose(n1)
    wait_until(lambda: all(n.bc.height == 1 for n in nodes), what="height 1 everywhere")
    assert len({n.bc.state.root() for n in nodes}) == 1
    assert all(len(n.mempool) == 0 for n in nodes)
    assert all(n.bc.state.balance(alice["addr"]) == 900 for n in nodes)

    banner("6. Late joiner: V3 goes offline, misses a block, restarts and catches up")
    n3.stop()
    time.sleep(1)
    wait_next_slot(n1)
    tx2 = Transaction.create(alice["priv"], carol["addr"], 50, 1)
    assert n1.submit_tx(tx2)[0]
    wait_until(lambda: tx2.tx_id() in n2.mempool, what="tx2 at V2")
    propose(n1)
    wait_until(lambda: n2.bc.height == 2, what="V2 at height 2")
    n3 = make(2)
    n3.start()
    wait_until(lambda: n3.bc.height == 2, timeout=30, what="V3 sync")
    assert n3.bc.tip.hash() == n1.bc.tip.hash()
    assert n3.bc.state.root() == n1.bc.state.root()

    banner("ALL P2P CHECKS PASSED")
    for n in (n1, n2, n3):
        print(n.status())
        n.stop()


if __name__ == "__main__":
    main()