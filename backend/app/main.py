"""Application factory and lifespan management."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app import __version__
from app.api import (
    auth,
    configurations,
    misc,
    services,
    telegram,
    users,
)
from app.core.config import settings
from app.core.database import engine, get_db_session, wait_for_database
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.services.auth_service import AuthError, InvalidCredentialsError, TOTPRequiredError

logger = get_logger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent


async def _run_migrations() -> None:
    """Run Alembic to head. Idempotent; never destroys data."""
    from alembic import command
    from alembic.config import Config

    ini = BACKEND_ROOT / "alembic.ini"
    if not ini.exists():
        logger.warning("alembic.ini not found; skipping migrations")
        return

    config = Config(str(ini))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.async_database_url)
    # Keep the application's logging configuration. Without this, Alembic's
    # fileConfig() repoints the root logger at alembic.ini (WARNING + plain
    # stderr handler) and every app log line after startup is lost.
    config.attributes["configure_logger"] = False

    def _upgrade() -> None:
        command.upgrade(config, "head")

    await asyncio.to_thread(_upgrade)
    logger.info("database migrations complete")


async def _seed_initial_data() -> None:
    """Seed roles, permissions, and the initial admin if absent."""
    from app.core.security import hash_password
    from app.models import Permission, Role, User
    from app.models.role import PERMISSIONS, ROLE_PERMISSIONS

    async with get_db_session() as db:
        # Permissions. `.scalars()` over a single-column SELECT yields plain
        # strings, so the previous `p.name` raised AttributeError on every
        # startup after the first one and aborted the whole lifespan.
        existing_perms = set(
            (await db.execute(text("SELECT name FROM permissions"))).scalars().all()
        )
        for name, description in PERMISSIONS:
            if name not in existing_perms:
                db.add(Permission(name=name, description=description))
        await db.flush()

        # Roles
        for role_name, perm_names in ROLE_PERMISSIONS.items():
            role = (
                await db.execute(
                    text("SELECT id, permissions FROM roles WHERE name = :n"),
                    {"n": role_name},
                )
            ).first()
            if role is None:
                db.add(
                    Role(
                        name=role_name,
                        description=f"System role: {role_name}",
                        is_system=True,
                        permissions=",".join(perm_names),
                    )
                )
        await db.flush()

        # Initial admin
        admin = (
            await db.execute(
                text("SELECT id FROM users WHERE username = :u"),
                {"u": settings.admin_username},
            )
        ).first()
        if admin is None:
            admin_role = (
                await db.execute(text("SELECT id FROM roles WHERE name = 'admin'"))
            ).scalar()
            user = User(
                username=settings.admin_username,
                email=f"{settings.admin_username}@zynox.local",
                password_hash=hash_password(settings.admin_password),
                is_active=True,
            )
            admin_role_obj = await db.get(Role, admin_role) if admin_role else None
            # Only attach the role when it actually resolved; never put a None
            # entry into a list typed as list[Role].
            user.roles = [admin_role_obj] if admin_role_obj is not None else []
            db.add(user)
        await db.commit()

    logger.info("database seeding complete")


async def _start_telegram_bot() -> None:
    """Start the Telegram bot polling loop if configured."""
    if not settings.telegram_bot_token:
        logger.info("telegram bot token not set; bot disabled")
        return
    try:
        from app.integrations.telegram.runner import start_bot

        await start_bot()
        logger.info("telegram bot started")
    except Exception:  # noqa: BLE001 — the panel must not fail if the bot cannot start
        logger.exception("failed to start telegram bot")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info(
        "application starting",
        extra={
            "app_name": settings.app_name,
            "version": __version__,
            "env": settings.app_env,
            "port": settings.effective_port(),
        },
    )

    try:
        await wait_for_database()
        await _run_migrations()
        await _seed_initial_data()
    except Exception:
        logger.exception("startup failed")
        raise

    await _start_telegram_bot()

    try:
        yield
    finally:
        logger.info("application shutting down")
        await engine.dispose()
        logger.info("application stopped")


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title=f"{settings.app_name} API",
        description=f"Management API for {settings.app_name}.",
        version=__version__,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware (order: outermost first) ──────────────────
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_credentials=False,
        allow_methods=("GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"),
        allow_headers=("Authorization", "Content-Type", "X-Request-Id"),
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    # ── Routers ──────────────────────────────────────────────
    api_prefix = "/api/v1"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(services.router, prefix=api_prefix)
    app.include_router(configurations.router, prefix=api_prefix)
    app.include_router(users.router, prefix=api_prefix)
    app.include_router(telegram.router, prefix=api_prefix)
    app.include_router(misc.settings_router, prefix=api_prefix)
    app.include_router(misc.logs_router, prefix=api_prefix)
    app.include_router(misc.dashboard_router, prefix=api_prefix)
    app.include_router(misc.servers_router, prefix=api_prefix)
    app.include_router(misc.metrics_router, prefix=api_prefix)

    # ── Static assets + SPA fallback ────────────────────────
    static_dir = BACKEND_ROOT / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    # Mount only when the production frontend build is present. In development
    # the Vite dev server serves assets, and the backend must still boot.
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # ── Exception handlers ──────────────────────────────────
    # AuthError is raised inside the service layer; it must never surface as a 500.
    @app.exception_handler(InvalidCredentialsError)
    async def _invalid_credentials(
        _request: Request, exc: InvalidCredentialsError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(exc)},
        )

    @app.exception_handler(TOTPRequiredError)
    async def _totp_required(_request: Request, exc: TOTPRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(exc), "error_code": "totp_required"},
        )

    @app.exception_handler(AuthError)
    async def _auth_error(_request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        # Validation helpers raise plain ValueError; surface it as 422, never 500.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc)},
        )

    # ── Health ──────────────────────────────────────────────
    @app.get("/health", tags=["health"])
    async def health() -> dict[str, object]:
        return {"status": "ok", "app": settings.app_name, "version": __version__}

    @app.get("/ready", tags=["health"])
    async def ready() -> JSONResponse:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "error": str(exc)},
            )
        return JSONResponse(status_code=200, content={"status": "ready"})

    @app.get("/", include_in_schema=False, response_model=None)
    async def root() -> FileResponse | HTMLResponse:
        index = BACKEND_ROOT / "static" / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse(
            f"<html><body><h1>{settings.app_name}</h1>"
            "<p>Frontend build not present. See docs/DEPLOYMENT.md.</p></body></html>"
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.effective_port(),
        log_level=settings.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
