"""
dashboard.py - per-node HTTP API + a single-page live dashboard (stdlib only).

GET  /                    dashboard page (polls all 3 nodes from the browser)
GET  /api/info            chain constants, validators, demo user addresses
GET  /api/status          height / tip / state root / mempool / peers
GET  /api/chain?limit=N   latest N blocks, newest first
GET  /api/mempool         pending transactions
GET  /api/balances        every account in the confirmed state
GET  /api/balance/<addr>  one account (+ next_nonce counting pending txs)
GET  /api/events?since=N  this node's log lines
POST /api/tx              submit a SIGNED transaction (JSON)
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse, parse_qs

from config import CHAIN_ID, BLOCK_TIME, GENESIS_TIME, VALIDATORS, USERS, DASHBOARD_BASE_PORT
from blockchain import Blockchain
from node import events_since
from transaction import Transaction, ADDR_RE

MAX_BODY = 100_000
NAMES = {v["addr"]: v["name"] for v in VALIDATORS}


def tx_json(t):
    return {"id": t.tx_id(), "from": t.sender, "to": t.to, "amount": t.amount, "nonce": t.nonce}


def start_api(node, port):
    boot = int(time.time() * 1000)     # lets the browser notice a node restart

    def account(addr):
        with node.lock:
            pending = sum(1 for t in node.mempool.txs.values() if t.sender == addr)
            conf = node.bc.state.nonce(addr)
            return {"address": addr, "balance": node.bc.state.balance(addr),
                    "nonce": conf, "pending": pending, "next_nonce": conf + pending}

    def chain(limit):
        with node.lock:
            blocks = node.bc.chain[-limit:]
            return [{"height": b.height, "hash": b.hash(), "slot": b.slot,
                     "proposer": NAMES.get(b.proposer, b.proposer), "merkle": b.merkle_root,
                     "sig": b.signature, "ts": b.timestamp,
                     "txs": [tx_json(t) for t in b.txs]} for b in reversed(blocks)]

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj, ctype="application/json"):
            body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                u = urlparse(self.path)
                p, q = u.path, parse_qs(u.query)
                if p in ("/", "/index.html"):
                    self._send(200, PAGE.encode(), "text/html; charset=utf-8")
                elif p == "/api/info":
                    self._send(200, {
                        "chain_id": CHAIN_ID, "genesis_time": GENESIS_TIME, "block_time": BLOCK_TIME,
                        "validators": [{"name": v["name"], "addr": v["addr"],
                                        "api_port": DASHBOARD_BASE_PORT + i}
                                       for i, v in enumerate(VALIDATORS)],
                        "users": {n: u_["addr"] for n, u_ in USERS.items()}})
                elif p == "/api/status":
                    d = node.status()
                    d["boot"] = boot
                    d["slot"] = Blockchain.slot_for_time(int(time.time()))
                    self._send(200, d)
                elif p == "/api/chain":
                    limit = max(1, min(50, int(q.get("limit", ["10"])[0])))
                    self._send(200, chain(limit))
                elif p == "/api/mempool":
                    with node.lock:
                        self._send(200, [tx_json(t) for t in node.mempool.txs.values()])
                elif p == "/api/balances":
                    with node.lock:
                        self._send(200, {a: dict(v) for a, v in node.bc.state.accounts.items()})
                elif p.startswith("/api/balance/"):
                    addr = p.rsplit("/", 1)[1]
                    if not ADDR_RE.fullmatch(addr):
                        return self._send(400, {"error": "invalid address"})
                    self._send(200, account(addr))
                elif p.startswith("/api/history/"):
                    addr = p.rsplit("/", 1)[1]
                    if not ADDR_RE.fullmatch(addr):
                        return self._send(400, {"error": "invalid address"})
                    out = []
                    with node.lock:
                        for t in node.mempool.txs.values():           # pending first
                            if t.sender == addr or t.to == addr:
                                d = tx_json(t)
                                d.update(status="pending", block=None, ts=None, proposer=None)
                                out.append(d)
                        for b in reversed(node.bc.chain):             # then newest confirmed
                            for t in reversed(b.txs):
                                if t.sender == addr or t.to == addr:
                                    d = tx_json(t)
                                    d.update(status="confirmed", block=b.height, ts=b.timestamp,
                                             proposer=NAMES.get(b.proposer, b.proposer))
                                    out.append(d)
                            if len(out) >= 50:
                                break
                    self._send(200, out[:50])
                elif p == "/api/events":
                    since = int(q.get("since", ["0"])[0])
                    self._send(200, events_since(node.name, since))
                else:
                    self._send(404, {"error": "not found"})
            except ValueError:
                self._send(400, {"error": "bad parameter"})
            except Exception as e:
                self._send(500, {"error": type(e).__name__})

        def do_POST(self):
            if urlparse(self.path).path != "/api/tx":
                return self._send(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= MAX_BODY:
                    return self._send(413, {"ok": False, "reason": "bad body size"})
                tx = Transaction.from_dict(json.loads(self.rfile.read(n)))
                tid = tx.tx_id()
            except Exception as e:
                return self._send(400, {"ok": False, "reason": f"malformed transaction ({type(e).__name__})"})
            ok, reason = node.submit_tx(tx)      # full validation + gossip happens inside
            self._send(200 if ok else 400, {"ok": ok, "reason": reason, "tx_id": tid})

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    Thread(target=srv.serve_forever, daemon=True).start()
    return srv


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>PoA Chain - live</title>
<style>
:root{--bg:#0f1218;--card:#181d27;--line:#2a3142;--tx:#e6e9ef;--dim:#8b94a7;--ok:#4ade80;--bad:#f87171;--mine:#fbbf24;--blue:#60a5fa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,"Segoe UI",sans-serif;padding:16px}
h1{font-size:18px;margin:0 0 10px}
.mono{font-family:Consolas,monospace}.dim{color:var(--dim)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0}
.grid2{display:grid;grid-template-columns:3fr 2fr;gap:12px}
.turn{border-color:var(--mine);box-shadow:0 0 0 1px var(--mine)}
.off{opacity:.5}
.bar{height:8px;background:#222a3a;border-radius:4px;overflow:hidden;margin-top:6px}
.bar>div{height:100%;background:var(--blue);width:0}
.blk{border-left:3px solid var(--blue);padding:4px 8px;margin:6px 0;background:#141924}
.tx{margin-left:10px;color:#cbd5e1}
#feed{height:320px;overflow:auto;font-family:Consolas,monospace;font-size:12px;margin-top:6px}
.ev{padding:1px 0;white-space:pre-wrap}
.good{color:var(--ok)}.bad{color:var(--bad)}.mine{color:var(--mine)}.txc{color:var(--blue)}
@media(max-width:800px){.grid3,.grid2{grid-template-columns:1fr}}
</style></head><body>
<h1>PoA Chain - live view</h1>
<div class="card"><div id="clock" class="mono"></div><div class="bar"><div id="bar"></div></div></div>
<div class="grid3" id="nodes"></div>
<div class="grid2">
  <div class="card"><b>Latest blocks</b> <span class="dim" id="src"></span><div id="blocks"></div></div>
  <div>
    <div class="card"><b>Mempool</b> <span class="dim">(pending, unconfirmed)</span><div id="mempool"></div></div>
    <div class="card" style="margin-top:12px"><b>Account balances</b> <span class="dim">(confirmed)</span><div id="bals"></div></div>
  </div>
</div>
<div class="card" style="margin-top:12px"><b>Event feed</b> <span class="dim">(all nodes, newest first)</span><div id="feed"></div></div>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const HOST = location.hostname;
let INFO = null, NAMES = {}, lastSeq = {}, boot = {}, events = [];
const nm = a => NAMES[a] || (a ? a.slice(0, 8) + '…' : '?');

async function get(port, path) {
  const c = new AbortController(), t = setTimeout(() => c.abort(), 900);
  try { const r = await fetch(`http://${HOST}:${port}${path}`, {signal: c.signal, cache: 'no-store'}); return await r.json(); }
  catch (e) { return null; } finally { clearTimeout(t); }
}
function slotNow() {
  const t = Date.now() / 1000 - INFO.genesis_time;
  return {slot: Math.floor(t / INFO.block_time), frac: (t % INFO.block_time) / INFO.block_time};
}
function turnOf(slot) { return INFO.validators[slot % INFO.validators.length].name; }
function drawClock() {
  if (!INFO) return;
  const s = slotNow();
  $('clock').textContent = `slot ${s.slot}  -  ${turnOf(s.slot)}'s turn to propose  -  chain ${INFO.chain_id}`;
  $('bar').style.width = (s.frac * 100) + '%';
}
function evClass(t) {
  if (/REJECTED|CONFLICTS|malformed|error|different genesis/i.test(t)) return 'bad';
  if (/ACCEPTED|synced/.test(t)) return 'good';
  if (/MINE|built block|committed|signed/.test(t)) return 'mine';
  if (/validated|submitted/.test(t)) return 'txc';
  return 'dim';
}
async function tick() {
  const cur = turnOf(slotNow().slot);
  const res = await Promise.all(INFO.validators.map(async v => {
    const s = await get(v.api_port, '/api/status');
    let ev = [];
    if (s) {
      if (boot[v.name] !== s.boot) { boot[v.name] = s.boot; lastSeq[v.name] = 0; }
      ev = (await get(v.api_port, `/api/events?since=${lastSeq[v.name] || 0}`)) || [];
      if (ev.length) lastSeq[v.name] = ev[ev.length - 1].seq;
    }
    return {v, s, ev};
  }));

  $('nodes').innerHTML = res.map(({v, s}) => {
    const turn = v.name === cur ? ' turn' : '';
    if (!s) return `<div class="card off${turn}"><b>${v.name}</b> <span class="bad">OFFLINE</span></div>`;
    return `<div class="card${turn}"><b>${v.name}</b> <span class="good">ONLINE</span>` +
      (turn ? ' <span class="mine">&larr; proposing this slot</span>' : '') +
      `<div class="mono">height ${s.height}<br>tip &nbsp;&nbsp;${esc(s.tip)}<br>state ${esc(s.state)}<br>mempool ${s.mempool} &middot; peers ${s.peers}</div></div>`;
  }).join('');

  const fresh = [];
  res.forEach(({v, ev}) => ev.forEach(e => fresh.push({node: v.name, t: e.t, ms: e.ms, text: e.text})));
  fresh.sort((a, b) => a.ms - b.ms);
  events = events.concat(fresh).slice(-300);
  $('feed').innerHTML = events.slice(-200).reverse().map(e =>
    `<div class="ev ${evClass(e.text)}">${e.t} ${esc(e.node).padStart(3)} | ${esc(e.text)}</div>`).join('');

  const up = res.filter(r => r.s).sort((a, b) => b.s.height - a.s.height)[0];
    if (!up) { $('src').textContent = '(ALL NODES OFFLINE - showing last known data)'; return; }
  const port = up.v.api_port;
  const [chain, pool, bals] = await Promise.all([
    get(port, '/api/chain?limit=10'), get(port, '/api/mempool'), get(port, '/api/balances')]);
  $('src').textContent = `(from ${up.v.name})`;
  if (chain) $('blocks').innerHTML = chain.map(b =>
    `<div class="blk"><div>#${b.height} <span class="mono">${esc(b.hash.slice(0, 10))}</span> &middot; slot ${b.slot} &middot; by <b>${esc(b.proposer)}</b>` +
    `<div class="dim mono">merkle ${esc(b.merkle.slice(0, 10))} &middot; sig ${esc((b.sig || '-').slice(0, 10))} &middot; prev-linked</div></div>` +
    b.txs.map(t => `<div class="tx">${esc(nm(t.from))} &rarr; ${esc(nm(t.to))}: <b>${t.amount}</b> <span class="mono dim">(${esc(t.id.slice(0, 8))}, nonce ${t.nonce})</span></div>`).join('') +
    `</div>`).join('');
  if (pool) $('mempool').innerHTML = pool.length ? pool.map(t =>
    `<div class="tx">${esc(nm(t.from))} &rarr; ${esc(nm(t.to))}: <b>${t.amount}</b> <span class="mono dim">(${esc(t.id.slice(0, 8))})</span></div>`).join('')
    : '<span class="dim">empty</span>';
  if (bals) $('bals').innerHTML = Object.entries(bals).sort((a, b) => b[1].balance - a[1].balance).map(([a, v]) =>
    `<div class="tx">${esc(nm(a))}: <b>${v.balance}</b> <span class="dim">(nonce ${v.nonce})</span></div>`).join('');
}
async function loop() { try { await tick(); } catch (e) {} setTimeout(loop, 1000); }
fetch('/api/info').then(r => r.json()).then(i => {
  INFO = i;
  Object.entries(i.users).forEach(([n, a]) => NAMES[a] = n);
  i.validators.forEach(v => NAMES[v.addr] = v.name);
  setInterval(drawClock, 200); loop();
});
</script></body></html>"""