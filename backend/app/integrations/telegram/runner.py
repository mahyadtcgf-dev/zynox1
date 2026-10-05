"""Telegram bot runner.

The bot token comes exclusively from TELEGRAM_BOT_TOKEN. Telegram users are
never administrators by default — every command resolves the linked panel user
and enforces panel RBAC.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.services.telegram_service import TelegramNotAuthorizedError

logger = get_logger(__name__)


def _bot_available() -> bool:
    try:
        from telegram import (
            Update,  # noqa: F401 - presence probe for python-telegram-bot  # type: ignore[import-not-found]
        )
        from telegram.ext import (  # type: ignore[import-not-found]
            Application,  # noqa: F401 - presence probe for python-telegram-bot
            CommandHandler,  # noqa: F401 - presence probe for python-telegram-bot
            ContextTypes,  # noqa: F401 - presence probe for python-telegram-bot
        )
        return True
    except ImportError:
        return False


async def start_bot() -> None:
    """Start long-polling if python-telegram-bot is installed."""
    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_BOT_TOKEN is not set; bot disabled")
        return

    try:
        from telegram import Update  # noqa: F401 - presence probe for python-telegram-bot
        from telegram.ext import (  # noqa: F401 - presence probe for python-telegram-bot
            Application,
            CommandHandler,
            ContextTypes,
        )
    except ImportError:
        logger.warning(
            "python-telegram-bot is not installed; telegram bot disabled. "
            "Install the 'telegram' optional dependency to enable it."
        )
        return

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    for name in ("start", "status", "services", "configs", "users", "server", "logs", "settings"):
        application.add_handler(CommandHandler(name, _make_handler(name)))

    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    logger.info("telegram bot is polling")


def _make_handler(command: str) -> Any:
    from telegram import Update  # noqa: F401 - presence probe for python-telegram-bot
    from telegram.ext import ContextTypes

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat is None or update.effective_user is None:
            return
        chat_id = update.effective_chat.id

        async with get_db() as db:  # type: ignore[attr-defined]
            from app.services.telegram_service import TelegramAuthService

            service = TelegramAuthService(db)
            try:
                user = await service.authorize_command(str(update.effective_user.id))
            except TelegramNotAuthorizedError as exc:
                await context.bot.send_message(chat_id=chat_id, text=str(exc))
                return

            text = await _build_response(command, db, user.username)

        await context.bot.send_message(chat_id=chat_id, text=text)

    return handler


async def _build_response(command: str, db: Any, username: str) -> str:
    from sqlalchemy import func, select

    from app.models import AuditLog, Service, ServiceConfig, User

    header = f"Zynox — {command}"

    if command == "start":
        return (
            f"{header}\n"
            f"Welcome, {username}. You are authorized.\n\n"
            "Commands:\n"
            "/status — system status\n"
            "/services — services\n"
            "/configs — configurations\n"
            "/users — users\n"
            "/server — server metrics\n"
            "/logs — recent activity\n"
            "/settings — settings\n"
        )

    if command == "status":
        services = await db.scalar(select(func.count()).select_from(Service))
        configs = await db.scalar(select(func.count()).select_from(ServiceConfig))
        users = await db.scalar(select(func.count()).select_from(User))
        return (
            f"{header}\n"
            f"Services: {services}\n"
            f"Configurations: {configs}\n"
            f"Users: {users}\n"
            f"Bot configured: {bool(settings.telegram_bot_token)}\n"
        )

    if command == "services":
        rows = (await db.execute(select(Service).limit(20))).scalars().all()
        if not rows:
            return f"{header}\nNo services."
        lines = [
            f"• {r.name} — {r.host}:{r.port} — {r.protocol}/{r.transport} — {r.status}"
            for r in rows
        ]
        return f"{header}\n" + "\n".join(lines)

    if command == "configs":
        rows = (await db.execute(select(ServiceConfig).limit(20))).scalars().all()
        if not rows:
            return f"{header}\nNo configurations."
        lines = [f"• {r.name} — {r.protocol}/{r.transport} — {r.host}:{r.port}" for r in rows]
        return f"{header}\n" + "\n".join(lines)

    if command == "users":
        rows = (await db.execute(select(User).limit(20))).scalars().all()
        if not rows:
            return f"{header}\nNo users."
        lines = [f"• {u.username} — {','.join(r.name for r in u.roles)}" for u in rows]
        return f"{header}\n" + "\n".join(lines)

    if command == "server":
        from app.services.monitoring_service import sample_metrics

        m = sample_metrics()
        return (
            f"{header}\n"
            f"CPU: {m.cpu_percent}%\n"
            f"Memory: {m.memory_percent}%\n"
            f"Disk: {m.disk_percent}%\n"
            f"Network RX: {m.network_rx_bps} B/s\n"
            f"Network TX: {m.network_tx_bps} B/s\n"
            f"Uptime: {m.uptime_seconds}s\n"
        )

    if command == "logs":
        rows = (
            await db.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)
            )
        ).scalars().all()
        if not rows:
            return f"{header}\nNo activity recorded."
        lines = [f"• {r.created_at:%Y-%m-%d %H:%M} — {r.actor_username} — {r.action}" for r in rows]
        return f"{header}\n" + "\n".join(lines)

    if command == "settings":
        return (
            f"{header}\n"
            f"App: {settings.app_name}\n"
            f"Environment: {settings.app_env}\n"
            f"Mini App URL: {settings.telegram_mini_app_url or 'not set'}\n"
        )

    return f"{header}\nUnknown command."
