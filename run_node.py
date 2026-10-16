"""
run_node.py - run ONE validator node with an interactive console.

    python run_node.py V1        (then V2, V3 in other windows)
"""

import argparse
import time

from config import VALIDATORS, USERS
from consensus import PoANode
from transaction import Transaction, ADDR_RE
from config import DASHBOARD_BASE_PORT
from dashboard import start_api

HELP = """
Commands:
  send <from> <to> <amount>   e.g.  send alice bob 100     (from: alice|bob|carol)
  bal                         confirmed balances of the demo users
  chain                       last 8 blocks
  status                      height / tip / state root / mempool / peers
  help | quit
"""

VNAME = {v["addr"]: v["name"] for v in VALIDATORS}


def resolve(x):
    if x in USERS:
        return USERS[x]["addr"]
    return x if ADDR_RE.fullmatch(x) else None


def console(node):
    print(HELP, flush=True)
    while True:
        try:
            line = input()
        except EOFError:                       # no interactive stdin: just keep running
            while True:
                time.sleep(3600)
        parts = line.strip().split()
        if not parts:
            continue
        cmd = parts[0].lower()
        try:
            if cmd in ("quit", "exit"):
                return
            elif cmd == "help":
                print(HELP)
            elif cmd == "status":
                print(node.status())
            elif cmd == "bal":
                with node.lock:
                    for n, u in USERS.items():
                        print(f"  {n:6} balance {node.bc.state.balance(u['addr']):>6}"
                              f"   nonce {node.bc.state.nonce(u['addr'])}")
            elif cmd == "chain":
                with node.lock:
                    for b in node.bc.chain[-8:]:
                        who = VNAME.get(b.proposer, b.proposer)
                        print(f"  #{b.height} {b.hash()[:8]}  slot {b.slot}  by {who:7} txs {len(b.txs)}")
            elif cmd == "send":
                if len(parts) != 4 or parts[1] not in USERS:
                    print("  usage: send <alice|bob|carol> <name-or-address> <amount>")
                    continue
                dest = resolve(parts[2])
                if dest is None:
                    print("  unknown recipient")
                    continue
                u = USERS[parts[1]]
                tx = Transaction.create(u["priv"], dest, int(parts[3]), node.next_nonce(u["addr"]))
                node.submit_tx(tx)
            else:
                print("  unknown command (type 'help')")
        except ValueError as e:
            print(f"  bad input: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", choices=[v["name"] for v in VALIDATORS])
    args = ap.parse_args()

    idx = next(i for i, v in enumerate(VALIDATORS) if v["name"] == args.name)
    v = VALIDATORS[idx]
    node = PoANode(v["name"], v["port"], [x["port"] for x in VALIDATORS], validator=v)
    node.start()
    api_port = DASHBOARD_BASE_PORT + idx
    start_api(node, api_port)
    print(f"dashboard + API: http://127.0.0.1:{api_port}", flush=True)
    try:
        console(node)
    except KeyboardInterrupt:
        pass
    finally:
        print("shutting down...")
        node.stop()

if __name__ == "__main__":
    main()