"""Transport abstraction.

A single `TransportParams` family with concrete implementations for TCP,
WebSocket, and xHTTP. Each implementation validates only the parameters that
apply to it and emits only the fields the target protocol actually supports.

References:
- TCP / WebSocket stream settings: Xray-core documentation
- xHTTP transport (successor to SplitHTTP), Xray-core 1.8.24+
- VLESS flow values (xtls-rprx-vision) for VLESS + TCP + TLS
- utls fingerprints supported by Xray-core
"""

from __future__ import annotations

import abc
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import validate_domain, validate_path

# ── Enums ────────────────────────────────────────────────────


class TransportType(str, Enum):  # noqa: UP042 - JSON must serialise to the raw value
    tcp = "tcp"
    ws = "ws"
    xhttp = "xhttp"


class ProtocolType(str, Enum):  # noqa: UP042 - JSON must serialise to the raw value
    vless = "vless"
    vmess = "vmess"
    trojan = "trojan"


class SecurityType(str, Enum):  # noqa: UP042 - JSON must serialise to the raw value
    none = "none"
    tls = "tls"
    reality = "reality"
    xtls = "xtls"


# Flow values documented for VLESS + TCP + TLS (vision flow).
VLESS_FLOWS = ("xtls-rprx-vision", "xtls-rprx-direct", "xtls-rprx-origin")

# utls fingerprints supported by Xray-core.
UTLS_FINGERPRINTS = (
    "chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq",
    "random", "randomized",
)

# xHTTP modes as documented for the "xhttp" transport.
XHTTP_MODES = ("packet-up", "stream-up", "stream-one")


# ── Base transport model ─────────────────────────────────────


class TransportParams(BaseModel):
    """Base validated transport parameters."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    security: SecurityType = SecurityType.none
    sni: str | None = Field(default=None, max_length=255)
    fingerprint: str | None = Field(default=None, max_length=64)
    alpn: str | None = Field(default=None, max_length=128)
    allow_insecure: bool = False

    @model_validator(mode="after")
    def _validate_tls(self) -> TransportParams:
        if self.security in (SecurityType.tls, SecurityType.reality, SecurityType.xtls):
            if not self.sni:
                raise ValueError("sni is required when security is tls/reality/xtls")
            self.sni = validate_domain(self.sni)
            if self.fingerprint is not None and self.fingerprint not in UTLS_FINGERPRINTS:
                raise ValueError(f"unsupported fingerprint: {self.fingerprint}")
        return self

    @abc.abstractmethod
    def transport_name(self) -> TransportType:
        ...

    @abc.abstractmethod
    def to_xray(self, protocol: ProtocolType) -> dict[str, Any]:
        """Emit the Xray-core `streamSettings` dictionary."""
        ...

    def to_metadata(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def _tls_block(self) -> dict[str, Any]:
        """Shared TLS/reality settings emitter."""
        if self.security == SecurityType.none:
            return {}

        tls_settings: dict[str, Any] = {
            "serverName": self.sni,
            "allowInsecure": self.allow_insecure,
        }
        if self.alpn:
            tls_settings["alpn"] = [a.strip() for a in self.alpn.split(",") if a.strip()]
        if self.fingerprint:
            tls_settings["fingerprint"] = self.fingerprint

        return {"security": self.security.value, "tlsSettings": tls_settings}


# ── TCP ──────────────────────────────────────────────────────


class TCPParams(TransportParams):
    """TCP transport.

    Supports host, port, security, TLS, SNI, flow. `flow` belongs on the account
    in Xray-core, but the panel stores it here because that is where users
    configure it; the generator places it on the account.
    """

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    flow: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _validate_tcp(self) -> TCPParams:
        if self.flow:
            if self.security not in (SecurityType.tls, SecurityType.xtls):
                raise ValueError("flow is only used with VLESS + TLS/XTLS")
            if self.flow not in VLESS_FLOWS:
                raise ValueError(f"unsupported flow: {self.flow}")
        return self

    def transport_name(self) -> TransportType:
        return TransportType.tcp

    def to_xray(self, protocol: ProtocolType) -> dict[str, Any]:
        stream: dict[str, Any] = {
            "network": "tcp",
            "security": self.security.value,
        }
        if self.security != SecurityType.none:
            stream.update(self._tls_block())
        return stream

    def to_metadata(self) -> dict[str, Any]:
        return super().to_metadata()


# ── WebSocket ────────────────────────────────────────────────


class WebSocketParams(TransportParams):
    """WebSocket transport.

    Supports host, port, path, Host header, TLS, SNI.
    """

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    path: str = Field(default="/", max_length=512)
    host_header: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _validate_ws(self) -> WebSocketParams:
        self.path = validate_path(self.path) or "/"
        return self

    def transport_name(self) -> TransportType:
        return TransportType.ws

    def to_xray(self, protocol: ProtocolType) -> dict[str, Any]:
        ws_settings: dict[str, Any] = {"path": self.path}
        if self.host_header:
            ws_settings["headers"] = {"Host": self.host_header}

        stream: dict[str, Any] = {
            "network": "ws",
            "security": self.security.value,
            "wsSettings": ws_settings,
        }
        if self.security != SecurityType.none:
            stream.update(self._tls_block())
        return stream

    def to_metadata(self) -> dict[str, Any]:
        data = super().to_metadata()
        data["host_header"] = self.host_header
        return data


# ── xHTTP ────────────────────────────────────────────────────


class XHTTPParams(TransportParams):
    """xHTTP transport (Xray-core 1.8.24+, successor to SplitHTTP).

    Supports host, port, path, mode, Host header, TLS, SNI, and a small set of
    documented extra parameters.
    """

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    path: str = Field(default="/", max_length=512)
    mode: str = Field(default="packet-up", max_length=32)
    host_header: str | None = Field(default=None, max_length=255)
    extra: dict[str, Any] | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_xhttp(self) -> XHTTPParams:
        if self.mode not in XHTTP_MODES:
            raise ValueError(
                f"unsupported xhttp mode: {self.mode}; use one of {', '.join(XHTTP_MODES)}"
            )
        self.path = validate_path(self.path) or "/"
        return self

    def transport_name(self) -> TransportType:
        return TransportType.xhttp

    def to_xray(self, protocol: ProtocolType) -> dict[str, Any]:
        settings: dict[str, Any] = {"mode": self.mode, "path": self.path}
        if self.host_header:
            settings["host"] = self.host_header
        if self.extra:
            settings.update(self.extra)

        stream: dict[str, Any] = {
            "network": "xhttp",
            "security": self.security.value,
            "xhttpSettings": settings,
        }
        if self.security != SecurityType.none:
            block = self._tls_block()
            stream["security"] = block["security"]
            stream["tlsSettings"] = block["tlsSettings"]
        return stream

    def to_metadata(self) -> dict[str, Any]:
        data = super().to_metadata()
        data["mode"] = self.mode
        data["host_header"] = self.host_header
        data["extra"] = dict(self.extra) if self.extra else None
        return data


# ── Registry / factory ───────────────────────────────────────

TRANSPORT_CLASSES: dict[TransportType, type[TransportParams]] = {
    TransportType.tcp: TCPParams,
    TransportType.ws: WebSocketParams,
    TransportType.xhttp: XHTTPParams,
}


def transport_for(transport: TransportType | str) -> type[TransportParams]:
    """Resolve the parameter class for a transport name."""
    if isinstance(transport, str):
        try:
            transport = TransportType(transport)
        except ValueError:
            raise ValueError(f"unsupported transport: {transport!r}") from None
    return TRANSPORT_CLASSES[transport]


def build_transport(
    transport: TransportType | str, data: dict[str, Any]
) -> TransportParams:
    """Validate `data` against the transport-specific parameter model."""
    return transport_for(transport)(**data)
