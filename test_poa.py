import time

from blockchain import Blockchain
from config import VALIDATORS, USERS
from consensus import PoANode
from transaction import Transaction

PORTS = [v["port"] for v in VALIDATORS]
alice, bob = USERS["alice"], USERS["bob"]
NAME = {v["addr"]: v["name"] for v in VALIDATORS}


def make(i):
    return PoANode(VALIDATORS[i]["name"], PORTS[i], PORTS, validator=VALIDATORS[i])


def wait_until(cond, timeout=30, what=""):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for: {what}")


def banner(s):
    print(f"\n===== {s} =====", flush=True)


def send_and_confirm(sender_node, live, amount=1):
    """Submit one alice->bob tx, wait for ALL live nodes to commit the resulting block."""
    h = sender_node.bc.height
    tx = Transaction.create(alice["priv"], bob["addr"], amount,
                            sender_node.next_nonce(alice["addr"]))
    ok, reason = sender_node.submit_tx(tx)
    assert ok, reason
    wait_until(lambda: all(n.bc.height == h + 1 for n in live), what=f"block #{h + 1} on all live nodes")
    blk = sender_node.bc.tip
    assert blk.proposer == Blockchain.proposer_for_slot(blk.slot)["addr"]     # right turn
    assert len({n.bc.tip.hash() for n in live}) == 1                          # same block everywhere
    return blk


def main():
    n1, n2, n3 = nodes = [make(i) for i in range(3)]
    for n in nodes:
        n.start()
    wait_until(lambda: all(n.net.connected() == 2 for n in nodes), what="mesh")
    live = list(nodes)

    banner("1. Four txs, one at a time: the validator whose slot it is proposes each block")
    order = []
    for _ in range(4):
        blk = send_and_confirm(n1, live, amount=10)
        order.append(NAME[blk.proposer])
        print(f"   >>> block #{blk.height} in slot {blk.slot} proposed by {NAME[blk.proposer]}", flush=True)
    assert len(set(order)) >= 2, f"expected rotation, got {order}"
    print("   proposer sequence:", order)

    banner("2. V2 goes offline: its slots are skipped, chain keeps going")
    n2.stop()
    live = [n1, n3]
    time.sleep(1)
    for _ in range(2):
        prev_slot = n1.bc.tip.slot
        blk = send_and_confirm(n1, live)
        assert NAME[blk.proposer] != "V2"
        print(f"   >>> block #{blk.height} slot {blk.slot} by {NAME[blk.proposer]} "
              f"(gap of {blk.slot - prev_slot} slot(s) since previous block)", flush=True)

    banner("3. V2 restarts, syncs (re-validating every block), and rejoins")
    n2 = make(1)
    n2.start()
    live = [n1, n2, n3]
    wait_until(lambda: n2.bc.height == n1.bc.height, timeout=40, what="V2 catch-up")
    assert n2.bc.state.root() == n1.bc.state.root()
    blk = send_and_confirm(n1, live)
    print(f"   >>> block #{blk.height} by {NAME[blk.proposer]} accepted by all three", flush=True)

    banner("ALL PoA CHECKS PASSED")
    for n in (n1, n2, n3):
        print(n.status())
        n.stop()


if __name__ == "__main__":
    main()