"""Application configuration.

Every setting is environment-driven. No secrets have defaults; the application
refuses to start in production without them.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["development", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


def logger_free_warning(message: str) -> None:
    """Surface a configuration warning without importing the logger here.

    ``app.core.logging`` imports settings, so it cannot be used from this
    module at import time.
    """
    import sys

    print(f"[config] WARNING: {message}", file=sys.stderr)


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────
    app_name: str = Field(default="Zynox", min_length=1, max_length=64)
    app_env: Env = "production"
    debug: bool = False
    host: str = "0.0.0.0"  # noqa: S104 - must accept connections on every interface (Railway)
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = "INFO"

    # ── Database ───────────────────────────────────────────────
    database_url: str = Field(default="", description="PostgreSQL connection string")

    # ── Secrets ────────────────────────────────────────────────
    jwt_secret: str = Field(default="")
    session_secret: str = Field(default="")

    # ── Initial administrator ──────────────────────────────────
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="")

    # ── Tokens ─────────────────────────────────────────────────
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=90)

    # ── Network / security ─────────────────────────────────────
    # Stored as the raw comma-separated string on purpose. pydantic-settings
    # JSON-decodes complex-typed fields from the environment *before* any field
    # validator runs, so an unset CORS_ORIGINS="" would raise SettingsError and
    # abort startup. docker-compose.yml and .env.example both emit an empty
    # value, so a raw str keeps a default deployment bootable.
    cors_origins: str = ""
    rate_limit_enabled: bool = True

    # ── Telegram ───────────────────────────────────────────────
    telegram_bot_token: str = Field(default="")
    telegram_mini_app_url: str = Field(default="")
    telegram_webapp_auth_timeout_seconds: int = Field(default=300, ge=30, le=86400)

    # ── Xray ───────────────────────────────────────────────────
    xray_binary_path: str = "/usr/local/bin/xray"
    xray_config_path: str = "/etc/xray/config.json"
    xray_api_address: str = "127.0.0.1:10085"
    xray_api_timeout_seconds: int = Field(default=5, ge=1, le=60)
    xray_control_mode: Literal["local", "api", "disabled"] = "local"

    # ── Derived ────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def async_database_url(self) -> str:
        """DSN with an explicit async driver.

        ``create_async_engine()`` and Alembic's ``async_engine_from_config()``
        both need an asyncio driver. Given a bare ``postgresql://`` URL,
        SQLAlchemy defaults to psycopg (v3), which is not a dependency here, so
        the URL must be rewritten to the asyncpg driver. Railway injects
        DATABASE_URL as a bare ``postgresql://`` string, so without this the
        application cannot start in production.
        """
        url = self.database_url
        if not url:
            return url
        if url.startswith("sqlite:"):
            if url.startswith("sqlite://") and "+aiosqlite" not in url:
                return "sqlite+aiosqlite://" + url[len("sqlite://") :]
            return url
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://") :]
        if url.startswith("postgresql+") or url.startswith("postgres+"):
            return url
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse ``CORS_ORIGINS`` into a clean list. Empty = same-origin only.

        Accepts the documented comma-separated form and tolerates a JSON-ish
        list such as ``["https://a","https://b"]`` so existing deployments that
        were written against the previous list-typed field keep working.
        """
        raw = self.cors_origins.strip()
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        parts = [p.strip().strip("\"'") for p in raw.split(",")]
        return [p for p in parts if p]

    @field_validator("port", mode="before")
    @classmethod
    def _coerce_port(cls, v: object) -> int:
        """Accept an out-of-range/garbage PORT without failing startup.

        Some shells and CI runners export PORT=0. The application must not
        refuse to boot over that; ``effective_port()`` re-reads the raw value
        at runtime for platforms (Railway) that inject the real port.
        """
        try:
            parsed = int(v)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return 8000
        return parsed if 1 <= parsed <= 65535 else 8000

    @field_validator("database_url", mode="before")
    @classmethod
    def _coerce_db_url(cls, v: object) -> str:
        """Accept postgres:// (SQLAlchemy legacy) and normalize to postgresql://."""
        if not isinstance(v, str):
            return ""
        url = v.strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        return url

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> Settings:
        if not self.is_production:
            return self

        missing: list[str] = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.jwt_secret:
            missing.append("JWT_SECRET")
        if not self.session_secret:
            missing.append("SESSION_SECRET")
        if not self.admin_password:
            missing.append("ADMIN_PASSWORD")

        if missing:
            raise ValueError(
                "Zynox refuses to start in production without required secrets: "
                + ", ".join(missing)
            )
        return self

    # ── Helpers ────────────────────────────────────────────────
    def effective_port(self) -> int:
        """Railway injects PORT; honour it over the configured default."""
        env_port = os.environ.get("PORT")
        if env_port:
            try:
                parsed = int(env_port)
            except ValueError:
                pass
            else:
                if 1 <= parsed <= 65535:
                    return parsed
                logger_free_warning(f"ignoring out-of-range PORT={env_port!r}")
        return self.port

    def backend_root(self) -> Path:
        return Path(__file__).resolve().parent.parent


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()


settings = get_settings()
