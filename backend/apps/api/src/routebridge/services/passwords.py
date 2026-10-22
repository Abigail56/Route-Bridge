"""Password hashing with Argon2id (argon2-cffi's defaults follow the RFC 9106 recommendation)."""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
# checked against when the email is unknown, so a wrong email takes as long as a wrong password
_DUMMY_HASH = _hasher.hash("routebridge-no-such-account")

MIN_LENGTH = 8
MAX_LENGTH = 128


def password_problem(password: str, email: str | None = None) -> str | None:
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters for your password."
    if len(password) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters for your password."
    if email and password.strip().lower() == email.strip().lower():
        return "Your password cannot be your email address."
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)
