from app.utils.crypto import encrypt_text, decrypt_text


def test_encrypt_decrypt_roundtrip(app):
    with app.app_context():
        ciphertext = encrypt_text("my-secret-token")
        assert ciphertext != "my-secret-token"
        assert decrypt_text(ciphertext) == "my-secret-token"


def test_none_passes_through(app):
    with app.app_context():
        assert encrypt_text(None) is None
        assert decrypt_text(None) is None


def test_tampered_ciphertext_fails_closed(app):
    with app.app_context():
        ciphertext = encrypt_text("secret")
        tampered = ciphertext[:-4] + "abcd"
        assert decrypt_text(tampered) is None
