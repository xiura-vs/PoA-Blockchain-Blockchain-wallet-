"""
wallet.py - keys live HERE, not in the node. The wallet signs locally and
sends only the signed transaction to a node's HTTP API.

  python wallet.py new                               # creates wallet.json
  python wallet.py address
  python wallet.py balance [name-or-address]
  python wallet.py send <name-or-address> <amount>

Global options go BEFORE the command:
  python wallet.py --user alice --node V2 send bob 25
  (--user uses a built-in demo account: alice|bob|carol; otherwise wallet.json)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from config import USERS, VALIDATORS, DASHBOARD_BASE_PORT
from crypto_utils import generate_keypair, public_key_from_private, public_key_to_address
from transaction import Transaction, ADDR_RE


# ---- tiny HTTP client (stdlib only) ----------------------------------------
def api_get(port, path, timeout=3):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return json.load(r)


def api_post(port, path, obj, timeout=5):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:      # API returns JSON on 4xx too
        return json.load(e)


def node_port(name):
    return DASHBOARD_BASE_PORT + [v["name"] for v in VALIDATORS].index(name)


# ---- the wallet ------------------------------------------------------------
class Wallet:
    def __init__(self, private_key_hex):
        self.priv = private_key_hex
        self.pub = public_key_from_private(private_key_hex)
        self.addr = public_key_to_address(self.pub)

    @classmethod
    def new(cls):
        return cls(generate_keypair()[0])

    @classmethod
    def demo(cls, name):
        return cls(USERS[name]["priv"])

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls(json.load(f)["private_key"])

    def save(self, path):
        # DEMO ONLY: plaintext private key on disk.
        with open(path, "w") as f:
            json.dump({"private_key": self.priv, "public_key": self.pub,
                       "address": self.addr}, f, indent=2)

    def account(self, port):
        return api_get(port, f"/api/balance/{self.addr}")

    def send(self, port, to_addr, amount):
        """Ask the node for our next nonce, SIGN LOCALLY, submit. Returns (tx, response)."""
        nonce = self.account(port)["next_nonce"]
        tx = Transaction.create(self.priv, to_addr, amount, nonce)
        return tx, api_post(port, "/api/tx", tx.to_dict())


def resolve(x):
    if x in USERS:
        return USERS[x]["addr"]
    if ADDR_RE.fullmatch(x):
        return x
    raise SystemExit(f"unknown recipient: {x}")


def main():
    ap = argparse.ArgumentParser(prog="wallet.py")
    ap.add_argument("--file", default="wallet.json")
    ap.add_argument("--user", choices=list(USERS))
    ap.add_argument("--node", default="V1", choices=[v["name"] for v in VALIDATORS])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new")
    p.add_argument("--force", action="store_true")
    sub.add_parser("address")
    p = sub.add_parser("balance")
    p.add_argument("target", nargs="?")
    p = sub.add_parser("send")
    p.add_argument("to")
    p.add_argument("amount", type=int)
    args = ap.parse_args()

    if args.cmd == "new":
        if os.path.exists(args.file) and not args.force:
            raise SystemExit(f"{args.file} exists (use --force to overwrite)")
        w = Wallet.new()
        w.save(args.file)
        print(f"created {args.file}\naddress: {w.addr}")
        return

    if args.user:
        w = Wallet.demo(args.user)
    elif os.path.exists(args.file):
        w = Wallet.load(args.file)
    else:
        raise SystemExit("no wallet: run 'python wallet.py new' or use --user alice")
    port = node_port(args.node)

    try:
        if args.cmd == "address":
            print(w.addr)
        elif args.cmd == "balance":
            addr = resolve(args.target) if args.target else w.addr
            a = api_get(port, f"/api/balance/{addr}")
            print(f"{addr}\n  balance {a['balance']}   nonce {a['nonce']}   pending txs {a['pending']}")
        elif args.cmd == "send":
            tx, resp = w.send(port, resolve(args.to), args.amount)
            print(f"signed locally: {tx}")
            print("node says:", "ACCEPTED into mempool" if resp.get("ok") else f"REJECTED - {resp.get('reason')}")
    except (urllib.error.URLError, ConnectionError, OSError):
        raise SystemExit(f"cannot reach node {args.node} on port {port}. Is it running?")


if __name__ == "__main__":
    main()