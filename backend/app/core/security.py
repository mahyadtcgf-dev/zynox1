"""Security primitives.

- Argon2id password hashing
- Constant-time comparison
- URL-safe token generation
- Telegram WebApp authentication (server-side, per Telegram spec)
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import urllib.parse
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

# ── Password hashing (Argon2id) ───────────────────────────────

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,   # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    if not password:
        raise ValueError("password must not be empty")
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against an Argon2id hash."""
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False
    except Exception:  # malformed hash, etc. — never leak internals
        return False


def needs_rehash(hashed: str) -> bool:
    return _hasher.check_needs_rehash(hashed)


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(value: str) -> str:
    """SHA-256 of refresh tokens — store hashes, not raw tokens."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ── Telegram WebApp authentication ────────────────────────────

class TelegramAuthError(Exception):
    """Raised when Telegram initData fails validation."""


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict[str, Any]:
    """Validate Telegram WebApp `initData` per the official Telegram mechanism.

    Steps (as documented by Telegram):
      1. Parse the query string.
      2. Remove `hash` and `sig` from the received set.
      3. Sort remaining parameters alphabetically.
      4. Concatenate as `key=value` newline-joined.
      5. Compute `secret_key = HMAC-SHA256("WebAppData", bot_token)`.
      6. Compute `hash = HMAC-SHA256(data_check_string, secret_key)` (hex).
      7. Compare the computed hash with the received `hash` (constant time).
      8. Check `auth_date` freshness to reject replays.

    Returns the parsed user payload on success. Raises TelegramAuthError
    otherwise. The caller must NEVER trust `initDataUnsafe` on the client.
    """
    if not init_data or not bot_token:
        raise TelegramAuthError("missing initData or bot token")

    parsed = urllib.parse.parse_qs(init_data, keep_blank_values=False)
    received_hash = parsed.pop("hash", [None])[0]

    if not received_hash:
        raise TelegramAuthError("initData is missing hash")

    # Drop empty-valued params (Telegram omits them; tolerate clients that send them).
    items = sorted(
        (k, v[0]) for k, v in parsed.items() if v and v[0] != ""
    )
    if not items:
        raise TelegramAuthError("initData has no parameters")

    data_check_string = "\n".join(f"{k}={v}" for k, v in items)

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not constant_time_eq(computed_hash, received_hash):
        raise TelegramAuthError("invalid Telegram signature")

    # ── Replay protection ─────────────────────────────────────
    auth_date_raw = parsed.get("auth_date", [None])[0]
    if not auth_date_raw:
        raise TelegramAuthError("initData is missing auth_date")
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError):
        raise TelegramAuthError("invalid auth_date") from None

    max_age = settings.telegram_webapp_auth_timeout_seconds
    if time.time() - auth_date > max_age:
        raise TelegramAuthError("Telegram auth data has expired")

    # ── Extract user payload ──────────────────────────────────
    user_raw = parsed.get("user", [None])[0]
    if not user_raw:
        raise TelegramAuthError("initData is missing user")

    import json

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        raise TelegramAuthError("initData user payload is not valid JSON") from None

    if not isinstance(user, dict) or "id" not in user:
        raise TelegramAuthError("initData user payload is missing id")

    return {
        "user": user,
        "auth_date": auth_date,
        "query_id": parsed.get("query_id", [None])[0],
        "start_param": parsed.get("start_param", [None])[0],
    }
