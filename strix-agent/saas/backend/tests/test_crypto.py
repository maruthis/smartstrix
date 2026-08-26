from app import crypto


def test_encrypt_decrypt_roundtrip():
    ciphertext = crypto.encrypt("ghp_realtoken12345")
    assert ciphertext != "ghp_realtoken12345"
    assert crypto.decrypt(ciphertext) == "ghp_realtoken12345"


def test_encrypting_the_same_plaintext_twice_yields_different_ciphertext():
    # Fernet includes a random nonce/timestamp, so ciphertext isn't
    # deterministic — guards against ever assuming it's safe to compare
    # encrypted values directly instead of decrypting first.
    a = crypto.encrypt("same-token")
    b = crypto.encrypt("same-token")
    assert a != b
    assert crypto.decrypt(a) == crypto.decrypt(b) == "same-token"
