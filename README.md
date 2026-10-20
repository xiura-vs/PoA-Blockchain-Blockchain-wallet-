# PoA Chain & Wallet

A from-scratch **Proof-of-Authority blockchain** in Python, with a **MetaMask-style
self-custody wallet** (React + TypeScript). Built as an educational project: every
piece is small enough to read in one sitting, and every claim is covered by a test.

> ⚠️ **Educational project, not for real funds.** Demo keys are derived from public
> seed strings, there is no finality or fork choice, and the networking is unauthenticated.
> See [Known limitations](#known-limitations).

## What's inside

| Layer | What it does |
|---|---|
| **Cryptography** | SHA-256, ECDSA (secp256k1) signatures, address derivation, Merkle trees |
| **Ledger** | Signed account-based transactions, hash-linked blocks, genesis block, replayed state |
| **P2P network** | Real TCP sockets, gossip with dedup, independent validation, chain sync for late joiners |
| **Consensus** | Proof of Authority: 3 validators take turns in 5-second slots; every node verifies every block |
| **Wallet** | BIP-39 12-word recovery phrase, BIP-32 HD accounts, AES-256-GCM encrypted vault, dApp approvals |
| **UI** | Live chain dashboard, React wallet (dark/light), "Byte Coffee" demo shop |

No mining, no Docker, runs on a low-spec laptop.

## Architecture

```
 React wallet UI  -->  Wallet service (holds keys, signs)  -->  Node V1 <--> Node V2
                       127.0.0.1:9000                              \          /
                                                                    Node V3
                                          P2P gossip over TCP (6000-6002), PoA blocks
```

Layers, bottom to top: **crypto → data structures → network → consensus → wallet**.

## Quick start (Windows / PowerShell)

**Requirements:** Python 3.10+, Node.js 20+, Git.

```powershell
git clone https://github.com/xiura-vs/PoA-Blockchain-Blockchain-wallet-.git
cd poa-chain

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd wallet-ui
npm install
npm run build
cd ..

.\start_all.ps1
```

If PowerShell blocks the script: `powershell -ExecutionPolicy Bypass -File .\start_all.ps1`

This starts 3 validator nodes, the wallet service and a demo shop, then opens:

| URL | What |
|---|---|
| http://127.0.0.1:9000 | The wallet |
| http://127.0.0.1:9100 | Byte Coffee (demo dApp) |
| http://127.0.0.1:8000 | Live chain dashboard |

Stop everything with `.\start_all.ps1 -Stop`.

**Fund a new wallet** (the chain has no faucet; Alice holds the genesis balance):

```powershell
python wallet.py --user alice send <your-address> 200
```

**Scripted chain demo** (narrated scenes; stop `start_all` first, the ports overlap):

```powershell
python run_demo.py
```

## Tests

Close any running nodes first (the tests use the same ports).

```powershell
python test_crypto.py
python test_ledger.py             # block rules and attack rejections
python test_p2p.py                # gossip and late-joiner sync
python test_poa.py                # round-robin, validator failure, recovery
python -m mm_wallet.test_core     # BIP-39/32 official vectors, vault
python -m mm_wallet.test_service  # sessions, throttling, end-to-end on a real chain
python -m mm_wallet.test_w4       # dApp flow, CORS limits, account discovery
cd wallet-ui; npm run lint; npm run build
```

## Project structure

```
.
├── config.py            chain parameters, validator list (order = schedule), genesis balances
├── crypto_utils.py      hashing, ECDSA keys/signatures, addresses
├── merkle.py            Merkle root of a block's transactions
├── transaction.py       signed nonce-based transfer
├── block.py             header + txs + validator signature
├── state.py             account balances and nonces
├── blockchain.py        genesis, PoA schedule, ALL block validation rules
├── mempool.py           pending transactions
├── p2p.py               TCP gossip network
├── node.py              full node (chain + mempool + p2p)
├── consensus.py         PoA proposer loop
├── run_node.py          run one validator with a console
├── dashboard.py         per-node HTTP API + live dashboard
├── wallet.py            CLI wallet
├── run_demo.py          scripted chain demo
├── dapp_demo.py         "Byte Coffee" demo website
├── start_all.ps1        one-command launcher
├── mm_wallet/           wallet backend: BIP-39/32, vault, service, dApp broker
└── wallet-ui/           React + TypeScript + Vite + Tailwind wallet UI
```

## How Proof of Authority works

In Proof of Work you earn the right to add a block by burning electricity; in Proof of
Stake, by locking up money. In **Proof of Authority** you earn it by **being a known,
approved identity**. The validator list lives in `config.py`, and only blocks signed by
those validators at the right time are accepted.

| | Proof of Work | Proof of Stake | **Proof of Authority** |
|---|---|---|---|
| Right to propose | Computation | Locked money | **Approved identity** |
| Energy use | Very high | Low | **Very low** |
| Trust assumption | Majority of hash power honest | Majority of stake honest | **Validators are honest** |
| Decentralization | High | Medium-high | **Low (permissioned)** |

### The slot schedule

```
slot     = (block timestamp - GENESIS_TIME) // 5      (5-second slots)
proposer = VALIDATORS[slot % 3]                        (V1, V2, V3, V1, ...)
```

Every slot has exactly one legitimate proposer, and every node computes the same answer
from the same clock and config, so no messages are needed to agree on whose turn it is.
If a validator is offline, its slot passes with no block and the next validator proposes
in its own slot. Rotation is tied to **time, not block height**, so one dead validator
can't halt the chain.

### How the nodes validate a block

A validator proposes, but never decides alone. Each node runs `Blockchain._validate()`
on **its own copy of the chain** and accepts the block only if every check passes:

| # | Check | Proves |
|---|---|---|
| 1 | Height is my tip + 1 and `prev_hash` matches my tip | The block extends my chain |
| 2 | Slot matches timestamp, is after the parent's, and isn't in the future | Timing is consistent |
| 3 | `proposer == VALIDATORS[slot % 3]` | It is this validator's turn |
| 4 | ECDSA signature verifies against the validator's public key from config | The real validator made it, unaltered |
| 5 | Transaction count within limit; recomputed Merkle root equals the header's | The transaction list wasn't changed |
| 6 | Every transaction is valid, in order: signature, chain ID, nonce, balance | No forged, overspent or replayed tx |

If any check fails, the block is dropped and **not relayed**, so bad data dies at the
first honest node. Nodes trust only the pre-agreed authority list and schedule. They
recompute balances and transaction validity themselves, so a validator can only choose
*which valid transactions to include and when*. It cannot mint coins or spend others' money.

> **This is not voting.** Nodes don't vote on blocks as in BFT protocols (IBFT, Tendermint).
> Each makes an independent decision with the same deterministic rules, and honest nodes
> reach the same answer. The trade-off is no finality (see limitations).

### Attacks covered by tests

| Attack | Stopped by |
|---|---|
| Wrong validator proposes | Checks 3 and 4 |
| Claiming to be V2 with another key | Check 4 |
| Editing a tx amount | Check 5 (Merkle mismatch) |
| Editing the amount and fixing the Merkle root | Check 4 (signature no longer matches) |
| Forged tx signature | Check 6 |
| Overspending | Check 6 |
| Replaying a confirmed tx | Check 6 (nonce) |
| Cross-chain replay | Chain ID is inside the signed data |
| Rewriting an old block | Hash links break and the signature fails |
| Future timestamp | Check 2 |

### Life of a transaction

1. The wallet signs `{from, to, amount, nonce, chain_id}`.
2. A node validates it (signature, nonce, balance) and adds it to its **mempool**.
3. It **gossips** the tx; each peer re-validates independently and relays it.
4. The validator whose slot comes next builds a block (Merkle root, `prev_hash`) and **signs the block hash**.
5. The block is broadcast and **every node runs the six checks**.
6. On success each node updates its own state. All nodes then show the same height, tip hash and state root.

## The wallet

A MetaMask-style wallet served at `http://127.0.0.1:9000`. A local Python service holds
the keys and signs; the browser only ever sees addresses and results.

- **12-word recovery phrase (BIP-39)** derives every account (BIP-32, path `m/44'/60'/0'/0/i`).
  Restoring the phrase restores all accounts; used accounts are rediscovered on-chain.
- **Encrypted vault:** password → scrypt → AES-256-GCM. A wrong password or tampered file fails to decrypt.
- **Session, auto-lock and throttling:** random session token, idle auto-lock, and growing delays after repeated wrong passwords.
- **dApp connections:** a website can only *file a request*. The wallet shows an approval sheet with the site's origin, and the service signs only if you confirm. Connected sites are saved inside the encrypted vault.
- **Web hardening:** `Host`/`Origin` checks, CORS enabled on exactly two endpoints, strict CSP (no inline scripts or `eval`), `X-Frame-Options: DENY`, path-traversal guard.

Wallet code is in `mm_wallet/`; the UI is in `wallet-ui/`.

## Security properties

| Property | How |
|---|---|
| Integrity | Hash links, Merkle root, validator signature over the header |
| Authenticity | ECDSA signatures on transactions (users) and blocks (validators) |
| Replay protection | Per-account nonce and chain ID in the signed data |
| No double spending | Nonce ordering, balance checks, state replay, mempool pending-spend accounting |
| Determinism | Canonical JSON, so every node hashes identical bytes |
| Trust minimization | Every node verifies every block; synced history is re-validated block by block |
| Robustness | Parsers never crash on malformed input; invalid data is never relayed |
| Liveness | A dead validator's slot is skipped (demonstrated in `test_poa.py` and `run_demo.py`) |
| Config binding | Genesis commits to the chain ID and starting balances |

## Known limitations

Deliberate shortcuts, each with its production counterpart:

| Area | This project | Production |
|---|---|---|
| Finality / forks | None; a conflicting block is ignored | BFT voting (IBFT/Tendermint) or fork choice |
| Equivocation | Not punished | Slashing, voting |
| Validator keys | Derived from public seed strings | HSM / remote signer |
| Validator set | Fixed in config | On-chain governance |
| Clock | Wall clock, 2s drift allowed | NTP / authenticated time |
| Network | Plain TCP, static peers | TLS/Noise, discovery, peer scoring |
| Persistence | None (nodes resync from peers) | Database |
| Fees | None | Fee market |
| Address format | No checksum | Checksummed (EIP-55, Bech32) |
| State proofs | No state root in header | Merkle-Patricia root, light clients |
| Wallet sandbox | Local service over localhost | Browser-extension sandbox |
| KDF cost | scrypt n=2^14 (laptop-friendly) | Much higher |

## Glossary

**Block** – a batch of transactions plus a header linking to the previous block.
**Genesis block** – block 0, identical on every node.
**Hash (SHA-256)** – one-way fingerprint; any change gives a completely different output.
**Merkle root** – one hash summarizing every transaction in a block.
**ECDSA / secp256k1** – the signature scheme and curve also used by Bitcoin and Ethereum.
**Nonce** – a per-account counter in each transaction that blocks replays.
**Account model** – ledger of `{address: balance, nonce}` (vs. Bitcoin's UTXO model).
**State** – all current balances, derived by replaying blocks.
**Mempool** – a node's pool of valid but unconfirmed transactions.
**Gossip** – nodes pass messages to peers, who pass them on; IDs prevent loops.
**Consensus** – how independent nodes agree on one chain.
**Validator / authority** – an approved block producer in PoA.
**Slot** – a fixed 5-second window with exactly one legitimate proposer.
**Liveness vs. safety** – the chain keeps progressing vs. no conflicting histories.
**Finality** – the guarantee a block can never be reverted (not implemented here).
**Equivocation** – a validator signing two blocks for one slot; the main PoA attack.
**BIP-39** – turns random bytes into a 12-word phrase with a checksum, then a seed.
**BIP-32 / HD wallet** – one seed deterministically derives a tree of keys.
**KDF (scrypt)** – turns a password into a key, deliberately slowly.
**AES-256-GCM** – authenticated encryption; detects a wrong key or tampering.
**CSP** – a header telling the browser which script sources may run.
**Origin / CORS** – the page's `scheme://host:port`, and the browser rule limiting cross-site reads.

## Tech stack

Python (stdlib sockets and `http.server`, `ecdsa`, `cryptography`) · React 19 · TypeScript · Vite · Tailwind CSS v4 · Framer Motion

## License

MIT, see [LICENSE](LICENSE).
