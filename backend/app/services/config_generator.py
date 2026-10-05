"""Configuration generation.

API → Configuration Service → Validation → Transport Builder →
Protocol Builder → Output Generator

Nothing is built by string concatenation of unvalidated input. Every value is
typed and validated before it reaches the output builders.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import uuid as uuid_module
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.schemas.config import ConfigBase, ConfigCreateIn, ConfigOut
from app.schemas.transports import (
    ProtocolType,
    SecurityType,
    TransportParams,
    TransportType,
)

logger = get_logger(__name__)


class ConfigGenerationError(ValueError):
    """Raised when a configuration cannot be generated or is invalid."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


# ── Protocol builder ─────────────────────────────────────────


def build_account(protocol: ProtocolType, client_uuid: str, flow: str | None) -> dict[str, Any]:
    """Build the Xray-core account block for a protocol."""
    if protocol == ProtocolType.vless:
        account: dict[str, Any] = {"id": client_uuid}
        if flow:
            account["flow"] = flow
        return account
    if protocol == ProtocolType.vmess:
        # VMess uses a UUID as the user id.
        return {"id": client_uuid, "alterId": 0}
    if protocol == ProtocolType.trojan:
        return {"password": client_uuid}
    raise ConfigGenerationError(f"unsupported protocol: {protocol}")


def build_share_url(
    protocol: ProtocolType,
    client_uuid: str,
    transport_params: TransportParams,
    tag: str,
) -> str:
    """Build the standard share URL for the protocol.

    VLESS  : vless://uuid@host:port?type=tcp&security=tls&...
    VMess  : vmess://base64(json)
    Trojan : trojan://password@host:port?...
    """
    host = transport_params.host  # type: ignore[attr-defined]
    port = transport_params.port  # type: ignore[attr-defined]

    if not host or not port:
        raise ConfigGenerationError("host and port are required to build a share URL")

    query: dict[str, str] = {"type": transport_params.transport_name().value}

    if transport_params.security != SecurityType.none:
        query["security"] = transport_params.security.value
        sni = transport_params.sni
        if sni:
            query["sni"] = sni
        if transport_params.fingerprint:
            query["fp"] = transport_params.fingerprint
        if transport_params.alpn:
            query["alpn"] = transport_params.alpn
        if getattr(transport_params, "allow_insecure", False):
            query["allowInsecure"] = "1"

    if transport_params.transport_name() == TransportType.ws:
        query["path"] = getattr(transport_params, "path", "/")
        header = getattr(transport_params, "host_header", None)
        if header:
            query["host"] = header
    elif transport_params.transport_name() == TransportType.xhttp:
        query["path"] = getattr(  # noqa: B008 — guarded getattr
            transport_params, "path", "/"
        )
        mode = getattr(  # noqa: B008 — guarded getattr
            transport_params, "mode", "packet-up"
        )
        query["mode"] = mode
        header = getattr(transport_params, "host_header", None)
        if header:
            query["host"] = header

    flow = getattr(transport_params, "flow", None)
    if protocol == ProtocolType.vless and flow:
        query["flow"] = flow

    if protocol == ProtocolType.vmess:
        payload = {
            "v": "2",
            "ps": tag,
            "add": host,
            "port": str(port),
            "id": client_uuid,
            "aid": "0",
            "scy": "auto",
            "net": transport_params.transport_name().value,
            "type": "none",
            "host": getattr(transport_params, "host_header", "") or "",
            "path": getattr(transport_params, "path", "/") or "/",
            "tls": (
                ""
                if transport_params.security == SecurityType.none
                else transport_params.security.value
            ),
            "sni": transport_params.sni or "",
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        return f"vmess://{encoded}"

    if protocol == ProtocolType.vless:
        qs = urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
        return f"vless://{client_uuid}@{host}:{port}?{qs}#{urllib.parse.quote(tag)}"

    if protocol == ProtocolType.trojan:
        qs = urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
        return f"trojan://{client_uuid}@{host}:{port}?{qs}#{urllib.parse.quote(tag)}"

    raise ConfigGenerationError(f"unsupported protocol: {protocol}")


# ── Transport builder ────────────────────────────────────────


def build_stream_settings(
    transport_params: TransportParams, protocol: ProtocolType
) -> dict[str, Any]:
    return transport_params.to_xray(protocol)


# ── Output generator ─────────────────────────────────────────


@dataclass(frozen=True)
class GeneratedConfig:
    config_model: ConfigBase
    client_uuid: str
    share_url: str
    xray_inbound_client: dict[str, Any]
    xray_stream_settings: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.client_uuid,
            "share_url": self.share_url,
            "account": self.xray_inbound_client,
            "stream_settings": self.xray_stream_settings,
        }


def generate_uuid() -> str:
    return str(uuid_module.uuid4())


def generate_config(
    payload: ConfigCreateIn,
    *,
    client_uuid: str | None = None,
) -> GeneratedConfig:
    """Full generation pipeline: validate → build transport → build protocol → output."""
    # ── 1. Validation happens inside the Pydantic model ─────
    transport_params = payload.transport_params()

    # ── 2. Client identity ───────────────────────────────────
    if client_uuid is None:
        client_uuid = payload.uuid or generate_uuid()

    # ── 3. Protocol builder ──────────────────────────────────
    flow = getattr(transport_params, "flow", None)
    account = build_account(payload.protocol, client_uuid, flow)

    # ── 4. Transport builder ────────────────────────────────
    stream_settings = build_stream_settings(transport_params, payload.protocol)

    # ── 5. Output generator ─────────────────────────────────
    share_url = build_share_url(payload.protocol, client_uuid, transport_params, payload.name)

    logger.info(
        "configuration generated",
        extra={
            "protocol": payload.protocol.value,
            "transport": payload.transport.value,
            # Not "name": that is a reserved LogRecord attribute and raises
            # KeyError in Logger.makeRecord, which turns every successful
            # generation into an HTTP 500.
            "config_name": payload.name,
        },
    )

    return GeneratedConfig(
        config_model=payload,
        client_uuid=client_uuid,
        share_url=share_url,
        xray_inbound_client=account,
        xray_stream_settings=stream_settings,
    )


def build_xray_inbound(
    generated: GeneratedConfig,
    *,
    tag: str,
    listen: str = "0.0.0.0",  # noqa: S104 - Xray inbound must bind every interface
    port: int | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Assemble a complete Xray-core inbound for one client."""
    port = port if port is not None else generated.config_model.port
    client = dict(generated.xray_inbound_client)
    if email:
        client["email"] = email

    return {
        "tag": tag,
        "listen": listen,
        "port": port,
        "protocol": generated.config_model.protocol.value,
        "settings": {"clients": [client], "decryption": "none"},
        "streamSettings": generated.xray_stream_settings,
        "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
    }


def config_model_to_out(
    generated: GeneratedConfig, record: Any
) -> ConfigOut:
    """Map a generated config plus its DB record to ConfigOut."""
    return ConfigOut.model_validate(record)


def qr_code_data_url(text: str) -> str:
    """Return a QR code as a data URL, or None if qrcode is unavailable."""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return ""
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(text, image_factory=factory, box_size=8, border=2)
    import io

    buffer = io.BytesIO()
    img.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
