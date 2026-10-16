import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request

from config import USERS, VALIDATORS, DASHBOARD_BASE_PORT
from consensus import PoANode
from dashboard import start_api
from mm_wallet.service import make_server

ABANDON = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
PW = "correct horse battery"
bob, alice = USERS["bob"], USERS["alice"]


def start(autolock=300, node_ports=None):
    path = os.path.join(tempfile.mkdtemp(), "vault.json")
    srv, svc = make_server(path, 0, autolock, node_ports or [1])   # port 1 = no node
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, svc, srv.server_address[1]


def call(port, method, path, body=None, token=None, headers=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["X-Session"] = token
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def wait_until(cond, timeout=45, what=""):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for: {what}")


def test_lifecycle_and_sessions():
    srv, svc, port = start()
    assert call(port, "GET", "/api/state")[1] == {"has_vault": False, "unlocked": False, "autolock_seconds": 300}
    assert call(port, "GET", "/api/accounts")[0] == 401                       # no token

    assert call(port, "POST", "/api/create", {"password": "short"})[0] == 400
    code, r = call(port, "POST", "/api/create", {"password": PW})
    assert code == 200 and len(r["mnemonic"].split()) == 12
    tok, phrase = r["token"], r["mnemonic"]
    assert call(port, "POST", "/api/create", {"password": PW})[0] == 400      # already exists

    code, r = call(port, "GET", "/api/accounts", token=tok)
    assert code == 200 and len(r["accounts"]) == 1
    assert r["accounts"][0]["balance"] is None                                # nodes are down: handled
    assert call(port, "GET", "/api/accounts", token="garbage")[0] == 401

    assert call(port, "POST", "/api/accounts/add", {"name": "Savings"}, tok)[0] == 200
    code, imp = call(port, "POST", "/api/accounts/import", {"private_key": alice["priv"], "name": "Alice"}, tok)
    assert code == 200 and imp["address"] == alice["addr"]
    assert call(port, "POST", "/api/accounts/import", {"private_key": "zz"}, tok)[0] == 400
    assert call(port, "POST", "/api/accounts/rename", {"address": alice["addr"], "name": "A2"}, tok)[0] == 200
    assert len(call(port, "GET", "/api/accounts", token=tok)[1]["accounts"]) == 3

    code, r = call(port, "POST", "/api/send", {"from": alice["addr"], "to": bob["addr"], "amount": 5}, tok)
    assert code == 400 and "node" in r["error"]                               # no node reachable
    assert call(port, "POST", "/api/send", {"from": alice["addr"], "to": "nope", "amount": 5}, tok)[0] == 400
    assert call(port, "POST", "/api/send", {"from": alice["addr"], "to": bob["addr"], "amount": 1.5}, tok)[0] == 400

    assert call(port, "POST", "/api/lock", {}, tok)[0] == 200                 # lock
    assert call(port, "GET", "/api/accounts", token=tok)[0] == 401
    assert call(port, "POST", "/api/unlock", {"password": "wrong password"})[0] == 401
    code, r = call(port, "POST", "/api/unlock", {"password": PW})
    assert code == 200
    tok2 = r["token"]
    assert call(port, "GET", "/api/accounts", token=tok)[0] == 401            # old token is dead
    assert call(port, "GET", "/api/accounts", token=tok2)[0] == 200

    assert call(port, "POST", "/api/reveal", {"password": "nope nope nope"}, tok2)[0] == 401
    code, r = call(port, "POST", "/api/reveal", {"password": PW}, tok2)
    assert code == 200 and r["mnemonic"] == phrase
    assert call(port, "POST", "/api/change_password", {"old": PW, "new": "a brand new password"}, tok2)[0] == 200
    srv.shutdown()


def test_browser_attack_defenses():
    srv, svc, port = start()
    assert call(port, "GET", "/api/state", headers={"Host": "evil.example.com"})[0] == 403   # DNS rebinding
    assert call(port, "POST", "/api/unlock", {"password": PW}, headers={"Origin": "http://evil.example.com"})[0] == 403
    code, _ = call(port, "POST", "/api/unlock", {"password": PW}, headers={"Content-Type": "text/plain"})
    assert code == 415
    srv.shutdown()


def test_password_throttling():
    srv, svc, port = start()
    call(port, "POST", "/api/create", {"password": PW})
    call(port, "POST", "/api/lock", {}, None)
    svc.do_lock()
    for _ in range(5):
        assert call(port, "POST", "/api/unlock", {"password": "wrong wrong wrong"})[0] == 401
    code, r = call(port, "POST", "/api/unlock", {"password": PW})            # even the RIGHT password
    assert code == 429, (code, r)
    print("   throttled ->", r["error"])
    srv.shutdown()


def test_auto_lock():
    srv, svc, port = start(autolock=2)
    tok = call(port, "POST", "/api/create", {"password": PW})[1]["token"]
    assert call(port, "GET", "/api/accounts", token=tok)[0] == 200
    time.sleep(4)                                                             # idle (reads don't count)
    assert call(port, "GET", "/api/accounts", token=tok)[0] == 401
    assert call(port, "GET", "/api/state", token=tok)[1]["unlocked"] is False
    srv.shutdown()


def test_restore_from_phrase():
    srv1, _, p1 = start()
    srv2, _, p2 = start()
    c1, r1 = call(p1, "POST", "/api/restore", {"password": PW, "mnemonic": ABANDON})
    c2, r2 = call(p2, "POST", "/api/restore", {"password": "different password", "mnemonic": ABANDON.upper()})
    assert c1 == c2 == 200
    assert r1["accounts"][0]["address"] == r2["accounts"][0]["address"]       # same phrase -> same account
    assert call(p2, "POST", "/api/restore", {"password": PW, "mnemonic": "abandon abandon"})[0] == 400
    srv1.shutdown()
    srv2.shutdown()


def test_end_to_end_with_real_chain():
    ports = [v["port"] for v in VALIDATORS]
    nodes = [PoANode(v["name"], v["port"], ports, validator=v) for v in VALIDATORS]
    apis = []
    for i, n in enumerate(nodes):
        n.start()
        apis.append(start_api(n, DASHBOARD_BASE_PORT + i))
    wait_until(lambda: all(n.net.connected() == 2 for n in nodes), what="mesh")

    srv, svc, port = start(node_ports=[DASHBOARD_BASE_PORT + i for i in range(3)])
    code, r = call(port, "POST", "/api/create", {"password": PW})
    tok = r["token"]
    me = r["accounts"][0]["address"]
    call(port, "POST", "/api/accounts/import", {"private_key": alice["priv"], "name": "Alice"}, tok)

    def acct(addr):
        accts = call(port, "GET", "/api/accounts", token=tok)[1]["accounts"]
        return next(a for a in accts if a["address"] == addr)

    print("   alice (imported) -> my new HD account: 100")
    code, r = call(port, "POST", "/api/send", {"from": alice["addr"], "to": me, "amount": 100}, tok)
    assert code == 200 and r["ok"], r
    wait_until(lambda: acct(me)["balance"] == 100, what="HD account funded")

    print("   overspend is refused by the network")
    code, r = call(port, "POST", "/api/send", {"from": me, "to": bob["addr"], "amount": 10 ** 6}, tok)
    assert code == 400 and "insufficient" in r["reason"], r

    print("   HD account -> bob: 30")
    code, r = call(port, "POST", "/api/send", {"from": me, "to": bob["addr"], "amount": 30}, tok)
    assert code == 200 and r["ok"], r
    wait_until(lambda: acct(me)["balance"] == 70, what="HD account spent")

    code, hist = call(port, "GET", f"/api/history/{me}", token=tok)
    assert code == 200 and [h["amount"] for h in hist] == [30, 100], hist     # newest first
    assert all(h["status"] == "confirmed" and h["proposer"] in ("V1", "V2", "V3") for h in hist)
    net = call(port, "GET", "/api/network", token=tok)[1]["nodes"]
    assert all(n["up"] for n in net)

    # the private keys must never appear in any normal response
    blob = json.dumps(call(port, "GET", "/api/accounts", token=tok)[1]) + json.dumps(hist)
    assert alice["priv"] not in blob

    srv.shutdown()
    for a in apis:
        a.shutdown()
        a.server_close()
    for n in nodes:
        n.stop()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)