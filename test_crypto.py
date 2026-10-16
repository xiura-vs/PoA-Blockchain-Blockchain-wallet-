from crypto_utils import *

def test_hash_deterministic():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}          # same content, different insertion order
    assert hash_obj(a) == hash_obj(b)
    assert len(hash_obj(a)) == 64

def test_keys_and_address():
    priv, pub = generate_keypair()
    assert len(priv) == 64 and len(pub) == 128
    assert public_key_from_private(priv) == pub
    addr = public_key_to_address(pub)
    assert addr.startswith("PC") and len(addr) == 42
    assert private_key_to_address(priv) == addr

def test_sign_verify():
    priv, pub = generate_keypair()
    msg = b"hello chain"
    sig = sign(priv, msg)
    assert verify(pub, sig, msg)
    assert not verify(pub, sig, b"hello chain!")           # tampered message
    _, other_pub = generate_keypair()
    assert not verify(other_pub, sig, msg)                 # wrong key
    assert not verify(pub, "deadbeef", msg)                # garbage sig
    assert not verify("nothex", sig, msg)                  # garbage key

def test_deterministic_signature():
    priv, _ = generate_keypair()
    assert sign(priv, b"x") == sign(priv, b"x")

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)