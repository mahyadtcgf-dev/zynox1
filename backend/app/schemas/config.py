"""Configuration schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ORMModel, validate_host, validate_path, validate_uuid
from app.schemas.transports import (
    ProtocolType,
    SecurityType,
    TransportParams,
    TransportType,
    build_transport,
)


class ConfigBase(BaseModel):
    """Transport-agnostic configuration fields with cross-field validation."""

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    name: str = Field(min_length=1, max_length=128)
    protocol: ProtocolType
    transport: TransportType

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)

    service_id: UUID | None = None

    path: str | None = Field(default=None, max_length=512)
    host_header: str | None = Field(default=None, max_length=255)
    sni: str | None = Field(default=None, max_length=255)
    flow: str | None = Field(default=None, max_length=64)

    security: SecurityType = SecurityType.none
    tls_server_name: str | None = Field(default=None, max_length=255)
    fingerprint: str | None = Field(default=None, max_length=64)
    alpn: str | None = Field(default=None, max_length=128)
    allow_insecure: bool = False

    extra: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=2048)
    expires_at: datetime | None = None

    # ── Cross-field validation ────────────────────────────────
    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        return validate_host(v)

    @field_validator("path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        return validate_path(v)

    @model_validator(mode="after")
    def _consistency(self) -> ConfigBase:
        # TLS falls back to the host when the caller omits the SNI.
        if self.security == SecurityType.tls and not self.sni and not self.tls_server_name:
            self.sni = validate_host(self.host)

        # REALITY / XTLS require an explicit SNI — no implicit fallback, because
        # the server name must match a server-side certificate/Reality config.
        if self.security in (SecurityType.reality, SecurityType.xtls) and (
                not self.sni and not self.tls_server_name
        ):
                raise ValueError(f"{self.security.value} requires an explicit SNI")

        # Flow is only meaningful for VLESS over TCP with TLS/XTLS.
        if self.flow:
            if self.protocol != ProtocolType.vless:
                raise ValueError("flow is only supported by VLESS")
            if self.transport != TransportType.tcp:
                raise ValueError("flow is only supported over TCP")
            if self.security == SecurityType.none:
                raise ValueError("flow requires TLS or XTLS security")

        # Path is only meaningful for ws / xhttp.
        if self.path and self.transport == TransportType.tcp:
            raise ValueError("path is not used by the TCP transport")

        return self

    # ── Transport binding ─────────────────────────────────────
    def transport_params(self) -> TransportParams:
        """Build and validate the transport-specific parameter model."""
        data: dict[str, Any] = {
            "security": self.security,
            "sni": self.sni or self.tls_server_name,
            "fingerprint": self.fingerprint,
            "alpn": self.alpn,
            "allow_insecure": self.allow_insecure,
            "host": self.host,
            "port": self.port,
        }
        if self.transport == TransportType.ws:
            data["path"] = self.path or "/"
            data["host_header"] = self.host_header
        elif self.transport == TransportType.xhttp:
            data["path"] = self.path or "/"
            data["host_header"] = self.host_header
            mode = (self.extra or {}).get("mode", "packet-up")
            data["mode"] = mode
            data["extra"] = {k: v for k, v in (self.extra or {}).items() if k != "mode"}
        elif self.transport == TransportType.tcp:
            data["flow"] = self.flow
        return build_transport(self.transport, data)


class ConfigCreateIn(ConfigBase):
    uuid: str | None = Field(default=None, max_length=64)

    @field_validator("uuid")
    @classmethod
    def _uuid(cls, v: str | None) -> str | None:
        return validate_uuid(v) if v else None


class ConfigUpdateIn(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=128)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)

    path: str | None = Field(default=None, max_length=512)
    host_header: str | None = Field(default=None, max_length=255)
    sni: str | None = Field(default=None, max_length=255)
    flow: str | None = Field(default=None, max_length=64)

    security: SecurityType | None = None
    tls_server_name: str | None = Field(default=None, max_length=255)
    fingerprint: str | None = Field(default=None, max_length=64)
    alpn: str | None = Field(default=None, max_length=128)
    allow_insecure: bool | None = None

    extra: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    notes: str | None = None
    enabled: bool | None = None
    expires_at: datetime | None = None
    service_id: UUID | None = None


class ConfigOut(ORMModel):
    id: uuid.UUID
    name: str
    uuid: str
    protocol: str
    transport: str
    service_id: UUID | None = None
    host: str
    port: int
    path: str | None = None
    sni: str | None = None
    host_header: str | None = None
    flow: str | None = None
    security: str
    tls_server_name: str | None = None
    fingerprint: str | None = None
    alpn: str | None = None
    allow_insecure: bool
    extra: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    enabled: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ConfigGenerateIn(BaseModel):
    """Request body for the generation endpoint.

    Either `service_id` + `transport` + `protocol` are provided, or a full
    `config` payload.
    """

    service_id: UUID | None = None
    protocol: ProtocolType | None = None
    transport: TransportType | None = None
    config: ConfigCreateIn | None = None
    generate_uuid: bool = True


class ConfigGeneratedOut(BaseModel):
    config: ConfigOut
    share_url: str
    xray: dict[str, Any]
    qr_code: str | None = None


class ConfigListItem(ORMModel):
    id: uuid.UUID
    name: str
    uuid: str
    protocol: str
    transport: str
    host: str
    share_url: str = ""
    enabled: bool
    expires_at: datetime | None = None
    created_at: datetime
    service_id: UUID | None = None


class ConfigDuplicateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
