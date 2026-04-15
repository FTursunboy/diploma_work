import base64
import hashlib
import hmac
import json
import os
import secrets
import time


class AuthError(Exception):
    pass


ROLE_USER = "user"
ROLE_MODERATOR = "moderator"
ROLE_ADMIN = "admin"
ALL_ROLES = {ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN}

DEFAULT_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
DEFAULT_PBKDF2_ITERATIONS = 310_000
DEFAULT_HASH_ALG = "sha256"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + pad).encode("ascii"))


def _auth_secret() -> bytes:
    secret = os.getenv("AUTH_SECRET", "dev-secret-change-me")
    return secret.encode("utf-8")


def token_ttl_seconds() -> int:
    raw = os.getenv("AUTH_TOKEN_TTL_SECONDS", str(DEFAULT_TOKEN_TTL_SECONDS))
    try:
        ttl = int(raw)
    except ValueError:
        return DEFAULT_TOKEN_TTL_SECONDS
    return max(60, ttl)


def pbkdf2_iterations() -> int:
    raw = os.getenv("AUTH_PBKDF2_ITERATIONS", str(DEFAULT_PBKDF2_ITERATIONS))
    try:
        iters = int(raw)
    except ValueError:
        return DEFAULT_PBKDF2_ITERATIONS
    return max(100_000, iters)


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 6:
        raise AuthError("Пароль должен быть не короче 6 символов.")

    salt = secrets.token_bytes(16)
    iters = pbkdf2_iterations()
    derived = hashlib.pbkdf2_hmac(DEFAULT_HASH_ALG, password.encode("utf-8"), salt, iters)
    return f"pbkdf2_{DEFAULT_HASH_ALG}${iters}${_b64url_encode(salt)}${_b64url_encode(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iters_raw, salt_b64, hash_b64 = (encoded or "").split("$", 3)
        if scheme != f"pbkdf2_{DEFAULT_HASH_ALG}":
            return False
        iters = int(iters_raw)
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(hash_b64)
    except Exception:
        return False

    derived = hashlib.pbkdf2_hmac(DEFAULT_HASH_ALG, password.encode("utf-8"), salt, iters)
    return hmac.compare_digest(derived, expected)


def create_access_token(*, user_id: int, ttl_seconds: int | None = None) -> str:
    now = int(time.time())
    exp = now + (ttl_seconds if ttl_seconds is not None else token_ttl_seconds())
    payload = {"sub": int(user_id), "exp": int(exp)}
    payload_raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_b64 = _b64url_encode(payload_raw)
    sig = hmac.new(_auth_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> dict:
    if not token or "." not in token:
        raise AuthError("Некорректный токен.")

    payload_b64, sig_b64 = token.split(".", 1)
    try:
        sig = _b64url_decode(sig_b64)
    except Exception as exc:
        raise AuthError("Некорректный токен.") from exc

    expected_sig = hmac.new(_auth_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected_sig):
        raise AuthError("Некорректный токен.")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise AuthError("Некорректный токен.") from exc

    exp = int(payload.get("exp") or 0)
    if exp <= int(time.time()):
        raise AuthError("Срок действия токена истёк.")

    sub = payload.get("sub")
    if sub is None:
        raise AuthError("Некорректный токен.")

    return payload

