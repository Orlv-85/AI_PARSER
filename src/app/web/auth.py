from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Any, cast

_Argon2PasswordHasher: Any = None
try:
    from argon2 import PasswordHasher as _Argon2PasswordHasher  # type: ignore[no-redef]
except ImportError:  # pragma: no cover - optional dependency
    pass

_bcrypt: Any = None
try:
    import bcrypt as _bcrypt  # type: ignore[no-redef]
except ImportError:  # pragma: no cover - optional dependency
    pass


_ARGON2_HASHER = _Argon2PasswordHasher() if _Argon2PasswordHasher is not None else None


def verify_bearer_token(authorization: str | None, expected_token: str | None) -> bool:
    """Check an ``Authorization: Bearer <token>`` header in constant time."""
    if not expected_token or not authorization:
        return False
    scheme, _, provided = authorization.partition(" ")
    if scheme.lower() != "bearer" or not provided.strip():
        return False
    return hmac.compare_digest(provided.strip().encode("utf-8"), expected_token.encode("utf-8"))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def hash_password(password: str) -> str:
    if _ARGON2_HASHER is not None:
        return cast(str, _ARGON2_HASHER.hash(password))
    if _bcrypt is not None:
        hashed = _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt())
        return cast(bytes, hashed).decode("utf-8")

    # Fallback for environments without argon2/bcrypt installed.
    salt = secrets.token_bytes(16)
    n = 2**14
    r = 8
    p = 1
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=32,
    )
    return f"scrypt${n}${r}${p}${_b64encode(salt)}${_b64encode(derived_key)}"


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$argon2"):
        return _verify_argon2_password(password, password_hash)

    if password_hash.startswith("$2"):
        return _verify_bcrypt_password(password, password_hash)

    return _verify_scrypt_password(password, password_hash)


def _verify_argon2_password(password: str, password_hash: str) -> bool:
    if _ARGON2_HASHER is None:
        return False
    try:
        return bool(_ARGON2_HASHER.verify(password_hash, password))
    except Exception:
        return False


def _verify_bcrypt_password(password: str, password_hash: str) -> bool:
    if _bcrypt is None:
        return False
    try:
        return bool(
            _bcrypt.checkpw(
                password.encode("utf-8"),
                password_hash.encode("utf-8"),
            )
        )
    except (TypeError, ValueError):
        return False


def _verify_scrypt_password(password: str, password_hash: str) -> bool:
    # Legacy scrypt support for existing stored hashes.
    try:
        algorithm, n_s, r_s, p_s, salt_b64, hash_b64 = password_hash.split("$", maxsplit=5)
        if algorithm != "scrypt":
            return False
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
        calculated = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(expected),
        )
        return hmac.compare_digest(calculated, expected)
    except (TypeError, ValueError):
        return False


class SessionSigner:
    def __init__(self, *, secret: str, ttl_seconds: int) -> None:
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds
        self._revoked_tokens: set[str] = set()
        self._active_token_by_subject: dict[str, str] = {}

    def sign(self, *, subject: str, now: datetime | None = None) -> str:
        issued_at = int((now or datetime.now(tz=UTC)).timestamp())
        payload = {"sub": subject, "iat": issued_at, "exp": issued_at + self._ttl_seconds}
        message_bytes = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        message = _b64encode(message_bytes)
        signature = _b64encode(
            hmac.new(
                self._secret,
                message.encode("ascii"),
                hashlib.sha256,
            ).digest()
        )
        token = f"{message}.{signature}"
        self._active_token_by_subject[subject] = self._token_fingerprint(token)
        return token

    def revoke(self, token: str) -> None:
        self._revoked_tokens.add(self._token_fingerprint(token))

    def verify(self, token: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        try:
            token_fingerprint = self._token_fingerprint(token)
            message, signature = token.split(".", maxsplit=1)
            expected_signature = _b64encode(
                hmac.new(self._secret, message.encode("ascii"), hashlib.sha256).digest()
            )
            payload_raw = json.loads(_b64decode(message).decode("utf-8"))
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return None
        if token_fingerprint in self._revoked_tokens:
            return None
        if not hmac.compare_digest(signature, expected_signature):
            return None
        if not isinstance(payload_raw, dict):
            return None

        payload = cast(dict[str, Any], payload_raw)
        is_expired = int((now or datetime.now(tz=UTC)).timestamp()) > int(payload["exp"])
        subject_raw = payload.get("sub")
        if is_expired or not subject_raw:
            return None
        subject = str(subject_raw)
        active_token = self._active_token_by_subject.get(subject)
        is_active_session = active_token is None or active_token == token_fingerprint
        return payload if is_active_session else None

    @staticmethod
    def _token_fingerprint(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
