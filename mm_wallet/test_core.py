import json
import os
import tempfile

from crypto_utils import public_key_to_address, public_key_from_private
from config import USERS
from transaction import Transaction
from mm_wallet import bip39, bip32
from mm_wallet.vault import Vault, WalletError, WrongPassword

ABANDON = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
PW = "correct horse battery"


def tmpvault():
    return Vault(os.path.join(tempfile.mkdtemp(), "vault.json"))


def test_bip39_official_vector():
    assert bip39.entropy_to_mnemonic(bytes(16)) == ABANDON
    assert bip39.mnemonic_to_entropy(ABANDON) == bytes(16)
    seed = bip39.mnemonic_to_seed(ABANDON, "TREZOR")
    assert seed.hex().startswith("c55257c360c07c72029aebc1b53c05ed")


def test_bip39_generate_and_validate():
    m = bip39.generate_mnemonic()
    assert len(m.split()) == 12 and bip39.is_valid(m)
    assert m != bip39.generate_mnemonic()                       # random each time
    words = ABANDON.split()
    words[-1] = "abandon"                                        # wrong checksum word
    assert not bip39.is_valid(" ".join(words))
    assert not bip39.is_valid("abandon " * 11 + "notaword")
    assert not bip39.is_valid("abandon abandon abandon")         # too short
    assert bip39.is_valid("  ABANDON " + ABANDON[8:] + "  ")     # case/space tolerant


def test_bip32_official_vectors():
    seed = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    k, _ = bip32.master_key(seed)
    assert k.to_bytes(32, "big").hex() == "e8f32e723decf4051aefac8e2c93c9c5b214313817cdb01a1494b917c8436b35"
    assert bip32.derive_private_key(seed, "m/0'") == "edb2e14f9ee77d26dd93b4ecede8d16ed408ce149b6cd80b0715a2d911a0afea"
    assert bip32.derive_private_key(seed, "m/0'/1") == "3c6cb8d0f6a264c91ea8b5030fadaa8e538b020f0a387421a12de9319dc93368"


def test_same_phrase_same_accounts():
    seed = bip39.mnemonic_to_seed(ABANDON)
    a0 = bip32.account_private_key(seed, 0)
    assert a0 == bip32.account_private_key(seed, 0)              # deterministic
    assert a0 != bip32.account_private_key(seed, 1)              # distinct accounts


def test_vault_create_lock_unlock():
    v = tmpvault()
    phrase = v.create(PW)
    assert len(phrase.split()) == 12 and v.unlocked
    addr = v.list_accounts()[0]["address"]
    assert addr.startswith("PC") and len(addr) == 42
    v.lock()
    assert not v.unlocked
    try:
        v.list_accounts()
        assert False, "locked vault must not list accounts"
    except WalletError:
        pass
    v.unlock(PW)
    assert v.list_accounts()[0]["address"] == addr


def test_wrong_password_and_tampering():
    v = tmpvault()
    v.create(PW)
    v.lock()
    try:
        v.unlock("not the password")
        assert False
    except WrongPassword:
        pass
    with open(v.path) as f:
        blob = json.load(f)
    ct = blob["ciphertext"]
    blob["ciphertext"] = ct[:-1] + ("0" if ct[-1] != "0" else "1")   # flip one nibble
    with open(v.path, "w") as f:
        json.dump(blob, f)
    try:
        v.unlock(PW)
        assert False, "tampered vault must not decrypt"
    except WalletError:
        pass


def test_file_contains_no_plaintext():
    v = tmpvault()
    phrase = v.create(PW)
    raw = open(v.path).read()
    assert phrase.split()[0] not in raw.replace('"', " ").split()
    assert "mnemonic" not in raw and "priv" not in raw


def test_restore_from_phrase():
    v1 = tmpvault()
    phrase = v1.create(PW)
    v1.add_account()
    addrs = [a["address"] for a in v1.list_accounts()]
    v2 = tmpvault()
    v2.create("another password", mnemonic=phrase)               # "Import using Secret Recovery Phrase"
    assert v2.list_accounts()[0]["address"] == addrs[0]
    v2.add_account()
    assert [a["address"] for a in v2.list_accounts()] == addrs   # same second account too
    try:
        tmpvault().create(PW, mnemonic="abandon abandon abandon")
        assert False
    except ValueError:
        pass


def test_accounts_import_rename():
    v = tmpvault()
    v.create(PW)
    a2 = v.add_account("Savings")
    assert a2["name"] == "Savings" and len(v.list_accounts()) == 2
    imp = v.import_private_key(USERS["alice"]["priv"], "Alice")
    assert imp["address"] == USERS["alice"]["addr"] and imp["kind"] == "imported"
    try:
        v.import_private_key(USERS["alice"]["priv"])
        assert False, "duplicate import must fail"
    except WalletError:
        pass
    for bad in ("zz", "00" * 32, "12"):
        try:
            v.import_private_key(bad)
            assert False
        except WalletError:
            pass
    v.rename_account(imp["address"], "Alice (imported)")
    v.lock()
    v.unlock(PW)                                                 # everything persisted + encrypted
    assert [a["name"] for a in v.list_accounts()] == ["Account 1", "Savings", "Alice (imported)"]


def test_secrets_need_password():
    v = tmpvault()
    phrase = v.create(PW)
    addr = v.list_accounts()[0]["address"]
    try:
        v.reveal_mnemonic("wrong password")
        assert False
    except WrongPassword:
        pass
    assert v.reveal_mnemonic(PW) == phrase
    priv = v.export_private_key(addr, PW)
    assert public_key_to_address(public_key_from_private(priv)) == addr


def test_change_password():
    v = tmpvault()
    v.create(PW)
    v.change_password(PW, "a brand new password")
    v.lock()
    try:
        v.unlock(PW)
        assert False
    except WrongPassword:
        pass
    v.unlock("a brand new password")


def test_vault_key_signs_valid_chain_tx():
    """The whole point: an HD account can sign a tx our chain accepts."""
    v = tmpvault()
    v.create(PW)
    me = v.list_accounts()[0]["address"]
    tx = Transaction.create(v.get_private_key(me), USERS["bob"]["addr"], 5, 0)
    ok, reason = tx.check_stateless()
    assert ok, reason
    assert tx.sender == me


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)