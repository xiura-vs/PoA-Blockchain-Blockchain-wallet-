"""
run_demo.py - one command for the whole mentor demo.

  python run_demo.py            # pauses for Enter between scenes (you narrate)
  python run_demo.py --auto     # no pauses
  python run_demo.py --no-failure --no-browser
"""

import argparse
import os
import subprocess
import sys
import time
import webbrowser

from config import VALIDATORS, USERS, DASHBOARD_BASE_PORT
from crypto_utils import public_key_to_address
from transaction import Transaction
from wallet import Wallet, api_get, api_post

HERE = os.path.dirname(os.path.abspath(__file__))
API = {v["name"]: DASHBOARD_BASE_PORT + i for i, v in enumerate(VALIDATORS)}
procs = {}


def launch(name):
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_CONSOLE   # each node gets its own window
    else:
        kw["stdin"] = subprocess.DEVNULL
    procs[name] = subprocess.Popen([sys.executable, "run_node.py", name], cwd=HERE, **kw)


def banner(t):
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}", flush=True)


def status(name):
    try:
        return api_get(API[name], "/api/status", timeout=1.5)
    except Exception:
        return None


def wait_for(cond, what, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if cond():
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit(f"timed out waiting for: {what}")


def bal(name, addr):
    return api_get(API[name], f"/api/balance/{addr}")["balance"]


def wait_balance(addr, expected, live):
    wait_for(lambda: all(bal(n, addr) == expected for n in live),
             f"balance {expected} on {live}", timeout=60)


def latest_block(name):
    return api_get(API[name], "/api/chain?limit=1")[0]


def show_block(name):
    b = latest_block(name)
    print(f"  -> included in block #{b['height']} (slot {b['slot']}) proposed & signed by {b['proposer']}, "
          f"hash {b['hash'][:10]}, merkle {b['merkle'][:10]}", flush=True)


def show_agreement(live):
    print("  all nodes agree?", flush=True)
    for n in live:
        s = status(n)
        print(f"    {n}: height {s['height']}  tip {s['tip']}  state {s['state']}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-failure", action="store_true")
    args = ap.parse_args()

    def pause(msg=""):
        if msg:
            print(f"\n  {msg}", flush=True)
        if not args.auto:
            input("  [press Enter to continue] ")

    names = [v["name"] for v in VALIDATORS]
    try:
        banner("Launching 3 validator nodes (one console window each)")
        for n in names:
            launch(n)
        wait_for(lambda: all((status(n) or {}).get("peers") == 2 for n in names), "mesh", 60)
        url = f"http://127.0.0.1:{API['V1']}"
        print(f"  mesh is up. Dashboard: {url}")
        if not args.no_browser:
            webbrowser.open(url)

        alice, bob = Wallet.demo("alice"), Wallet.demo("bob")
        dave = Wallet.new()
        print(f"  fresh wallet 'dave' generated: {dave.addr}")
        live = list(names)

        # ---- Scene 1 ------------------------------------------------------
        pause("SCENE 1: alice pays the brand-new wallet dave 100 (submitted to V1).")
        banner("SCENE 1 - submit -> gossip -> validator -> block -> everyone validates")
        print(f"  alice balance {bal('V1', alice.addr)}, dave balance {bal('V1', dave.addr)}")
        tx1, resp = alice.send(API["V1"], dave.addr, 100)
        print(f"  alice signs locally and submits to V1: {tx1}")
        print(f"  V1 replies: {resp}")
        print("  waiting for the validator whose slot comes next (up to ~15s)...", flush=True)
        wait_balance(dave.addr, 100, live)
        show_block("V1")
        show_agreement(live)

        # ---- Scene 2 ------------------------------------------------------
        pause("SCENE 2: same thing, but submitted to a DIFFERENT node (V3), by bob.")
        banner("SCENE 2 - any node accepts a tx; gossip carries it to the right validator")
        tx2, resp = bob.send(API["V3"], dave.addr, 50)
        print(f"  bob -> dave 50 submitted to V3: {resp}")
        wait_balance(dave.addr, 150, live)
        show_block("V3")

        # ---- Scene 3 ------------------------------------------------------
        pause("SCENE 3: attacks. Every one of these must be refused.")
        banner("SCENE 3 - invalid transactions are rejected independently")
        _, r = alice.send(API["V2"], dave.addr, 10**6)
        print(f"  overspend (alice has ~900, sends 1,000,000): {r.get('reason')}")

        forged = Transaction(alice.addr, alice.pub, dave.addr, 5, alice.account(API["V1"])["next_nonce"])
        forged.sign(dave.priv)                                  # signed with the WRONG key
        r = api_post(API["V1"], "/api/tx", forged.to_dict())
        print(f"  forged signature (tx 'from alice' signed by dave): {r.get('reason')}")

        r = api_post(API["V2"], "/api/tx", tx1.to_dict())
        print(f"  replay of alice's already-confirmed tx: {r.get('reason')}")

        # ---- Scene 4 ------------------------------------------------------
        if not args.no_failure:
            pause("SCENE 4: kill validator V2. Its slots will pass with no block; the chain must go on.")
            banner("SCENE 4 - a validator dies, the chain survives, then it rejoins")
            procs["V2"].terminate()
            procs["V2"].wait()
            live = ["V1", "V3"]
            print("  V2 killed (watch its card go OFFLINE on the dashboard).")
            time.sleep(1)
            _, r = alice.send(API["V1"], dave.addr, 10)
            print(f"  alice -> dave 10 via V1: {r}")
            wait_balance(dave.addr, 160, live)
            show_block("V1")

            pause("Now restart V2: it should re-download and RE-VALIDATE every block it missed.")
            launch("V2")
            wait_for(lambda: status("V2") and status("V2")["height"] == status("V1")["height"],
                     "V2 catch-up", 60)
            live = list(names)
            print("  V2 is back and caught up.")
            time.sleep(2)
            show_agreement(live)

        banner("DEMO COMPLETE - dashboard is still live")
        input("  Press Enter to shut down all nodes... ")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs.values():
            if p.poll() is None:
                p.terminate()
        print("nodes stopped.")


if __name__ == "__main__":
    main()