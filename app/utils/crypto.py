"""
Symmetric encryption for secrets-at-rest (spec: encrypted sensitive data
where appropriate) - currently used only for Gmail OAuth tokens
(app/models/integration.py). Key is derived from SECRET_KEY so no separate
key-management story is needed for this app's scale; if SECRET_KEY rotates,
previously-encrypted tokens become unreadable and the affected user simply
reconnects Gmail (not a data-loss concern - these are refreshable API
tokens, not user content).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _fernet():
    digest = hashlib.sha256(current_app.config["SECRET_KEY"].encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


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
        return None
