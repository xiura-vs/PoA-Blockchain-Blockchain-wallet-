"""
dapp_demo.py - "Byte Coffee", a fake website that asks the wallet to connect and pay.
It is a separate origin (port 9100) and holds NO keys: it can only ask.

    python dapp_demo.py     ->  http://127.0.0.1:9100
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config import USERS

SHOP = USERS["carol"]["addr"]          # the shop's receiving address

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Byte Coffee</title>
<style>
body{margin:0;background:#1b1410;color:#f3e9dc;font:15px/1.5 system-ui,"Segoe UI",sans-serif;display:flex;justify-content:center;padding:40px}
.wrap{width:520px}
h1{margin:0 0 4px}.dim{color:#b8a58f}.mono{font-family:Consolas,monospace;font-size:12px;word-break:break-all}
.card{background:#271d16;border:1px solid #3d2e22;border-radius:14px;padding:18px;margin-top:16px}
button{padding:11px 18px;border:0;border-radius:22px;background:#f6851b;color:#111;font-weight:600;font-size:14px;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}
.cup{font-size:56px}.ok{color:#4ade80}.bad{color:#f87171}.pend{color:#fbbf24}
</style></head><body><div class="wrap">
<h1>☕ Byte Coffee</h1><div class="dim">Pay with PoA Coin. This site never sees your keys.</div>
<div class="card"><div id="acct" class="dim">Not connected</div>
  <button id="conn" style="margin-top:10px">Connect wallet</button></div>
<div class="card" style="display:flex;align-items:center;gap:16px">
  <div class="cup">☕</div><div style="flex:1"><b>Flat white</b><div class="dim">5 PC</div></div>
  <button id="buy" disabled>Buy now</button></div>
<div class="card"><b>Status</b><div id="log" class="dim" style="margin-top:6px">Nothing yet.</div></div>
</div>
<script>
const WALLET = 'http://127.0.0.1:9000', NODE = 'http://127.0.0.1:8000', SHOP = '__SHOP__';
let me = null;
const $ = id => document.getElementById(id);
const say = (t, cls) => { $('log').textContent = t; $('log').className = cls || 'dim'; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function ask(type, params) {             // file a request, then wait for the user's decision
  const r = await fetch(WALLET + '/api/dapp/request', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({type, params})});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error);
  for (let i = 0; i < 125; i++) {
    await sleep(1000);
    const x = await (await fetch(WALLET + '/api/dapp/result/' + d.id)).json();
    if (!x.status) throw new Error(x.error || 'lost request');
    if (x.status === 'approved') return x.result;
    if (x.status === 'rejected' || x.status === 'failed') throw new Error(x.error || x.status);
  }
  throw new Error('timed out waiting for the wallet');
}
async function balance() {
  try { const b = await (await fetch(NODE + '/api/balance/' + me)).json(); return b.balance; } catch (e) { return null; }
}
async function showAcct() {
  const b = await balance();
  $('acct').innerHTML = '<span class="ok">Connected</span> <span class="mono">' + me + '</span><br>Balance: ' + (b == null ? '?' : b + ' PC');
}
$('conn').onclick = async () => {
  try {
    say('Approve the connection in your wallet window…', 'pend');
    const r = await ask('connect', {});
    me = r.accounts[0]; $('buy').disabled = false; $('conn').textContent = 'Reconnect';
    say('Connected.', 'ok'); showAcct();
  } catch (e) { say('Could not connect: ' + e.message, 'bad'); }
};
$('buy').onclick = async () => {
  $('buy').disabled = true;
  try {
    say('Confirm the payment in your wallet window…', 'pend');
    const r = await ask('send_tx', {from: me, to: SHOP, amount: 5});
    say('Payment sent (tx ' + r.tx_id.slice(0, 10) + '…). Waiting for a validator to confirm…', 'pend');
    for (let i = 0; i < 60; i++) {
      await sleep(2000);
      const h = await (await fetch(NODE + '/api/history/' + me)).json();
      const t = h.find(x => x.id === r.tx_id);
      if (t && t.status === 'confirmed') {
        say('Paid ✓ confirmed in block ' + t.block + ' by ' + t.proposer + '. Enjoy your coffee!', 'ok');
        showAcct(); break;
      }
    }
  } catch (e) { say('Payment failed: ' + e.message, 'bad'); }
  $('buy').disabled = false;
};
</script></body></html>""".replace("__SHOP__", SHOP)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("Byte Coffee on http://127.0.0.1:9100  (shop address:", SHOP + ")")
    srv = ThreadingHTTPServer(("127.0.0.1", 9100), H)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nshop closed.")
    finally:
        srv.server_close()