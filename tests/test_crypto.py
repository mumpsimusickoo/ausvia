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


def test_encrypt_decrypt_roundtrip_with_dedicated_token_key(app, monkeypatch):
    """Phase 8 security audit (D6a): TOKEN_ENCRYPTION_KEY, when set, is used
    instead of the SECRET_KEY-derived key."""
    with app.app_context():
        monkeypatch.setitem(app.config, "TOKEN_ENCRYPTION_KEY", "a-dedicated-test-key")
        ciphertext = encrypt_text("my-secret-token")
        assert decrypt_text(ciphertext) == "my-secret-token"


def test_token_encrypted_before_dedicated_key_introduced_still_decrypts_after(app, monkeypatch):
    """The core D6a backward-compatibility guarantee: introducing
    TOKEN_ENCRYPTION_KEY on a deployment that already has Gmail tokens
    encrypted under the old SECRET_KEY-derived key must not force those
    users to reconnect Gmail."""
    with app.app_context():
        ciphertext = encrypt_text("pre-existing-token")  # old behavior, no TOKEN_ENCRYPTION_KEY yet

    with app.app_context():
        monkeypatch.setitem(app.config, "TOKEN_ENCRYPTION_KEY", "newly-introduced-key")
        assert decrypt_text(ciphertext) == "pre-existing-token"


def test_new_encryptions_after_key_introduced_use_the_new_key(app, monkeypatch):
    with app.app_context():
        monkeypatch.setitem(app.config, "TOKEN_ENCRYPTION_KEY", "newly-introduced-key")
        ciphertext = encrypt_text("fresh-token")

    # monkeypatch only reverts at test teardown, not at the end of a `with`
    # block, so TOKEN_ENCRYPTION_KEY is still set here unless removed
    # explicitly - do that to genuinely simulate "not set".
    with app.app_context():
        monkeypatch.delitem(app.config, "TOKEN_ENCRYPTION_KEY", raising=False)
        # without TOKEN_ENCRYPTION_KEY set, this ciphertext isn't decryptable -
        # it was never encrypted under the SECRET_KEY-derived key at all
        assert decrypt_text(ciphertext) is None

    with app.app_context():
        monkeypatch.setitem(app.config, "TOKEN_ENCRYPTION_KEY", "newly-introduced-key")
        assert decrypt_text(ciphertext) == "fresh-token"


def test_garbage_ciphertext_fails_closed_even_with_dedicated_key_set(app, monkeypatch):
    with app.app_context():
        monkeypatch.setitem(app.config, "TOKEN_ENCRYPTION_KEY", "a-dedicated-test-key")
        assert decrypt_text("not-a-real-fernet-token") is None
