"""
Symmetric encryption for secrets-at-rest (spec: encrypted sensitive data
where appropriate) - currently used only for Gmail OAuth tokens
(app/models/integration.py).

Phase 8 security audit (D6): key is now derived from a dedicated
TOKEN_ENCRYPTION_KEY env var when set, rather than always being derived
from SECRET_KEY - a compromised/rotated SECRET_KEY (session signing, CSRF)
no longer also exposes/invalidates every stored Gmail token. Falls back to
the original SECRET_KEY-derived behavior when TOKEN_ENCRYPTION_KEY is
unset, so this is opt-in and backward compatible: a deployment that never
sets it is completely unaffected. decrypt_text() also tries the legacy
SECRET_KEY-derived key as a fallback whenever TOKEN_ENCRYPTION_KEY is set,
so introducing it on a live deployment that already has tokens encrypted
under the old derivation doesn't force those users to reconnect Gmail -
new encryptions move to the new key immediately, already-stored tokens
keep decrypting until they're naturally replaced (token refresh,
reconnect, etc). If SECRET_KEY rotates while TOKEN_ENCRYPTION_KEY is
unset (the default, pre-existing behavior), previously-encrypted tokens
still become unreadable and the affected user simply reconnects Gmail -
not a data-loss concern, these are refreshable API tokens, not user
content.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _derive_key(secret):
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet():
    key_material = current_app.config.get("TOKEN_ENCRYPTION_KEY") or current_app.config["SECRET_KEY"]
    return Fernet(_derive_key(key_material))


def _legacy_fernet():
    """The pre-D6 key derivation (always from SECRET_KEY) - only used as a
    decrypt fallback, and only when TOKEN_ENCRYPTION_KEY is actually set
    (otherwise it's identical to _fernet() and retrying would be pointless)."""
    return Fernet(_derive_key(current_app.config["SECRET_KEY"]))


def encrypt_text(plain):
    if plain is None:
        return None
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_text(ciphertext):
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        if not current_app.config.get("TOKEN_ENCRYPTION_KEY"):
            return None
        try:
            return _legacy_fernet().decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            return None
