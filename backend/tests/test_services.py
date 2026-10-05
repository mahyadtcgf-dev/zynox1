"""Service CRUD tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_service(auth_client):
    response = await auth_client.post(
        "/api/v1/services",
        json={
            "name": "edge-01",
            "host": "edge01.example.com",
            "port": 443,
            "protocol": "vless",
            "transport": "tcp",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["name"] == "edge-01"
    assert payload["protocol"] == "vless"
    assert payload["status"] == "unknown"


@pytest.mark.asyncio
async def test_list_services(auth_client):
    await auth_client.post(
        "/api/v1/services",
        json={
            "name": "edge-01",
            "host": "edge01.example.com",
            "port": 443,
            "protocol": "vless",
            "transport": "tcp",
        },
    )
    response = await auth_client.get("/api/v1/services")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert any(item["name"] == "edge-01" for item in payload["items"])


@pytest.mark.asyncio
async def test_update_service(auth_client):
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

    response = await auth_client.patch(
        f"/api/v1/services/{service_id}",
        json={"description": "Updated description", "port": 8443},
    )
    assert response.status_code == 200
    assert response.json()["port"] == 8443


@pytest.mark.asyncio
async def test_delete_service(auth_client):
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

    response = await auth_client.delete(f"/api/v1/services/{service_id}")
    assert response.status_code == 200

    listing = await auth_client.get("/api/v1/services")
    assert not any(item["id"] == service_id for item in listing.json()["items"])


@pytest.mark.asyncio
async def test_service_action_rejects_unknown_action(auth_client):
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

    response = await auth_client.post(
        f"/api/v1/services/{service_id}/action",
        json={"action": "rm -rf /"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_connectivity_test_action(auth_client):
    created = await auth_client.post(
        "/api/v1/services",
        json={
            "name": "edge-01",
            "host": "127.0.0.1",
            "port": 1,
            "protocol": "vless",
            "transport": "tcp",
        },
    )
    service_id = created.json()["id"]

    response = await auth_client.post(
        f"/api/v1/services/{service_id}/action",
        json={"action": "test"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "test"
    assert payload["status"] in {"stopped", "degraded", "running"}
