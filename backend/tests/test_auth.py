"""Authentication and authorization tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_login_success(client, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "TestPassword123!"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["user"]["username"] == "admin"
    assert "admin" in payload["user"]["roles"]


@pytest.mark.asyncio
async def test_login_wrong_password(client, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "whatever"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(client, admin_token):
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_refresh_token_rotates(client, admin_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "TestPassword123!"},
    )
    refresh = login.json()["refresh_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert response.status_code == 200
    new_token = response.json()["refresh_token"]
    assert new_token != refresh


@pytest.mark.asyncio
async def test_refresh_token_reuse_is_revoked(client, admin_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "TestPassword123!"},
    )
    refresh = login.json()["refresh_token"]

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert first.status_code == 200

    # Reusing the original (already rotated) token must fail.
    second = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_password_change(client, admin_token):
    response = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "current_password": "TestPassword123!",
            "new_password": "NewPassword456@",
        },
    )
    assert response.status_code == 200

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "NewPassword456@"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_anonymous(client):
    response = await client.get("/api/v1/services")
    assert response.status_code == 401
