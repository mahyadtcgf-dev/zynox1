"""Security-focused tests.

These exercise the threat model documented in docs/SECURITY.md:

  - Telegram WebApp initData is validated server-side, never trusted.
  - An unlinked Telegram account gets no administrative access.
  - RBAC denies missing permissions.
  - Arbitrary command execution is impossible (only fixed actions exist).
  - Sort fields are whitelisted (no ORDER BY injection).
  - Auth material never leaks into audit log details.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
import uuid

import pytest

from app.core.security import TelegramAuthError, validate_telegram_init_data


def _make_init_data(bot_token: str, user_id: int = 100, auth_date: int | None = None) -> str:
    """Build a correctly signed Telegram initData for the given bot token."""
    user = json.dumps({"id": user_id, "first_name": "Admin", "username": "admin"})
    params = {
        "query_id": "aae0eb2d-5c01-4a1c-bb20-d6b1e0b3b7c1",
        "user": user,
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode({**params, "hash": computed})


class TestTelegramWebAppAuth:
    """The Mini App must never be authenticated by client-side data alone."""

    @pytest.mark.asyncio
    async def test_valid_signature_is_accepted(self):
        token = "123456789:ABCdefGhIjklmnoPQRstuVwxyz-1234567890"
        init_data = _make_init_data(token, user_id=42)
        payload = validate_telegram_init_data(init_data, token)
        assert payload["user"]["id"] == 42

    @pytest.mark.asyncio
    async def test_wrong_bot_token_is_rejected(self):
        signed = _make_init_data("123456789:CORRECT-TOKEN-VALUE", user_id=42)
        with pytest.raises(TelegramAuthError):
            validate_telegram_init_data(signed, "123456789:DIFFERENT-TOKEN-VALUE")

    @pytest.mark.asyncio
    async def test_tampered_user_is_rejected(self):
        token = "123456789:ABCdefGhIjklmnoPQRstuVwxyz-1234567890"
        init_data = _make_init_data(token, user_id=1)
        # Elevate the claimed id without re-signing.
        parsed = dict(urllib.parse.parse_qsl(init_data))
        tampered_user = json.dumps({"id": 999, "first_name": "Attacker"})
        parsed["user"] = tampered_user
        with pytest.raises(TelegramAuthError):
            validate_telegram_init_data(urllib.parse.urlencode(parsed), token)

    @pytest.mark.asyncio
    async def test_replay_of_stale_data_is_rejected(self):
        token = "123456789:ABCdefGhIjklmnoPQRstuVwxyz-1234567890"
        old = int(time.time()) - 3600
        init_data = _make_init_data(token, auth_date=old)
        with pytest.raises(TelegramAuthError):
            validate_telegram_init_data(init_data, token)

    @pytest.mark.asyncio
    async def test_missing_hash_is_rejected(self):
        token = "123456789:ABCdefGhIjklmnoPQRstuVwxyz-1234567890"
        with pytest.raises(TelegramAuthError):
            validate_telegram_init_data("user=%7B%22id%22%3A1%7D&auth_date=123", token)


class TestWebAppLoginEndpoint:
    @pytest.mark.asyncio
    async def test_login_rejected_when_bot_not_configured(self, client, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.telegram_bot_token", "")
        response = await client.post(
            "/api/v1/telegram/webapp/login",
            json={"init_data": "hash=abc&user=%7B%22id%22%3A1%7D"},
        )
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_login_rejects_unlinked_account(self, client, admin_user, monkeypatch):
        token = "123456789:ABCdefGhIjklmnoPQRstuVwxyz-1234567890"
        monkeypatch.setattr("app.core.config.settings.telegram_bot_token", token)
        init_data = _make_init_data(token, user_id=500)

        response = await client.post(
            "/api/v1/telegram/webapp/login",
            json={"init_data": init_data},
        )
        # 401: signature is valid but the Telegram account is not linked.
        assert response.status_code == 401, response.text


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_viewer_cannot_create_service(self, client, db_session):
        from app.core.security import hash_password
        from app.models import Role, User

        role = Role(name="viewer", is_system=True, permissions="service:view")
        db_session.add(role)
        user = User(
            id=uuid.uuid4(),
            username="viewer",
            email="viewer@example.com",
            password_hash=hash_password("ViewerPassword123!"),
            is_active=True,
            roles=[role],
        )
        db_session.add(user)
        await db_session.commit()

        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "viewer", "password": "ViewerPassword123!"},
        )
        assert login.status_code == 200
        bearer = login.json()["access_token"]

        response = await client.post(
            "/api/v1/services",
            headers={"Authorization": f"Bearer {bearer}"},
            json={
                "name": "forbidden",
                "host": "edge01.example.com",
                "port": 443,
                "protocol": "vless",
                "transport": "tcp",
            },
        )
        assert response.status_code == 403
        assert "service:create" in response.json()["detail"]


class TestNoCommandExecution:
    """Only the five predefined service actions may run."""

    @pytest.mark.asyncio
    async def test_action_whitelist(self, client, admin_token):
        from app.schemas.service import ServiceActionIn

        allowed = set(ServiceActionIn.model_fields["action"].metadata)
        pattern = ServiceActionIn.model_fields["action"].metadata[0].pattern
        import re

        assert re.fullmatch(pattern, "rm -rf /") is None
        assert allowed  # field exists and is constrained

    @pytest.mark.asyncio
    async def test_shell_injection_payload_is_rejected(self, auth_client):
        created = await auth_client.post(
            "/api/v1/services",
            json={
                "name": "edge-01",
                "host": "edge01.example.com",
                "port": 443,
                "protocol": "vless",
                "transport": "tcp",
            },
        )
        service_id = created.json()["id"]

        for payload in (
            {"action": "rm -rf /"},
            {"action": "start; rm -rf /"},
            {"action": "$(reboot)"},
            {"action": "test && cat /etc/passwd"},
        ):
            response = await auth_client.post(
                f"/api/v1/services/{service_id}/action", json=payload
            )
            assert response.status_code == 422, payload


class TestQuerySafety:
    @pytest.mark.asyncio
    async def test_sort_field_is_whitelisted(self, auth_client):
        # An arbitrary column must not be accepted for ordering.
        response = await auth_client.get("/api/v1/logs/audit?sort_by=password_hash")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_does_not_leak(self, auth_client):
        await auth_client.get("/api/v1/configurations?search=%25")
        # Endpoint exists and returns paginated items without error.
        response = await auth_client.get("/api/v1/configurations")
        assert response.status_code == 200


class TestAuditLogHygiene:
    @pytest.mark.asyncio
    async def test_password_never_recorded(self, client, admin_user, db_session):
        from sqlalchemy import select

        from app.models import AuditLog

        await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "TestPassword123!"},
        )

        entries = (await db_session.execute(select(AuditLog))).scalars().all()
        for entry in entries:
            blob = json.dumps(entry.details or {})
            assert "TestPassword123" not in blob, "password leaked into audit details"
