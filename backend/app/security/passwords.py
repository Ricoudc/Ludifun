"""Mots de passe des parents : argon2id (§16.1)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH, MAX_LENGTH = 12, 128

_hasher = PasswordHasher()  # argon2id, paramètres recommandés par la bibliothèque
# Empreinte factice : vérifier un e-mail inconnu prend le même temps qu'un e-mail connu.
_DUMMY_HASH = _hasher.hash("mot de passe factice pour égaliser les temps de réponse")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
