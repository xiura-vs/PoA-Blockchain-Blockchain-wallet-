"""
config.py - shared chain parameters. Every node must load identical values.
"""

from crypto_utils import sha256_hex, public_key_from_private, public_key_to_address

# ---- Chain parameters ------------------------------------------------------
CHAIN_ID = "poa-demo-1"
BLOCK_TIME = 5                 # seconds per slot
GENESIS_TIME = 1_700_000_000   # fixed unix time -> genesis hash identical everywhere
MAX_FUTURE_DRIFT = 2           # seconds a block timestamp may be ahead of our clock
MAX_TXS_PER_BLOCK = 100

# ---- Network (used in later steps) ----------------------------------------
P2P_BASE_PORT = 6000           # validator i listens on 6000 + i
DASHBOARD_BASE_PORT = 8000     # node i serves its dashboard on 8000 + i


# ---- Deterministic DEMO keys ----------------------------------------------
def key_from_seed(seed: str):
    """DEMO ONLY: private key = SHA-256(seed). Anyone who knows the seed owns the key."""
    priv = sha256_hex(seed.encode())
    pub = public_key_from_private(priv)
    return priv, pub, public_key_to_address(pub)


def _account(name: str, seed_prefix: str) -> dict:
    priv, pub, addr = key_from_seed(f"{seed_prefix}-{name}")
    return {"name": name, "priv": priv, "pub": pub, "addr": addr}


# Ordered list: the ORDER defines the round-robin schedule.
VALIDATORS = []
for _i, _name in enumerate(["V1", "V2", "V3"]):
    _v = _account(_name, "poa-demo-validator")
    _v["port"] = P2P_BASE_PORT + _i
    VALIDATORS.append(_v)

# Demo end-user wallets
USERS = {n: _account(n, "poa-demo-user") for n in ["alice", "bob", "carol"]}

# Genesis balances (the "premine")
GENESIS_ALLOC = {
    USERS["alice"]["addr"]: 1000,
    USERS["bob"]["addr"]: 500,
}

if __name__ == "__main__":
    print("Validators (round-robin order):")
    for i, v in enumerate(VALIDATORS):
        print(f"  slot%3=={i}  {v['name']}  {v['addr']}  port {v['port']}")
    print("Users:")
    for n, u in USERS.items():
        print(f"  {n:6} {u['addr']}  genesis balance: {GENESIS_ALLOC.get(u['addr'], 0)}")