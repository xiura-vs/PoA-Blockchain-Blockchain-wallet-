"""
vault.py - the encrypted wallet vault (what MetaMask calls the "keyring").

On disk: vault.json = {kdf params, salt, nonce, ciphertext}.
The plaintext inside holds the recovery phrase + account list and exists only
in memory while the wallet is unlocked.

  password --scrypt--> 256-bit key --AES-256-GCM--> ciphertext
GCM is *authenticated*: a wrong password OR a modified file fails the tag check.
"""

import hmac
import hashlib
import json
import os
import secrets
import threading

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ecdsa import SigningKey, SECP256k1

from crypto_utils import public_key_from_private, public_key_to_address
from . import bip32, bip39

MIN_PASSWORD = 8
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}      # laptop-friendly; production uses a higher cost
AAD = b"poa-wallet-vault-v1"


class WalletError(Exception):
    pass


class WrongPassword(WalletError):
    pass


def _kdf(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p,
                          dklen=32, maxmem=128 * n * r * 2)


def _clean_priv(priv_hex: str) -> str:
    s = priv_hex.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if len(s) != 64:
        raise WalletError("private key must be 64 hex characters")
    try:
        k = int(s, 16)
    except ValueError:
        raise WalletError("private key is not valid hex")
    if not 0 < k < SECP256k1.order:
        raise WalletError("private key out of range")
    return s


class Vault:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._key = None
        self._kdf_params = None
        self._salt = None
        self._data = None
        self._seed = None

    # ---- state -------------------------------------------------------------
    def exists(self) -> bool:
        return os.path.exists(self.path)

    @property
    def unlocked(self) -> bool:
        return self._data is not None

    def _require_unlocked(self):
        if not self.unlocked:
            raise WalletError("wallet is locked")

    # ---- create / restore ------------------------------------------------
    def create(self, password: str, mnemonic: str = None) -> str:
        """New wallet (random phrase) or restore (pass an existing phrase).
        Leaves the vault unlocked and returns the normalized phrase."""
        with self._lock:
            if self.exists():
                raise WalletError("a wallet already exists at this location")
            if len(password) < MIN_PASSWORD:
                raise WalletError(f"password must be at least {MIN_PASSWORD} characters")
            if mnemonic is None:
                mnemonic = bip39.generate_mnemonic(12)
            else:
                bip39.mnemonic_to_entropy(mnemonic)               # raises ValueError if invalid
                mnemonic = bip39.normalize(mnemonic)
            self._kdf_params = dict(SCRYPT)
            self._salt = secrets.token_bytes(16)
            self._key = _kdf(password, self._salt, **self._kdf_params)
            self._data = {"mnemonic": mnemonic, "next_index": 1,
                          "accounts": [{"name": "Account 1", "kind": "hd", "index": 0}]}
            self._seed = bip39.mnemonic_to_seed(mnemonic)
            self._save()
            return mnemonic

    # ---- lock / unlock -----------------------------------------------------
    def unlock(self, password: str):
        with self._lock:
            try:
                with open(self.path) as f:
                    blob = json.load(f)
                params = blob["kdf"]
                salt = bytes.fromhex(blob["salt"])
                key = _kdf(password, salt, params["n"], params["r"], params["p"])
                plain = AESGCM(key).decrypt(bytes.fromhex(blob["nonce"]),
                                            bytes.fromhex(blob["ciphertext"]), AAD)
                data = json.loads(plain)
            except InvalidTag:
                raise WrongPassword("incorrect password")
            except (OSError, KeyError, ValueError, TypeError):
                raise WalletError("vault file is missing or corrupted")
            self._kdf_params = {k: params[k] for k in ("n", "r", "p")}   # drop the "name" label
            self._salt, self._key, self._data = salt, key, data
            self._seed = bip39.mnemonic_to_seed(data["mnemonic"])

    def lock(self):
        with self._lock:
            self._key = self._data = self._seed = None      # drop references to secrets

    def _check_password(self, password: str):
        self._require_unlocked()
        key = _kdf(password, self._salt, **self._kdf_params)
        if not hmac.compare_digest(key, self._key):
            raise WrongPassword("incorrect password")

    def _save(self):
        nonce = os.urandom(12)                               # fresh nonce on every save
        ct = AESGCM(self._key).encrypt(nonce, json.dumps(self._data).encode(), AAD)
        blob = {"version": 1, "kdf": {"name": "scrypt", **self._kdf_params},
                "salt": self._salt.hex(), "cipher": "aes-256-gcm",
                "nonce": nonce.hex(), "ciphertext": ct.hex()}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(blob, f, indent=2)
        os.replace(tmp, self.path)                           # atomic: never a half-written vault

    # ---- accounts ----------------------------------------------------------
    def _priv(self, acct) -> str:
        if acct["kind"] == "hd":
            return bip32.account_private_key(self._seed, acct["index"])
        return acct["priv"]

    def list_accounts(self):
        with self._lock:
            self._require_unlocked()
            return [{"name": a["name"], "kind": a["kind"],
                     "address": public_key_to_address(public_key_from_private(self._priv(a)))}
                    for a in self._data["accounts"]]

    def _find(self, address):
        for a in self._data["accounts"]:
            if public_key_to_address(public_key_from_private(self._priv(a))) == address:
                return a
        raise WalletError("unknown account")

    def add_account(self, name: str = None):
        """Derive the next account from the recovery phrase (like '+ Create account')."""
        with self._lock:
            self._require_unlocked()
            idx = self._data["next_index"]
            self._data["next_index"] = idx + 1
            self._data["accounts"].append(
                {"name": (name or "").strip() or f"Account {len(self._data['accounts']) + 1}",
                 "kind": "hd", "index": idx})
            self._save()
            return self.list_accounts()[-1]
    def discover(self, is_used, gap_limit=3, max_index=50):
        """After a restore: find HD accounts that were used on-chain and re-add them.
        Scans onward from the next index and stops after `gap_limit` unused accounts in a row
        (the same 'gap limit' idea Bitcoin wallets use). Returns how many accounts were added."""
        with self._lock:
            self._require_unlocked()
            start = self._data["next_index"]
            last_used, misses, idx = None, 0, start
            while misses < gap_limit and idx < max_index:
                priv = bip32.account_private_key(self._seed, idx)
                if is_used(public_key_to_address(public_key_from_private(priv))):
                    last_used, misses = idx, 0
                else:
                    misses += 1
                idx += 1
            if last_used is None:
                return 0
            for i in range(start, last_used + 1):
                self._data["accounts"].append(
                    {"name": f"Account {len(self._data['accounts']) + 1}", "kind": "hd", "index": i})
            self._data["next_index"] = last_used + 1
            self._save()
            return last_used - start + 1

    def import_private_key(self, priv_hex: str, name: str = None):
        """Import a standalone key. NOT covered by the recovery phrase (same as MetaMask)."""
        with self._lock:
            self._require_unlocked()
            priv = _clean_priv(priv_hex)
            addr = public_key_to_address(public_key_from_private(priv))
            if any(a["address"] == addr for a in self.list_accounts()):
                raise WalletError("this account is already in the wallet")
            self._data["accounts"].append(
                {"name": (name or "").strip() or f"Imported {len(self._data['accounts']) + 1}",
                 "kind": "imported", "priv": priv})
            self._save()
            return self.list_accounts()[-1]

    def rename_account(self, address: str, name: str):
        with self._lock:
            self._require_unlocked()
            if not name.strip():
                raise WalletError("name cannot be empty")
            self._find(address)["name"] = name.strip()
            self._save()
            
    # ---- connected sites (stored inside the encrypted vault) ---------------
    def get_sites(self):
        """{origin: [addresses]} for sites the user connected, limited to accounts we still own."""
        with self._lock:
            self._require_unlocked()
            own = {a["address"] for a in self.list_accounts()}
            return {o: [x for x in addrs if x in own]
                    for o, addrs in self._data.get("sites", {}).items()}

    def set_site(self, origin: str, addresses):
        with self._lock:
            self._require_unlocked()
            self._data.setdefault("sites", {})[origin] = sorted(set(addresses))
            self._save()

    def remove_site(self, origin: str):
        with self._lock:
            self._require_unlocked()
            if self._data.get("sites", {}).pop(origin, None) is not None:
                self._save()

    # ---- secrets (internal use or password-gated) ---------------------------
    def get_private_key(self, address: str) -> str:
        """For the signing code only. Never expose this over an API without re-auth."""
        with self._lock:
            self._require_unlocked()
            return self._priv(self._find(address))

    def reveal_mnemonic(self, password: str) -> str:
        with self._lock:
            self._check_password(password)
            return self._data["mnemonic"]

    def export_private_key(self, address: str, password: str) -> str:
        with self._lock:
            self._check_password(password)
            return self._priv(self._find(address))

    def change_password(self, old: str, new: str):
        with self._lock:
            self._check_password(old)
            if len(new) < MIN_PASSWORD:
                raise WalletError(f"password must be at least {MIN_PASSWORD} characters")
            self._salt = secrets.token_bytes(16)
            self._key = _kdf(new, self._salt, **self._kdf_params)
            self._save()