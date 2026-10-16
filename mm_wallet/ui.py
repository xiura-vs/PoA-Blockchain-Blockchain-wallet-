PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>PoA Wallet</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0f1218;--card:#181d27;--line:#2a3142;--tx:#e6e9ef;--dim:#8b94a7;--ok:#4ade80;--bad:#f87171;--acc:#f6851b;--blue:#60a5fa}
*{box-sizing:border-box}
body{margin:0;background:#0b0e13;color:var(--tx);font:14px/1.45 system-ui,"Segoe UI",sans-serif;display:flex;justify-content:center;padding:24px}
#frame{width:380px;min-height:640px;background:var(--bg);border:1px solid var(--line);border-radius:14px;padding:18px}
h2{margin:6px 0 8px;font-size:20px}
p{margin:6px 0}
.dim{color:var(--dim)}.mono{font-family:Consolas,monospace;font-size:12px}
label{display:block;margin:12px 0 4px;color:var(--dim);font-size:12px}
input,textarea{width:100%;background:var(--card);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:10px;font:inherit}
textarea{height:90px;resize:none}
input:focus,textarea:focus{outline:1px solid var(--acc)}
.chk{display:flex;gap:8px;align-items:flex-start;color:var(--tx);font-size:13px}
.chk input{width:auto;margin-top:3px}
.btn{width:100%;margin-top:12px;padding:11px;border:0;border-radius:22px;background:var(--acc);color:#111;font-weight:600;font-size:14px;cursor:pointer}
.btn.ghost{background:transparent;color:var(--acc);border:1px solid var(--acc)}
.btn:disabled{opacity:.45;cursor:not-allowed}
.link{background:none;border:0;color:var(--blue);cursor:pointer;font:inherit;padding:0}
a{color:var(--blue);cursor:pointer}
.err{color:var(--bad);min-height:18px;margin-top:8px;font-size:13px}
.ok{color:var(--ok);min-height:18px;margin-top:8px;font-size:13px}
.warn{background:#2a1f12;border:1px solid #6b4a1d;color:#fbbf24;padding:8px;border-radius:8px;margin:8px 0;font-size:12px}
.logo{font-size:48px;text-align:center;margin-top:50px}
.center{text-align:center}
.srp{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}
.srp div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;font-family:Consolas,monospace}
.srp span{color:var(--dim);margin-right:6px;font-size:11px}
.blur{filter:blur(8px);user-select:none}
.top{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.accbtn{flex:1;background:var(--card);border:1px solid var(--line);color:var(--tx);border-radius:20px;padding:7px 12px;cursor:pointer;text-align:left}
.icon{background:var(--card);border:1px solid var(--line);color:var(--tx);border-radius:50%;width:34px;height:34px;cursor:pointer}
.net{font-size:11px;color:var(--dim);margin-bottom:6px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;background:var(--dim)}
.hero{text-align:center;padding:10px 0 6px}
.bal{font-size:34px;font-weight:700;margin-top:6px}
.tabs{display:flex;border-bottom:1px solid var(--line);margin:12px 0}
.tabs button{flex:1;background:none;border:0;border-bottom:2px solid transparent;color:var(--dim);padding:9px;cursor:pointer;font:inherit}
.tabs button.on{color:var(--acc);border-bottom-color:var(--acc)}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;word-break:break-all}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:10px;border-bottom:1px solid var(--line)}
.acct{cursor:pointer;border:1px solid var(--line);border-radius:8px;margin:6px 0}
.acct.sel{border-color:var(--acc)}
.tag{background:#222a3a;border-radius:4px;padding:1px 6px;font-size:10px;color:var(--dim)}
.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.foot{margin-top:18px;text-align:center;font-size:12px}
.pend{color:#fbbf24}.conf{color:var(--ok)}
hr{border:0;border-top:1px solid var(--line);margin:16px 0}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;justify-content:center;align-items:center;z-index:99}
.modal .sheet{width:350px;max-height:90vh;overflow:auto;background:var(--bg);border:1px solid var(--acc);border-radius:14px;padding:16px}
</style></head><body><div id="frame"></div>
<script>
const S = {token: sessionStorage.getItem('tok'), accounts: [], sel: null, autolock: 300,
           last: Date.now(), tab: 'activity', hist: [], view: '', phrase: null};
const el = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short = a => a ? a.slice(0, 8) + '…' + a.slice(-4) : '';
const ADDR = /^PC[0-9a-f]{40}$/;
const show = html => { el('frame').innerHTML = html; };
const err = m => { const e = el('err'); if (e) e.textContent = m || ''; };
const busy = (id, b) => { const x = el(id); if (x) x.disabled = b; };
const cur = () => S.accounts.find(a => a.address === S.sel) || S.accounts[0];
const nameOf = a => { const m = S.accounts.find(x => x.address === a); return m ? m.name : short(a); };

function setToken(t) {
  S.token = t; S.last = Date.now();
  if (t) sessionStorage.setItem('tok', t); else sessionStorage.removeItem('tok');
}
async function api(method, path, body) {
  const h = {};
  if (body !== undefined) h['Content-Type'] = 'application/json';
  if (S.token) h['X-Session'] = S.token;
  let r;
  try { r = await fetch(path, {method, headers: h, body: body !== undefined ? JSON.stringify(body) : undefined}); }
  catch (e) { return {ok: false, status: 0, data: {error: 'wallet service unreachable'}}; }
  let d = {};
  try { d = await r.json(); } catch (e) {}
  if (r.status === 401 && d.error === 'wallet is locked' && S.view !== 'lock') gotoLocked();
  return {ok: r.ok, status: r.status, data: d};
}
function copy(text, btn) {
  const old = btn.textContent;
  navigator.clipboard.writeText(text)
    .then(() => { btn.textContent = 'Copied ✓'; setTimeout(() => btn.textContent = old, 1200); })
    .catch(() => { btn.textContent = 'Copy failed'; });
}
function gotoLocked() { setToken(null); S.accounts = []; S.sel = null; S.phrase = null; S.hist = []; vLock(); }
async function reloadAccounts() {
  const r = await api('GET', '/api/accounts');
  if (r.ok) {
    S.accounts = r.data.accounts;
    if (!S.accounts.find(a => a.address === S.sel)) S.sel = S.accounts[0] && S.accounts[0].address;
  }
  return r.ok;
}

/* ---------- onboarding ---------- */
function vWelcome() {
  S.view = 'welcome';
  show(`<div class="logo">⛓️</div><h2 class="center">PoA Wallet</h2>
    <p class="dim center">A self-custody wallet for the PoA chain.<br>Your keys stay on this computer.</p>
    <button id="c" class="btn" style="margin-top:50px">Create a new wallet</button>
    <button id="i" class="btn ghost">Import using Secret Recovery Phrase</button>`);
  el('c').onclick = vCreate; el('i').onclick = vImport;
}
function vCreate() {
  S.view = 'create';
  show(`<h2>Create a password</h2>
    <p class="dim">This password unlocks the wallet on this computer only. It cannot recover your wallet.</p>
    <label>New password (8+ characters)</label><input id="p1" type="password">
    <label>Confirm password</label><input id="p2" type="password">
    <label class="chk"><input id="ok" type="checkbox"> I understand that nobody can recover this password for me.</label>
    <div id="err" class="err"></div>
    <button id="go" class="btn">Create wallet</button><button id="bk" class="btn ghost">Back</button>`);
  el('bk').onclick = vWelcome;
  el('go').onclick = async () => {
    const p1 = el('p1').value, p2 = el('p2').value;
    if (p1.length < 8) return err('Password must be at least 8 characters');
    if (p1 !== p2) return err('Passwords do not match');
    if (!el('ok').checked) return err('Please tick the box to continue');
    busy('go', true);
    const r = await api('POST', '/api/create', {password: p1});
    if (!r.ok) { busy('go', false); return err(r.data.error); }
    setToken(r.data.token); S.phrase = r.data.mnemonic; S.accounts = r.data.accounts;
    vSrp();
  };
}
function vSrp() {
  S.view = 'srp';
  const words = S.phrase.split(' ');
  show(`<h2>Secret Recovery Phrase</h2>
    <div class="warn">Write these 12 words on paper, in order. Anyone who has them controls your funds. Never share or screenshot them. There is no recovery without them.</div>
    <div id="srp" class="srp blur">${words.map((w, i) => `<div><span>${i + 1}</span>${esc(w)}</div>`).join('')}</div>
    <button id="rev" class="btn ghost">Reveal phrase</button>
    <button id="cp" class="btn ghost">Copy to clipboard</button>
    <button id="nx" class="btn" disabled>I wrote it down</button>`);
  el('rev').onclick = () => { el('srp').classList.remove('blur'); el('nx').disabled = false; el('rev').style.display = 'none'; };
  el('cp').onclick = () => copy(S.phrase, el('cp'));
  el('nx').onclick = vQuiz;
}
function vQuiz() {
  S.view = 'quiz';
  const words = S.phrase.split(' ');
  const idx = [...Array(12).keys()].sort(() => Math.random() - .5).slice(0, 3).sort((a, b) => a - b);
  show(`<h2>Confirm your phrase</h2><p class="dim">Type the words at these positions to prove you saved it.</p>
    ${idx.map(i => `<label>Word #${i + 1}</label><input class="q" data-i="${i}" autocomplete="off">`).join('')}
    <div id="err" class="err"></div>
    <button id="ck" class="btn">Confirm</button><button id="bk" class="btn ghost">Show phrase again</button>`);
  el('bk').onclick = vSrp;
  el('ck').onclick = () => {
    const ok = [...document.querySelectorAll('.q')].every(q => q.value.trim().toLowerCase() === words[+q.dataset.i]);
    if (!ok) return err('One or more words are wrong. Check your written copy.');
    S.phrase = null; vMain();
  };
}
function vImport() {
  S.view = 'import';
  show(`<h2>Import a wallet</h2><p class="dim">Enter your 12-word Secret Recovery Phrase and choose a password for this computer.</p>
    <label>Secret Recovery Phrase</label><textarea id="ph" autocomplete="off" spellcheck="false"></textarea>
    <label>New password (8+ characters)</label><input id="p1" type="password">
    <label>Confirm password</label><input id="p2" type="password">
    <div id="err" class="err"></div>
    <button id="go" class="btn">Import wallet</button><button id="bk" class="btn ghost">Back</button>`);
  el('bk').onclick = vWelcome;
  el('go').onclick = async () => {
    const p1 = el('p1').value, p2 = el('p2').value;
    if (p1.length < 8) return err('Password must be at least 8 characters');
    if (p1 !== p2) return err('Passwords do not match');
    busy('go', true);
    const r = await api('POST', '/api/restore', {password: p1, mnemonic: el('ph').value});
    if (!r.ok) { busy('go', false); return err(r.data.error); }
    setToken(r.data.token); S.accounts = r.data.accounts; vMain();
    if (r.data.discovered) setTimeout(() => alert(`Recovered ${r.data.discovered} more account(s) that were used on-chain.`), 300);
  };
}
function vLock() {
  S.view = 'lock';
  show(`<div class="logo">⛓️</div><h2 class="center">Welcome back</h2>
    <label>Password</label><input id="pw" type="password" autofocus>
    <div id="err" class="err"></div>
    <button id="go" class="btn">Unlock</button>
    <p class="dim center" style="margin-top:24px;font-size:12px">Forgot your password? Stop the service, delete <span class="mono">wallet_vault.json</span>, restart, and import your Secret Recovery Phrase.</p>`);
  const go = async () => {
    busy('go', true);
    const r = await api('POST', '/api/unlock', {password: el('pw').value});
    busy('go', false);
    if (!r.ok) return err(r.data.error);
    setToken(r.data.token); S.accounts = r.data.accounts; S.sel = null; vMain();
  };
  el('go').onclick = go;
  el('pw').onkeydown = e => { if (e.key === 'Enter') go(); };
}

/* ---------- main screen ---------- */
async function vMain() {
  S.view = 'main'; S.last = Date.now();
  if (!S.sel && S.accounts[0]) S.sel = S.accounts[0].address;
  show(`<div id="netb" class="net"><span class="dot"></span>checking network…</div>
    <div class="top"><button id="acc" class="accbtn">…</button><button id="lk" class="icon" title="Lock">🔒</button></div>
    <div class="hero"><div id="aaddr" class="mono dim"></div><div id="bal" class="bal">…</div><div id="pend" class="dim"></div></div>
    <div class="tabs"><button data-t="activity">Activity</button><button data-t="send">Send</button><button data-t="receive">Receive</button></div>
    <div id="tab"></div>
    <div class="foot dim">Auto-lock in <span id="cd"></span> · <a id="sec">Security</a></div>`);
  el('acc').onclick = vAccounts; el('sec').onclick = vSecurity;
  el('lk').onclick = async () => { await api('POST', '/api/lock', {}); gotoLocked(); };
  document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => setTab(b.dataset.t));
  paintHero(); setTab(S.tab);
  await refresh();
}
function paintHero() {
  if (S.view !== 'main') return;
  const a = cur(); if (!a) return;
  el('acc').textContent = a.name + ' ▾';
  el('aaddr').textContent = a.address;
  el('bal').textContent = a.balance == null ? '—' : a.balance + ' PC';
  el('pend').textContent = a.pending ? `${a.pending} pending transaction(s)` : '';
}
function paintNet(nodes) {
  const b = el('netb'); if (!b || S.view !== 'main') return;
  const up = nodes.filter(n => n.up), h = Math.max(0, ...up.map(n => n.height));
  const col = up.length === nodes.length ? 'var(--ok)' : up.length ? '#fbbf24' : 'var(--bad)';
  b.innerHTML = `<span class="dot" style="background:${col}"></span>PoA chain · ${up.length}/${nodes.length} nodes online` + (up.length ? ` · height ${h}` : ' · start the nodes');
}
function paintHist() {
  const box = el('hist'); if (!box) return;
  const me = S.sel;
  if (!S.hist.length) { box.innerHTML = '<p class="dim center" style="margin-top:30px">No transactions yet</p>'; return; }
  box.innerHTML = S.hist.map(t => {
    const out = t.from === me, self = t.from === t.to;
    const label = self ? 'Self transfer' : out ? 'Sent' : 'Received';
    const peer = out ? t.to : t.from;
    const status = t.status === 'pending' ? '<span class="pend">Pending…</span>'
      : `<span class="conf">Confirmed</span> · block ${t.block}${t.proposer ? ' · ' + esc(t.proposer) : ''}`;
    return `<div class="row"><div><b>${label}</b> <span class="dim">${out ? 'to' : 'from'} ${esc(nameOf(peer))}</span>
      <div class="dim" style="font-size:12px">${status}</div>
      <div class="mono dim">${t.id.slice(0, 10)}${t.ts ? ' · ' + new Date(t.ts * 1000).toLocaleString() : ''}</div></div>
      <div><b>${out && !self ? '−' : out ? '' : '+'}${t.amount}</b></div></div>`;
  }).join('');
}
async function refresh() {
  if (S.view !== 'main' || !S.token) return;
  if (await reloadAccounts()) paintHero();
  const me = S.sel;
  if (me) {
    const h = await api('GET', '/api/history/' + me);
    if (h.ok && Array.isArray(h.data) && S.sel === me) { S.hist = h.data; paintHist(); }
  }
  const n = await api('GET', '/api/network');
  if (n.ok) paintNet(n.data.nodes);
}

/* ---------- tabs ---------- */
function setTab(t) {
  S.tab = t;
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.t === t));
  if (t === 'activity') { el('tab').innerHTML = '<div id="hist"></div>'; paintHist(); }
  else if (t === 'receive') tReceive();
  else tSend();
}
function tReceive() {
  const a = cur(); if (!a) return;
  el('tab').innerHTML = `<p class="dim center">Share this address to receive PC</p>
    <div class="box mono center">${esc(a.address)}</div>
    <button id="cp" class="btn ghost">Copy address</button>`;
  el('cp').onclick = () => copy(a.address, el('cp'));
}
function tSend() {
  const a = cur(); if (!a) return;
  el('tab').innerHTML = `<label>From</label><div class="box">${esc(a.name)} <span class="mono dim">${short(a.address)}</span></div>
    <label>To (address)</label><input id="to" list="own" placeholder="PC…" autocomplete="off">
    <datalist id="own">${S.accounts.filter(x => x.address !== a.address).map(x => `<option value="${x.address}">${esc(x.name)}</option>`).join('')}</datalist>
    <label>Amount (whole coins)</label><input id="amt" inputmode="numeric" placeholder="0">
    <div class="dim" style="margin-top:6px;font-size:12px">Network fee: none (demo chain)</div>
    <div id="err" class="err"></div><button id="nx" class="btn">Review</button>`;
  el('nx').onclick = () => {
    const to = el('to').value.trim(), s = el('amt').value.trim();
    if (!ADDR.test(to)) return err('Enter a valid recipient address (PC + 40 hex characters)');
    if (!/^[1-9][0-9]{0,14}$/.test(s)) return err('Amount must be a positive whole number');
    const amount = parseInt(s, 10);
    if (a.balance != null && amount > a.balance) return err('Insufficient funds');
    tConfirm(a, to, amount);
  };
}
function tConfirm(a, to, amount) {
  el('tab').innerHTML = `<h2 style="font-size:16px">Confirm transaction</h2>
    <div class="box"><div class="dim">From</div>${esc(a.name)} <span class="mono">${short(a.address)}</span>
    <div class="dim" style="margin-top:8px">To</div><span class="mono">${esc(nameOf(to) === short(to) ? to : nameOf(to) + ' · ' + short(to))}</span>
    <div class="dim" style="margin-top:8px">Amount</div><b style="font-size:20px">${amount} PC</b></div>
    <p class="dim" style="font-size:12px">The wallet will sign this locally. The network checks the signature, nonce and balance independently.</p>
    <div id="err" class="err"></div>
    <button id="ok" class="btn">Confirm</button><button id="no" class="btn ghost">Reject</button>`;
  el('no').onclick = tSend;
  el('ok').onclick = async () => {
    busy('ok', true); busy('no', true);
    const r = await api('POST', '/api/send', {from: a.address, to, amount});
    if (!r.ok) { busy('ok', false); busy('no', false); return err(r.data.reason || r.data.error || 'send failed'); }
    setTab('activity'); await refresh();
  };
}

/* ---------- accounts / security ---------- */
function vAccounts() {
  S.view = 'accounts';
  show(`<div class="bar"><button id="bk" class="link">‹ Back</button><b>My accounts</b><span></span></div>
    ${S.accounts.map(a => `<div class="row acct ${a.address === S.sel ? 'sel' : ''}" data-a="${a.address}">
      <div><b>${esc(a.name)}</b>${a.kind === 'imported' ? ' <span class="tag">imported</span>' : ''}<div class="mono dim">${short(a.address)}</div></div>
      <div>${a.balance == null ? '—' : a.balance + ' PC'}</div></div>`).join('')}
    <div id="err" class="err"></div>
    <button id="add" class="btn ghost">+ Create account</button>
    <button id="imp" class="btn ghost">Import account (private key)</button>
    <button id="ren" class="btn ghost">Rename current account</button>`);
  el('bk').onclick = vMain;
  document.querySelectorAll('.acct').forEach(d => d.onclick = () => { S.sel = d.dataset.a; vMain(); });
  el('add').onclick = async () => {
    const name = prompt('Account name (optional)'); if (name === null) return;
    const r = await api('POST', '/api/accounts/add', {name});
    if (!r.ok) return err(r.data.error);
    await reloadAccounts(); vAccounts();
  };
  el('ren').onclick = async () => {
    const a = cur(), name = prompt('New name for ' + a.name, a.name); if (!name) return;
    const r = await api('POST', '/api/accounts/rename', {address: a.address, name});
    if (!r.ok) return err(r.data.error);
    await reloadAccounts(); vAccounts();
  };
  el('imp').onclick = vImportKey;
}
function vImportKey() {
  S.view = 'importkey';
  show(`<div class="bar"><button id="bk" class="link">‹ Back</button><b>Import account</b><span></span></div>
    <div class="warn">Imported accounts are NOT covered by your Secret Recovery Phrase. Back up the private key separately.</div>
    <label>Private key (64 hex characters)</label><input id="pk" type="password" autocomplete="off">
    <label>Name (optional)</label><input id="nm">
    <div id="err" class="err"></div><button id="go" class="btn">Import</button>`);
  el('bk').onclick = vAccounts;
  el('go').onclick = async () => {
    busy('go', true);
    const r = await api('POST', '/api/accounts/import', {private_key: el('pk').value, name: el('nm').value});
    if (!r.ok) { busy('go', false); return err(r.data.error); }
    S.sel = r.data.address; await reloadAccounts(); vMain();
  };
}
async function loadSites() {
  const r = await api('GET', '/api/dapp/permissions'), box = el('sites');
  if (!box || !r.ok) return;
  box.innerHTML = r.data.sites.length ? r.data.sites.map(s =>
    `<div class="row"><div class="mono">${esc(s.origin)}<div class="dim">${s.accounts.length} account(s)</div></div>
     <button class="link" data-o="${esc(s.origin)}">Disconnect</button></div>`).join('') : 'No connected sites';
  box.querySelectorAll('button').forEach(b => b.onclick = async () => {
    await api('POST', '/api/dapp/revoke', {origin: b.dataset.o}); loadSites();
  });
}
function vSecurity() {
  S.view = 'security';
  show(`<div class="bar"><button id="bk" class="link">‹ Back</button><b>Security</b><span></span></div>
    <p class="dim">Enter your password to view secrets.</p>
    <input id="pw" type="password" placeholder="Password">
    <button id="rs" class="btn ghost">Reveal Secret Recovery Phrase</button>
    <button id="ek" class="btn ghost">Export private key of current account</button>
    <div id="err" class="err"></div><div id="secret"></div>
    <hr><b>Change password</b>
    <input id="op" type="password" placeholder="Current password" style="margin-top:8px">
    <input id="np" type="password" placeholder="New password (8+ characters)" style="margin-top:8px">
    <button id="cpw" class="btn ghost">Change password</button><div id="msg" class="ok"></div>
    <hr><b>Connected sites</b><div id="sites" class="dim">loading…</div>`);
  el('bk').onclick = vMain;
  loadSites();
  const showSecret = html => { el('secret').innerHTML = html + '<button id="hide" class="btn ghost">Hide</button>';
    el('hide').onclick = () => { el('secret').innerHTML = ''; }; };
  el('rs').onclick = async () => {
    err(''); const r = await api('POST', '/api/reveal', {password: el('pw').value}); el('pw').value = '';
    if (!r.ok) return err(r.data.error);
    showSecret(`<div class="warn">Anyone with these words controls your funds.</div><div class="srp">${r.data.mnemonic.split(' ').map((w, i) => `<div><span>${i + 1}</span>${esc(w)}</div>`).join('')}</div>`);
  };
  el('ek').onclick = async () => {
    err(''); const r = await api('POST', '/api/export', {address: cur().address, password: el('pw').value}); el('pw').value = '';
    if (!r.ok) return err(r.data.error);
    showSecret(`<div class="warn">Private key for ${esc(cur().name)}. Never share it.</div><div class="box mono">${esc(r.data.private_key)}</div>`);
  };
  el('cpw').onclick = async () => {
    el('msg').textContent = ''; err('');
    const r = await api('POST', '/api/change_password', {old: el('op').value, new: el('np').value});
    el('op').value = ''; el('np').value = '';
    if (!r.ok) return err(r.data.error);
    el('msg').textContent = 'Password changed.';
  };
}
/* ---------- dApp approval popup ---------- */
let popupOpen = false;
async function pollDapp() {
  if (!S.token || popupOpen || ['welcome', 'create', 'srp', 'quiz', 'import', 'lock'].includes(S.view)) return;
  const r = await api('GET', '/api/dapp/pending');
  if (r.ok && r.data.requests && r.data.requests.length) showPopup(r.data.requests[0]);
}
function showPopup(q) {
  popupOpen = true;
  const isConnect = q.type === 'connect';
  let body;
  if (isConnect) {
    body = `<h2>Connect request</h2>
      <div class="box"><b>${esc(q.origin)}</b></div>
      <p class="dim">wants to see your account address and request transactions.</p>
      <label>Choose account(s)</label>
      ${S.accounts.map(a => `<label class="chk"><input type="checkbox" class="pick" value="${esc(a.address)}" ${a.address === S.sel ? 'checked' : ''}> ${esc(a.name)} <span class="mono dim">${short(a.address)}</span></label>`).join('')}
      <div class="warn">Only connect to sites you trust. A connected site can ask you to approve payments but cannot move funds by itself.</div>`;
  } else {
    const p = q.params;
    body = `<h2>Confirm transaction</h2>
      <p class="dim">Requested by</p><div class="box"><b>${esc(q.origin)}</b></div>
      <div class="box" style="margin-top:8px"><div class="dim">From</div>${esc(nameOf(p.from))} <span class="mono">${short(p.from)}</span>
      <div class="dim" style="margin-top:8px">To</div><span class="mono">${esc(p.to)}</span>
      <div class="dim" style="margin-top:8px">Amount</div><b style="font-size:20px">${esc(p.amount)} PC</b></div>
      <p class="dim" style="font-size:12px">The wallet signs this locally only if you confirm.</p>`;
  }
  const m = document.createElement('div');
  m.className = 'modal';
  m.innerHTML = `<div class="sheet">${body}<div id="perr" class="err"></div>
    <button id="pok" class="btn">${isConnect ? 'Connect' : 'Confirm'}</button><button id="pno" class="btn ghost">Reject</button></div>`;
  document.body.appendChild(m);
  const close = () => { m.remove(); popupOpen = false; if (S.view === 'main') refresh(); };
  m.querySelector('#pno').onclick = async () => {
    await api('POST', '/api/dapp/resolve', {id: q.id, approve: false}); close();
  };
  m.querySelector('#pok').onclick = async () => {
    const accounts = [...m.querySelectorAll('.pick:checked')].map(x => x.value);
    if (isConnect && !accounts.length) { m.querySelector('#perr').textContent = 'Select at least one account'; return; }
    m.querySelectorAll('button').forEach(b => b.disabled = true);
    const r = await api('POST', '/api/dapp/resolve', {id: q.id, approve: true, accounts});
    if (r.ok && r.data.status === 'failed') alert('Failed: ' + r.data.error);
    close();
  };
}
setInterval(pollDapp, 1500);

/* ---------- timers & boot ---------- */
setInterval(() => {
  if (!S.token) return;
  const left = Math.max(0, Math.floor(S.autolock - (Date.now() - S.last) / 1000));
  const c = el('cd'); if (c) c.textContent = Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
  if (left === 0) gotoLocked();
}, 1000);
setInterval(refresh, 4000);
let lastPing = 0;
const activity = () => {
  if (!S.token) return;
  S.last = Date.now();
  if (Date.now() - lastPing > 10000) { lastPing = Date.now(); api('POST', '/api/ping', {}); }
};
document.addEventListener('click', activity);
document.addEventListener('keydown', activity);

(async () => {
  const r = await api('GET', '/api/state');
  if (!r.ok) { show('<h2>Wallet service error</h2><p class="dim">' + esc(r.data.error || r.status) + '</p>'); return; }
  S.autolock = r.data.autolock_seconds;
  if (!r.data.has_vault) { setToken(null); vWelcome(); }
  else if (r.data.unlocked) vMain();
  else { setToken(null); vLock(); }
})();
</script></body></html>"""