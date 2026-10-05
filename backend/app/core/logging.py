"""Structured logging with secret scrubbing.

Never logs: passwords, bot tokens, private keys, access/refresh tokens, or any
value matched against the configured secret registry.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

from app.core.config import settings

# ── Secret scrubbing ──────────────────────────────────────────

_REDACTED = "***REDACTED***"

# Fixed patterns — high-signal, low false-positive rate.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(secret|token|api[_-]?key)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(bearer)\s+[A-Za-z0-9\-\._~\+\/=]+"),
    re.compile(
        r"(?i)(?:-----BEGIN[A-Z ]*PRIVATE KEY-----)"
        r"[\s\S]*?(?:-----END[A-Z ]*PRIVATE KEY-----)"
    ),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
)

# Values registered at runtime (env secrets, tokens) — exact-match redaction.
_secret_values: list[str] = []
_secret_keys: set[str] = {
    "password", "passwd", "pwd", "secret", "token", "access_token", "refresh_token",
    "api_key", "apikey", "authorization", "bot_token", "private_key", "credentials",
    "session_secret", "jwt_secret", "database_url",
}


def register_secret(value: str) -> None:
    """Register a concrete secret value for exact-match redaction."""
    if value and len(value) >= 8:
        _secret_values.append(value)


def scrub(value: Any) -> Any:
    """Recursively redact secrets from a value (str/dict/list/tuple)."""
    if isinstance(value, str):
        result = value
        for pattern in _PATTERNS:
            result = pattern.sub(_REDACTED, result)
        for secret in _secret_values:
            if secret and secret in result:
                result = result.replace(secret, _REDACTED)
        return result
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k.lower() in _secret_keys else scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return type(value)(scrub(v) for v in value)  # type: ignore[call-overload]
    return value


# ``logging`` merges the dict passed as ``extra=`` straight into
# ``record.__dict__``; it never stores it under an ``"extra"`` key. Reading
# ``record.__dict__.get("extra")`` therefore always returned None and every
# structured field was silently dropped from every log line. These are the
# attributes the stdlib sets itself; anything else came from ``extra=``.
_STANDARD_LOG_ATTRS = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "taskName", "thread", "threadName",
})


def _structured_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Return the ``extra=`` fields attached to a log record."""
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_LOG_ATTRS and not key.startswith("_")
    }


class SecretScrubbingFormatter(logging.Formatter):
    """JSON formatter that redacts secrets before serializing."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        structured = _structured_fields(record)
        if structured:
            payload["extra"] = scrub(structured)

        # Redact any string args that may carry secrets.
        if record.args:
            record.args = scrub(record.args)
        payload["message"] = scrub(record.getMessage())

        import json

        return json.dumps(payload, default=str, ensure_ascii=False)


def setup_logging() -> None:
    """Configure root logging from settings."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Scrub registered env secrets so they never reach the log stream.
    for attr in ("jwt_secret", "session_secret", "admin_password", "telegram_bot_token"):
        register_secret(getattr(settings, attr, ""))

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        SecretScrubbingFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
    )

    # Replace existing handlers (uvicorn re-entrancy safety).
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy third-party loggers.
    for name in ("uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # In production, never emit debug from libraries.
    if settings.is_production:
        for name in ("asyncio", "sqlalchemy.engine", "alembic"):
            logging.getLogger(name).setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
