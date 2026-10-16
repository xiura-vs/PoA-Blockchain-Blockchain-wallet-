"""
service.py - local wallet service (the "background script" of our MetaMask).

  python -m mm_wallet.service [--port 9000] [--vault wallet_vault.json]
                              [--autolock 300] [--nodes 8000,8001,8002]

Holds the Vault, issues an in-memory session token on unlock, auto-locks when
idle, throttles password guessing, and SIGNS transactions itself. Private keys
are never returned by any endpoint except /api/export (password required).
"""

import argparse
import hmac
import json
import secrets
import threading
import time
import urllib.error
import urllib.request
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from config import DASHBOARD_BASE_PORT, VALIDATORS
from transaction import Transaction, ADDR_RE
from .vault import Vault, WalletError, WrongPassword

MAX_BODY = 20_000
MAX_FAILS = 5
# The React build lives next to this package: <project>/wallet-ui/dist
DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wallet-ui", "dist")
MIME = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
        ".svg": "image/svg+xml", ".json": "application/json", ".ico": "image/x-icon",
        ".png": "image/png", ".woff2": "font/woff2"}
STRICT_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
              "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
              "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
LEGACY_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
              "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")


class Locked(WalletError):
    pass


class Throttled(WalletError):
    def __init__(self, wait):
        super().__init__(f"too many wrong passwords, try again in {wait}s")
        self.wait = wait


# ---- talking to the chain nodes ---------------------------------------------
class NodeClient:
    def __init__(self, ports):
        self.ports = list(ports)

    def _req(self, port, path, obj=None, timeout=2.0):
        url = f"http://127.0.0.1:{port}{path}"
        if obj is None:
            req = urllib.request.Request(url)
        else:
            req = urllib.request.Request(
                url, data=json.dumps(obj).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:          # node answered with a 4xx: return its JSON
            return json.load(e)

    def call(self, path, obj=None):
        """Try each node in order; only CONNECTION failures trigger failover."""
        for port in self.ports:
            try:
                return self._req(port, path, obj)
            except (OSError, ValueError):
                continue
        raise WalletError("no chain node reachable - start the nodes first")

class DappBroker:
    """Website -> wallet requests (our stand-in for MetaMask's window.ethereum)."""
    TTL = 120            # seconds a request waits for the user
    MAX_PENDING = 5      # stops a hostile page from spamming popups

    def __init__(self):
        self.lock = threading.Lock()
        self.reqs = {}
        self.perms = {}   # origin -> set of connected addresses (in memory only)

    def _expire(self):
        now = time.time()
        for r in self.reqs.values():
            if r["status"] == "pending" and now - r["t"] > self.TTL:
                r["status"], r["error"] = "rejected", "request expired"
        for rid in [k for k, r in self.reqs.items() if now - r["t"] > 600]:
            del self.reqs[rid]

    def submit(self, origin, rtype, params):
        if not isinstance(origin, str) or not origin or len(origin) > 200:
            raise WalletError("missing Origin header (requests must come from a web page)")
        if rtype not in ("connect", "send_tx"):
            raise WalletError("unknown request type")
        clean = {}
        with self.lock:
            self._expire()
            if sum(1 for r in self.reqs.values() if r["status"] == "pending") >= self.MAX_PENDING:
                raise WalletError("too many pending requests")
            if rtype == "send_tx":
                frm, to, amt = params.get("from"), params.get("to"), params.get("amount")
                if not isinstance(frm, str) or frm not in self.perms.get(origin, ()):
                    raise WalletError("this site is not connected to that account")
                if not isinstance(to, str) or not ADDR_RE.fullmatch(to):
                    raise WalletError("invalid recipient address")
                if type(amt) is not int or not 0 < amt <= 10 ** 12:
                    raise WalletError("invalid amount")
                clean = {"from": frm, "to": to, "amount": amt}
            rid = secrets.token_urlsafe(16)
            self.reqs[rid] = {"id": rid, "origin": origin, "type": rtype, "params": clean,
                              "status": "pending", "result": None, "error": None, "t": time.time()}
            return rid

    def pending(self):
        with self.lock:
            self._expire()
            return [{"id": r["id"], "origin": r["origin"], "type": r["type"], "params": r["params"]}
                    for r in self.reqs.values() if r["status"] == "pending"]

    def result(self, rid, origin):
        with self.lock:
            self._expire()
            r = self.reqs.get(rid)
            if not r or (origin is not None and origin != r["origin"]):
                raise WalletError("unknown request")
            return {"status": r["status"], "result": r["result"], "error": r["error"]}

    def permissions(self):
        with self.lock:
            return [{"origin": o, "accounts": sorted(a)} for o, a in self.perms.items() if a]

    def revoke(self, origin):
        with self.lock:
            self.perms.pop(origin, None)
    def load(self, sites):
        with self.lock:
            self.perms = {o: set(a) for o, a in sites.items()
                          if isinstance(o, str) and isinstance(a, list)}

    def clear(self):
        with self.lock:
            self.perms = {}

# ---- wallet logic + session ---------------------------------------------------
class Service:
    def __init__(self, vault_path, node_ports, autolock):
        self.vault = Vault(vault_path)
        self.nodes = NodeClient(node_ports)
        self.autolock = autolock
        self.lock = threading.Lock()
        self.token = None
        self.last = 0.0
        self.fails = 0
        self.blocked_until = 0.0
        self.dapp = DappBroker()
        threading.Thread(target=self._watch, daemon=True).start()

    # -- session --
    def begin_session(self):
        with self.lock:
            self.token = secrets.token_urlsafe(32)
            self.last = time.time()
            try:
                self.dapp.load(self.vault.get_sites())     # restore saved connections
            except WalletError:
                self.dapp.load({})
            return self.token

    def check_session(self, token, touch):
        with self.lock:
            if (self.token and token and self.vault.unlocked
                    and hmac.compare_digest(token.encode(), self.token.encode())):
                if touch:
                    self.last = time.time()
                return True
            return False

    def do_lock(self):
        with self.lock:
            self.vault.lock()
            self.token = None
            self.dapp.clear()


    def _watch(self):
        while True:
            time.sleep(1)
            with self.lock:
                if self.token and time.time() - self.last > self.autolock:
                    self.vault.lock()
                    self.token = None
                    self.dapp.clear()

    # -- password throttling --
    def with_password(self, fn):
        with self.lock:
            wait = self.blocked_until - time.time()
            if wait > 0:
                raise Throttled(int(wait) + 1)
        try:
            result = fn()
        except WrongPassword:
            with self.lock:
                self.fails += 1
                if self.fails >= MAX_FAILS:
                    self.blocked_until = time.time() + min(300, 15 * 2 ** (self.fails - MAX_FAILS))
            raise
        with self.lock:
            self.fails = 0
        return result

    # -- chain-facing actions --
    def accounts_with_balances(self):
        out = []
        for a in self.vault.list_accounts():
            try:
                info = self.nodes.call(f"/api/balance/{a['address']}")
                a["balance"], a["pending"] = info["balance"], info["pending"]
            except (WalletError, KeyError):
                a["balance"], a["pending"] = None, None
            out.append(a)
        return out

    def send(self, frm, to, amount):
        for label, addr in (("sender", frm), ("recipient", to)):
            if not isinstance(addr, str) or not ADDR_RE.fullmatch(addr):
                raise WalletError(f"invalid {label} address")
        if type(amount) is not int or amount <= 0:
            raise WalletError("amount must be a positive whole number")
        priv = self.vault.get_private_key(frm)                 # raises if not our account
        nonce = self.nodes.call(f"/api/balance/{frm}")["next_nonce"]
        tx = Transaction.create(priv, to, amount, nonce)       # SIGNED HERE, locally
        resp = self.nodes.call("/api/tx", tx.to_dict())
        return {"ok": bool(resp.get("ok")), "reason": resp.get("reason"), "tx_id": tx.tx_id()}

    def network(self):
        out = []
        for i, port in enumerate(self.nodes.ports):
            name = VALIDATORS[i]["name"] if i < len(VALIDATORS) else str(port)
            try:
                s = self.nodes._req(port, "/api/status", timeout=1.0)
                out.append({"name": name, "up": True, "height": s["height"], "peers": s["peers"]})
            except (OSError, ValueError, KeyError):
                out.append({"name": name, "up": False})
        return {"nodes": out}
    def revoke_site(self, origin):
        self.dapp.revoke(origin)
        self.vault.remove_site(origin)
    def discover(self):
        """Re-add used HD accounts after a restore. Silent no-op if no node is reachable."""
        def used(addr):
            info = self.nodes.call(f"/api/balance/{addr}")
            return info["balance"] > 0 or info["nonce"] > 0 or info["pending"] > 0
        try:
            return self.vault.discover(used)
        except (WalletError, KeyError):
            return 0

    def dapp_resolve(self, rid, approve, accounts):
        b = self.dapp
        with b.lock:
            r = b.reqs.get(rid)
            if not r or r["status"] != "pending":
                raise WalletError("request not found or already handled")
            if not approve:
                r["status"], r["error"] = "rejected", "user rejected the request"
                return {"status": "rejected"}
            r["status"] = "working"                      # blocks double-approval
            origin, rtype, params = r["origin"], r["type"], r["params"]
        try:
            if rtype == "connect":
                own = {a["address"] for a in self.vault.list_accounts()}
                if (not isinstance(accounts, list) or not accounts
                        or not all(isinstance(a, str) and a in own for a in accounts)):
                    raise WalletError("pick at least one of your accounts")
                with b.lock:
                    b.perms[origin] = set(accounts)
                self.vault.set_site(origin, accounts)      # saved inside the encrypted vault
                result = {"accounts": accounts}
            else:
                with b.lock:
                    still = params["from"] in b.perms.get(origin, ())
                if not still:
                    raise WalletError("site is no longer connected")
                res = self.send(params["from"], params["to"], params["amount"])   # SIGNED HERE
                if not res["ok"]:
                    raise WalletError(res["reason"] or "rejected by the network")
                result = {"tx_id": res["tx_id"]}
        except WalletError as e:
            with b.lock:
                r["status"], r["error"] = "failed", str(e)
            return {"status": "failed", "error": str(e)}
        with b.lock:
            r["status"], r["result"] = "approved", result
        return {"status": "approved"}


def _s(body, key):
    v = body.get(key)
    if not isinstance(v, str):
        raise WalletError(f"missing or invalid field: {key}")
    return v


def _opt(body, key):
    v = body.get(key)
    return v if isinstance(v, str) else None


# ---- HTTP server --------------------------------------------------------------
def make_server(vault_path, port=9000, autolock=300, node_ports=None):
    node_ports = node_ports or [DASHBOARD_BASE_PORT + i for i in range(len(VALIDATORS))]
    svc = Service(vault_path, node_ports, autolock)
    allowed_hosts, allowed_origins = set(), set()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        # -- plumbing --
        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            cors = getattr(self, "_cors", None)
            if cors:                                   # only ever set for the two dApp endpoints
                self.send_header("Access-Control-Allow-Origin", cors)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(body)

        @staticmethod
        def _is_dapp(path):
            return path == "/api/dapp/request" or path.startswith("/api/dapp/result/")

        def _guard_request(self):
            self._cors = None
            if self.headers.get("Host") not in allowed_hosts:
                self._json(403, {"error": "bad host header"})
                return False
            origin = self.headers.get("Origin")
            if self._is_dapp(urlparse(self.path).path):
                self._cors = origin                    # websites may talk to these two endpoints only
            elif self.command == "POST" and origin is not None and origin not in allowed_origins:
                self._json(403, {"error": "foreign origin refused"})
                return False
            if self.command == "POST" and not self.headers.get("Content-Type", "").startswith("application/json"):
                self._json(415, {"error": "content-type must be application/json"})
                return False
            return True

        def do_OPTIONS(self):                          # CORS preflight
            if not self._guard_request():
                return
            origin = self.headers.get("Origin")
            if not origin or not self._is_dapp(urlparse(self.path).path):
                return self._json(403, {"error": "no cross-origin access"})
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _need(self, touch):
            if not svc.check_session(self.headers.get("X-Session"), touch):
                raise Locked("wallet is locked")

        def _body(self):
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 <= n <= MAX_BODY:
                raise WalletError("bad body size")
            if n == 0:
                return {}
            d = json.loads(self.rfile.read(n))
            if not isinstance(d, dict):
                raise WalletError("body must be a JSON object")
            return d

        def _run(self, fn):
            try:
                code, obj = fn()
            except Throttled as e:
                code, obj = 429, {"error": str(e)}
            except (WrongPassword, Locked) as e:
                code, obj = 401, {"error": str(e)}
            except (WalletError, ValueError) as e:
                code, obj = 400, {"error": str(e)}
            except Exception as e:
                code, obj = 500, {"error": type(e).__name__}
            self._json(code, obj)

        # -- routes --
        def _bytes(self, code, body, ctype, csp=STRICT_CSP):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")      # nobody may frame the wallet (clickjacking)
            self.send_header("Content-Security-Policy", csp)
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _legacy(self):
            try:
                from .ui import PAGE
            except ImportError:
                PAGE = "<h3>Wallet service is running.</h3>"
            self._bytes(200, PAGE.encode(), "text/html; charset=utf-8", LEGACY_CSP)
        def _static(self, path):
            """Serve the React build. Returns True if the request was answered."""
            root = os.path.realpath(DIST)
            index = os.path.join(root, "index.html")
            if not os.path.isfile(index):                    # no build yet: fall back to the old UI
                if path in ("/", "/index.html"):
                    self._legacy()
                    return True
                return False
            rel = path.lstrip("/") or "index.html"
            full = os.path.realpath(os.path.join(root, rel))
            if not (full == root or full.startswith(root + os.sep)):     # path-traversal guard
                return False
            if not os.path.isfile(full):
                if "." in os.path.basename(rel):             # a missing asset is a real 404
                    return False
                full = index                                  # unknown route: single-page app
            ext = os.path.splitext(full)[1].lower()
            ctype = MIME.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as f:
                self._bytes(200, f.read(), ctype)
            return True

        def do_GET(self):
            if not self._guard_request():
                return
            path = urlparse(self.path).path
            if path == "/legacy":                            # the original single-file UI
                return self._legacy()
            if not path.startswith("/api/") and self._static(path):
                return
            self._run(self._get)

        def do_POST(self):
            if self._guard_request():
                self._run(self._post)

        def _get(self):
            p = urlparse(self.path).path
            if not p.startswith("/api/"):
                return 404, {"error": "not found"}
            if p == "/api/state":
                return 200, {"has_vault": svc.vault.exists(),
                             "unlocked": svc.check_session(self.headers.get("X-Session"), False),
                             "autolock_seconds": svc.autolock}
            if p.startswith("/api/dapp/result/"):      # polled by the website; id is an unguessable secret
                return 200, svc.dapp.result(p.rsplit("/", 1)[1], self.headers.get("Origin"))
            self._need(False)                          # reads never reset the idle timer
            if p == "/api/accounts":
                return 200, {"accounts": svc.accounts_with_balances()}
            if p.startswith("/api/balance/") or p.startswith("/api/history/"):
                addr = p.rsplit("/", 1)[1]
                if not ADDR_RE.fullmatch(addr):
                    raise WalletError("invalid address")
                return 200, svc.nodes.call(p)
            if p == "/api/network":
                return 200, svc.network()
            if p == "/api/dapp/pending":
                return 200, {"requests": svc.dapp.pending()}
            if p == "/api/dapp/permissions":
                return 200, {"sites": svc.dapp.permissions()}
            return 404, {"error": "not found"}

        def _post(self):
            p = urlparse(self.path).path
            body = self._body()
            v = svc.vault

            # --- endpoints that work while locked ---
            if p == "/api/create":
                phrase = v.create(_s(body, "password"))
                return 200, {"mnemonic": phrase, "token": svc.begin_session(),
                             "accounts": v.list_accounts()}
            if p == "/api/restore":
                v.create(_s(body, "password"), mnemonic=_s(body, "mnemonic"))
                found = svc.discover()
                return 200, {"token": svc.begin_session(), "accounts": v.list_accounts(),
                             "discovered": found}
            if p == "/api/unlock":
                pw = _s(body, "password")
                svc.with_password(lambda: v.unlock(pw))
                return 200, {"token": svc.begin_session(), "accounts": v.list_accounts()}
            if p == "/api/dapp/request":               # called by WEBSITES (no session, no idle reset)
                if not v.unlocked:
                    raise Locked("wallet is locked - open the wallet and unlock it first")
                params = body.get("params")
                rid = svc.dapp.submit(self.headers.get("Origin"), body.get("type"),
                                      params if isinstance(params, dict) else {})
                return 200, {"id": rid}

            # --- everything below needs a live session (and counts as activity) ---
            self._need(True)
            if p == "/api/lock":
                svc.do_lock()
                return 200, {"ok": True}
            if p == "/api/ping":
                return 200, {"ok": True}
            if p == "/api/accounts/add":
                return 200, v.add_account(_opt(body, "name"))
            if p == "/api/accounts/import":
                return 200, v.import_private_key(_s(body, "private_key"), _opt(body, "name"))
            if p == "/api/accounts/rename":
                v.rename_account(_s(body, "address"), _s(body, "name"))
                return 200, {"ok": True}
            if p == "/api/send":
                res = svc.send(body.get("from"), body.get("to"), body.get("amount"))
                return (200 if res["ok"] else 400), res
            if p == "/api/reveal":
                pw = _s(body, "password")
                return 200, {"mnemonic": svc.with_password(lambda: v.reveal_mnemonic(pw))}
            if p == "/api/export":
                pw, addr = _s(body, "password"), _s(body, "address")
                return 200, {"private_key": svc.with_password(lambda: v.export_private_key(addr, pw))}
            if p == "/api/change_password":
                old, new = _s(body, "old"), _s(body, "new")
                svc.with_password(lambda: v.change_password(old, new))
                return 200, {"ok": True}
            if p == "/api/dapp/resolve":
                return 200, svc.dapp_resolve(_s(body, "id"), body.get("approve") is True,
                                             body.get("accounts"))
            if p == "/api/dapp/revoke":
                svc.revoke_site(_s(body, "origin"))
                return 200, {"ok": True}
            return 404, {"error": "not found"}

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    real = srv.server_address[1]
    for h in (f"127.0.0.1:{real}", f"localhost:{real}"):
        allowed_hosts.add(h)
        allowed_origins.add("http://" + h)
    return srv, svc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--vault", default="wallet_vault.json")
    ap.add_argument("--autolock", type=int, default=300, help="idle seconds before auto-lock")
    ap.add_argument("--nodes", default=",".join(str(DASHBOARD_BASE_PORT + i) for i in range(len(VALIDATORS))))
    a = ap.parse_args()
    srv, svc = make_server(a.vault, a.port, a.autolock, [int(x) for x in a.nodes.split(",")])
    print(f"wallet service on http://127.0.0.1:{a.port}  (vault: {a.vault}, "
          f"auto-lock {a.autolock}s, nodes {a.nodes})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        svc.do_lock()
        print("locked and stopped.")


if __name__ == "__main__":
    main()