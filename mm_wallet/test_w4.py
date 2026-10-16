import os
import tempfile
import urllib.error
import urllib.request
import threading
from mm_wallet.service import make_server

from config import USERS
from mm_wallet.test_service import start, call, PW, ABANDON
from mm_wallet.vault import Vault, WalletError

bob = USERS["bob"]
SITE = {"Origin": "http://shop.example"}
EVIL = {"Origin": "http://evil.example"}


def tv():
    return Vault(os.path.join(tempfile.mkdtemp(), "vault.json"))


def raw(port, method, path, headers):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.headers


def test_discovery():
    scratch = tv()
    scratch.create(PW, mnemonic=ABANDON)
    for _ in range(6):
        scratch.add_account()
    addrs = [a["address"] for a in scratch.list_accounts()]            # HD indices 0..6

    v = tv()
    v.create(PW, mnemonic=ABANDON)
    assert v.discover(lambda a: False) == 0 and len(v.list_accounts()) == 1
    assert v.discover(lambda a: a in {addrs[2], addrs[3]}) == 3        # re-adds indices 1..3
    assert [a["address"] for a in v.list_accounts()] == addrs[:4]
    v.add_account()                                                    # next one continues at index 4
    assert v.list_accounts()[4]["address"] == addrs[4]

    v2 = tv()
    v2.create(PW, mnemonic=ABANDON)
    assert v2.discover(lambda a: a == addrs[6]) == 0                   # beyond the gap limit: not found

    v3 = tv()
    v3.create(PW, mnemonic=ABANDON)

    def boom(a):
        raise WalletError("nodes down")
    try:
        v3.discover(boom)
        assert False
    except WalletError:
        pass
    assert len(v3.list_accounts()) == 1                                # nothing half-added


def test_dapp_flow():
    srv, svc, port = start()
    connect = {"type": "connect"}
    assert call(port, "POST", "/api/dapp/request", connect, headers=SITE)[0] == 401     # locked wallet
    code, r = call(port, "POST", "/api/create", {"password": PW})
    tok, me = r["token"], r["accounts"][0]["address"]

    assert call(port, "POST", "/api/dapp/request", connect)[0] == 400                   # no Origin header
    pay = {"type": "send_tx", "params": {"from": me, "to": bob["addr"], "amount": 5}}
    assert call(port, "POST", "/api/dapp/request", pay, headers=SITE)[0] == 400         # not connected yet

    rid = call(port, "POST", "/api/dapp/request", connect, headers=SITE)[1]["id"]
    pend = call(port, "GET", "/api/dapp/pending", token=tok)[1]["requests"]
    assert [(x["origin"], x["type"]) for x in pend] == [("http://shop.example", "connect")]
    assert call(port, "GET", "/api/dapp/pending")[0] == 401                             # needs a session
    assert call(port, "GET", f"/api/dapp/result/{rid}", headers=SITE)[1]["status"] == "pending"
    assert call(port, "GET", f"/api/dapp/result/{rid}", headers=EVIL)[0] == 400         # other origin can't read
    r = call(port, "POST", "/api/dapp/resolve", {"id": rid, "approve": True, "accounts": ["PC" + "0" * 40]}, tok)[1]
    assert r["status"] == "failed"                                                      # not our account

    rid = call(port, "POST", "/api/dapp/request", connect, headers=SITE)[1]["id"]
    assert call(port, "POST", "/api/dapp/resolve", {"id": rid, "approve": True, "accounts": [me]}, tok)[1]["status"] == "approved"
    assert call(port, "GET", f"/api/dapp/result/{rid}", headers=SITE)[1] == \
        {"status": "approved", "result": {"accounts": [me]}, "error": None}
    assert call(port, "POST", "/api/dapp/resolve", {"id": rid, "approve": True, "accounts": [me]}, tok)[0] == 400
    sites = call(port, "GET", "/api/dapp/permissions", token=tok)[1]["sites"]
    assert sites == [{"origin": "http://shop.example", "accounts": [me]}]

    for params in ({"from": me, "to": "nope", "amount": 5},
                   {"from": me, "to": bob["addr"], "amount": 1.5},
                   {"from": me, "to": bob["addr"], "amount": -1},
                   {"from": "PC" + "1" * 40, "to": bob["addr"], "amount": 5},
                   {"from": [1], "to": bob["addr"], "amount": 5}):
        assert call(port, "POST", "/api/dapp/request", {"type": "send_tx", "params": params}, headers=SITE)[0] == 400

    rid = call(port, "POST", "/api/dapp/request", pay, headers=SITE)[1]["id"]
    assert call(port, "POST", "/api/dapp/resolve", {"id": rid, "approve": False}, tok)[1]["status"] == "rejected"
    x = call(port, "GET", f"/api/dapp/result/{rid}", headers=SITE)[1]
    assert x["status"] == "rejected" and "rejected" in x["error"]

    rid = call(port, "POST", "/api/dapp/request", pay, headers=SITE)[1]["id"]
    r = call(port, "POST", "/api/dapp/resolve", {"id": rid, "approve": True}, tok)[1]
    assert r["status"] == "failed" and "node" in r["error"]                              # no chain node in this test

    assert call(port, "POST", "/api/dapp/revoke", {"origin": "http://shop.example"}, tok)[0] == 200
    assert call(port, "POST", "/api/dapp/request", pay, headers=SITE)[0] == 400          # permission gone

    for _ in range(5):
        assert call(port, "POST", "/api/dapp/request", connect, headers=SITE)[0] == 200
    code, r = call(port, "POST", "/api/dapp/request", connect, headers=SITE)
    assert code == 400 and "too many" in r["error"]                                      # popup-spam cap
    srv.shutdown()


def test_cors_only_on_dapp_endpoints():
    srv, svc, port = start()
    code, h = raw(port, "OPTIONS", "/api/dapp/request", {"Origin": "http://shop.example"})
    assert code == 204 and h.get("Access-Control-Allow-Origin") == "http://shop.example"
    code, h = raw(port, "OPTIONS", "/api/send", {"Origin": "http://shop.example"})
    assert code == 403 and h.get("Access-Control-Allow-Origin") is None
    code, _ = raw(port, "OPTIONS", "/api/dapp/request", {"Origin": "http://shop.example", "Host": "evil.example.com"})
    assert code == 403
    assert call(port, "POST", "/api/unlock", {"password": PW}, headers=EVIL)[0] == 403   # normal endpoints stay locked
    srv.shutdown()

def test_connected_sites_survive_restart():
    path = os.path.join(tempfile.mkdtemp(), "vault.json")

    def boot():                                    # starts a fresh service on the SAME vault file
        srv, svc = make_server(path, 0, 300, [1])
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, srv.server_address[1]

    def sites(port, tok):
        return call(port, "GET", "/api/dapp/permissions", token=tok)[1]["sites"]

    srv, port = boot()
    r = call(port, "POST", "/api/create", {"password": PW})[1]
    tok, me = r["token"], r["accounts"][0]["address"]
    rid = call(port, "POST", "/api/dapp/request", {"type": "connect"}, headers=SITE)[1]["id"]
    assert call(port, "POST", "/api/dapp/resolve", {"id": rid, "approve": True, "accounts": [me]}, tok)[1]["status"] == "approved"
    srv.shutdown()
    srv.server_close()

    srv, port = boot()                              # "service restarted"
    tok = call(port, "POST", "/api/unlock", {"password": PW})[1]["token"]
    assert sites(port, tok) == [{"origin": "http://shop.example", "accounts": [me]}]
    pay = {"type": "send_tx", "params": {"from": me, "to": bob["addr"], "amount": 5}}
    assert call(port, "POST", "/api/dapp/request", pay, headers=SITE)[0] == 200      # still connected
    assert call(port, "POST", "/api/dapp/revoke", {"origin": "http://shop.example"}, tok)[0] == 200
    srv.shutdown()
    srv.server_close()

    srv, port = boot()                              # restart again: the removal persisted too
    tok = call(port, "POST", "/api/unlock", {"password": PW})[1]["token"]
    assert sites(port, tok) == []
    assert "shop.example" not in open(path).read()  # and the vault file never shows the origin in clear
    srv.shutdown()
    srv.server_close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)