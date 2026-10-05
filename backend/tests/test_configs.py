"""Configuration CRUD and validation tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_generate_vless_tcp_tls(auth_client):
    response = await auth_client.post(
        "/api/v1/configurations/generate",
        json={
            "config": {
                "name": "client-01",
                "protocol": "vless",
                "transport": "tcp",
                "host": "edge01.example.com",
                "port": 443,
                "security": "tls",
                "sni": "edge01.example.com",
                "flow": "xtls-rprx-vision",
            }
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["share_url"].startswith("vless://")
    assert "xtls-rprx-vision" in payload["share_url"]
    assert payload["xray"]["protocol"] == "vless"
    assert payload["config"]["uuid"]


@pytest.mark.asyncio
async def test_generate_vmess_ws(auth_client):
    response = await auth_client.post(
        "/api/v1/configurations/generate",
        json={
            "config": {
                "name": "client-ws",
                "protocol": "vmess",
                "transport": "ws",
                "host": "edge01.example.com",
                "port": 443,
                "path": "/ray",
                "security": "tls",
                "sni": "edge01.example.com",
            }
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["share_url"].startswith("vmess://")
    assert payload["xray"]["streamSettings"]["network"] == "ws"
    assert payload["xray"]["streamSettings"]["wsSettings"]["path"] == "/ray"


@pytest.mark.asyncio
async def test_generate_xhttp(auth_client):
    response = await auth_client.post(
        "/api/v1/configurations/generate",
        json={
            "config": {
                "name": "client-xhttp",
                "protocol": "vless",
                "transport": "xhttp",
                "host": "edge01.example.com",
                "port": 443,
                "path": "/xhttp",
                "security": "tls",
                "sni": "edge01.example.com",
                "extra": {"mode": "stream-one"},
            }
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["xray"]["streamSettings"]["network"] == "xhttp"
    settings = payload["xray"]["streamSettings"]["xhttpSettings"]
    assert settings["mode"] == "stream-one"
    assert settings["path"] == "/xhttp"


@pytest.mark.asyncio
async def test_generate_rejects_invalid_xhttp_mode(auth_client):
    response = await auth_client.post(
        "/api/v1/configurations/generate",
        json={
            "config": {
                "name": "client-bad",
                "protocol": "vless",
                "transport": "xhttp",
                "host": "edge01.example.com",
                "port": 443,
                "security": "none",
                "extra": {"mode": "not-a-real-mode"},
            }
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_rejects_flow_without_tls(auth_client):
    response = await auth_client.post(
        "/api/v1/configurations/generate",
        json={
            "config": {
                "name": "client-bad",
                "protocol": "vless",
                "transport": "tcp",
                "host": "edge01.example.com",
                "port": 443,
                "security": "none",
                "flow": "xtls-rprx-vision",
            }
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_rejects_flow_on_wrong_protocol(auth_client):
    response = await auth_client.post(
        "/api/v1/configurations/generate",
        json={
            "config": {
                "name": "client-bad",
                "protocol": "trojan",
                "transport": "tcp",
                "host": "edge01.example.com",
                "port": 443,
                "security": "tls",
                "sni": "edge01.example.com",
                "flow": "xtls-rprx-vision",
            }
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_rejects_tls_without_sni(auth_client):
    response = await auth_client.post(
        "/api/v1/configurations/generate",
        json={
            "config": {
                "name": "client-bad",
                "protocol": "vless",
                "transport": "ws",
                "host": "edge01.example.com",
                "port": 443,
                "security": "reality",
            }
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_and_list_config(auth_client):
    created = await auth_client.post(
        "/api/v1/configurations",
        json={
            "name": "persisted-01",
            "protocol": "vless",
            "transport": "tcp",
            "host": "edge01.example.com",
            "port": 443,
            "security": "tls",
            "sni": "edge01.example.com",
        },
    )
    assert created.status_code == 201, created.text
    config_id = created.json()["id"]

    listing = await auth_client.get("/api/v1/configurations")
    assert listing.status_code == 200
    assert any(item["id"] == config_id for item in listing.json()["items"])


@pytest.mark.asyncio
async def test_duplicate_config(auth_client):
    created = await auth_client.post(
        "/api/v1/configurations",
        json={
            "name": "to-duplicate",
            "protocol": "vless",
            "transport": "ws",
            "host": "edge01.example.com",
            "port": 443,
            "path": "/ray",
            "security": "tls",
            "sni": "edge01.example.com",
        },
    )
    config_id = created.json()["id"]

    response = await auth_client.post(
        f"/api/v1/configurations/{config_id}/duplicate", json={"name": "duplicated"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "duplicated"
    assert response.json()["uuid"] != created.json()["uuid"]


@pytest.mark.asyncio
async def test_enable_disable_config(auth_client):
    created = await auth_client.post(
        "/api/v1/configurations",
        json={
            "name": "toggle-me",
            "protocol": "vless",
            "transport": "tcp",
            "host": "edge01.example.com",
            "port": 443,
            "security": "none",
        },
    )
    config_id = created.json()["id"]

    disabled = await auth_client.post(f"/api/v1/configurations/{config_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    enabled = await auth_client.post(f"/api/v1/configurations/{config_id}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


@pytest.mark.asyncio
async def test_delete_config(auth_client):
    created = await auth_client.post(
        "/api/v1/configurations",
        json={
            "name": "delete-me",
            "protocol": "vless",
            "transport": "tcp",
            "host": "edge01.example.com",
            "port": 443,
            "security": "none",
        },
    )
    config_id = created.json()["id"]

    response = await auth_client.delete(f"/api/v1/configurations/{config_id}")
    assert response.status_code == 200

    listing = await auth_client.get("/api/v1/configurations")
    assert not any(item["id"] == config_id for item in listing.json()["items"])


@pytest.mark.asyncio
async def test_export_config(auth_client):
    created = await auth_client.post(
        "/api/v1/configurations",
        json={
            "name": "export-me",
            "protocol": "vless",
            "transport": "tcp",
            "host": "edge01.example.com",
            "port": 443,
            "security": "tls",
            "sni": "edge01.example.com",
        },
    )
    config_id = created.json()["id"]

    response = await auth_client.get(f"/api/v1/configurations/{config_id}/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.json()["protocol"] == "vless"
