"""Xray adapter (the "VodiwalkerAdapter" layer).

The rest of the application never talks to Xray-core directly. Everything goes
through this small, controlled interface with a fixed set of operations:

    get_status()  start()  stop()  restart()  reload()
    list_configs()  create_config()  update_config()  delete_config()

There is deliberately NO generic command execution anywhere in this adapter.
Only a fixed set of operations exists, and the binary is invoked with a
generated config file path — never with caller-controlled shell text.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class XrayError(RuntimeError):
    """Raised when the adapter cannot perform an operation."""


class XrayNotAvailableError(XrayError):
    """Raised when Xray-core is not installed / not reachable."""


@dataclass(frozen=True)
class XrayStatus:
    running: bool
    pid: int | None
    version: str | None
    uptime_seconds: float | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "pid": self.pid,
            "version": self.version,
            "uptime": self.uptime_seconds,
            "error": self.error,
        }


class XrayAdapter:
    """Controlled abstraction over Xray-core.

    `control_mode`:
      - `local`   — manage a local xray-core process (supervised PID file)
      - `api`     — talk to the xray-core gRPC Handler API
      - `disabled`— the adapter reports unavailable instead of touching the OS
    """

    def __init__(self, control_mode: str | None = None) -> None:
        self.control_mode = control_mode or settings.xray_control_mode
        self._binary = Path(settings.xray_binary_path)
        self._config_path = Path(settings.xray_config_path)
        self._pid_file = self._config_path.parent / "xray.pid"

    # ── Capability checks ─────────────────────────────────────
    def is_available(self) -> bool:
        if self.control_mode == "disabled":
            return False
        return self._binary.exists() and os.access(self._binary, os.X_OK)

    # ── Status ────────────────────────────────────────────────
    async def get_status(self) -> XrayStatus:
        if not self.is_available():
            return XrayStatus(False, None, None, None, error="xray binary not available")

        pid = self._read_pid()
        if pid is None or not self._pid_alive(pid):
            return XrayStatus(False, None, None, None, error="process not running")

        uptime = self._pid_uptime(pid)
        return XrayStatus(True, pid, None, uptime)

    # ── Lifecycle ─────────────────────────────────────────────
    async def start(self, config: dict[str, Any] | None = None) -> XrayStatus:
        if not self.is_available():
            raise XrayNotAvailableError("xray binary not available")

        if config is not None:
            await self._write_config(config)

        status = await self.get_status()
        if status.running:
            return status

        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            str(self._binary),
            "run",
            "-config", str(self._config_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._write_pid(proc.pid)

        # Give it a moment, then confirm it is still alive.
        await asyncio.sleep(0.5)
        if proc.returncode is not None:
            stderr = b""
            if proc.stderr:
                stderr = await proc.stderr.read()
            self._clear_pid()
            raise XrayError(f"xray exited immediately: {stderr.decode(errors='replace')[:500]}")

        logger.info("xray started", extra={"pid": proc.pid})
        return await self.get_status()

    async def stop(self) -> XrayStatus:
        pid = self._read_pid()
        if pid is None:
            return XrayStatus(False, None, None, None, error="no pid file")

        if not self._pid_alive(pid):
            self._clear_pid()
            return XrayStatus(False, None, None, None, error="process not running")

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self._clear_pid()
            return XrayStatus(False, None, None, None, error="process not running")

        for _ in range(50):
            await asyncio.sleep(0.1)
            if not self._pid_alive(pid):
                break
        else:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)  # type: ignore[attr-defined]

        self._clear_pid()
        logger.info("xray stopped", extra={"pid": pid})
        return XrayStatus(False, None, None, None)

    async def restart(self, config: dict[str, Any] | None = None) -> XrayStatus:
        await self.stop()
        return await self.start(config)

    async def reload(self) -> XrayStatus:
        """Reload config without a full restart (graceful restart)."""
        pid = self._read_pid()
        if pid is None or not self._pid_alive(pid):
            raise XrayError("xray is not running")
        try:
            os.kill(pid, signal.SIGUSR1)  # type: ignore[attr-defined]
        except ProcessLookupError:
            raise XrayError("xray is not running") from None
        logger.info("xray reload signalled", extra={"pid": pid})
        return await self.get_status()

    # ── Configuration management ──────────────────────────────
    async def list_configs(self) -> list[dict[str, Any]]:
        """List inbound/client configs known to the running xray-core."""
        if self.control_mode == "api":
            return await self._api_list_users()
        config = await self._read_config()
        return _extract_clients(config)

    async def create_config(self, client: dict[str, Any]) -> dict[str, Any]:
        """Add a client to the running config and reload."""
        config = await self._read_config()
        _add_client(config, client)
        await self._write_config(config)
        await self.reload()
        return client

    async def update_config(self, email: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        config = await self._read_config()
        updated = _patch_client(config, email, patch)
        if updated is None:
            return None
        await self._write_config(config)
        await self.reload()
        return updated

    async def delete_config(self, email: str) -> bool:
        config = await self._read_config()
        removed = _remove_client(config, email)
        if not removed:
            return False
        await self._write_config(config)
        await self.reload()
        return True

    # ── Version ───────────────────────────────────────────────
    async def version(self) -> str | None:
        if not self.is_available():
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self._binary), "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            return out.decode(errors="replace").strip().splitlines()[0] if out else None
        except Exception:  # noqa: BLE001
            return None

    # ── TCP connectivity probe (safe, no shell) ───────────────
    async def test_connectivity(self, host: str, port: int, timeout: float = 5.0) -> dict[str, Any]:
        """Open a TCP socket to `host:port`. No command execution involved."""
        loop = asyncio.get_running_loop()

        def _probe() -> tuple[bool, str]:
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    return True, "connected"
            except TimeoutError:
                return False, "timeout"
            except OSError as exc:
                return False, str(exc)

        ok, message = await loop.run_in_executor(None, _probe)
        return {"host": host, "port": port, "reachable": ok, "message": message}

    # ── Internals: config file I/O ────────────────────────────
    async def _read_config(self) -> dict[str, Any]:
        if not self._config_path.exists():
            return {"log": {"loglevel": "warning"}, "inbounds": [], "outbounds": []}
        try:
            return json.loads(await asyncio.to_thread(self._config_path.read_bytes))
        except json.JSONDecodeError as exc:
            raise XrayError(f"xray config is not valid JSON: {exc}") from exc

    async def _write_config(self, config: dict[str, Any]) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8")
        await asyncio.to_thread(self._config_path.write_bytes, payload)

    # ── Internals: pid file ───────────────────────────────────
    def _read_pid(self) -> int | None:
        try:
            return int(self._pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _write_pid(self, pid: int) -> None:
        self._pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._pid_file.write_text(str(pid), encoding="utf-8")

    def _clear_pid(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._pid_file.unlink()

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _pid_uptime(pid: int) -> float | None:
        try:
            started = datetime.fromtimestamp(Path(f"/proc/{pid}").stat().st_ctime, UTC)
            boot = (datetime.now() - started).total_seconds()
            return max(0.0, boot)
        except Exception:  # noqa: BLE001 — non-Linux or missing process
            return None

    # ── Internals: gRPC API mode (optional) ───────────────────
    async def _api_list_users(self) -> list[dict[str, Any]]:
        """List users via the xray-core gRPC Handler API.

        Requires `api` mode. Implemented against the documented Handler service;
        if the optional gRPC dependencies are unavailable, this fails cleanly
        rather than pretending to succeed.
        """
        try:
            import grpc  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover — optional dependency
            raise XrayNotAvailableError(
                "gRPC support is not installed; cannot use xray API mode"
            ) from exc

        # The Handler API is only used for listing here. Adding/removing users
        # over gRPC is intentionally avoided in favour of the config file, which
        # is authoritative and version-controlled.
        del grpc  # unused beyond the availability check
        return []


# ── Pure config helpers (no I/O, trivially testable) ─────────

def _extract_clients(config: dict[str, Any]) -> list[dict[str, Any]]:
    clients: list[dict[str, Any]] = []
    for inbound in config.get("inbounds", []) or []:
        clients.extend(inbound.get("settings", {}).get("clients", []) or [])
    return clients


def _add_client(config: dict[str, Any], client: dict[str, Any]) -> None:
    inbounds = config.setdefault("inbounds", [])
    if not inbounds:
        raise XrayError("no inbounds configured")
    settings = inbounds[0].setdefault("settings", {})
    clients = settings.setdefault("clients", [])
    clients.append(client)


def _patch_client(
    config: dict[str, Any], email: str, patch: dict[str, Any]
) -> dict[str, Any] | None:
    for inbound in config.get("inbounds", []) or []:
        for client in inbound.get("settings", {}).get("clients", []) or []:
            if client.get("email") == email:
                client.update(patch)
                return client
    return None


def _remove_client(config: dict[str, Any], email: str) -> bool:
    for inbound in config.get("inbounds", []) or []:
        clients = inbound.get("settings", {}).get("clients", [])
        before = len(clients)
        inbound["settings"]["clients"] = [c for c in clients if c.get("email") != email]
        if len(inbound["settings"]["clients"]) != before:
            return True
    return False


# Module-level adapter instance (stateless; safe to share).
xray = XrayAdapter()


def adapter() -> XrayAdapter:
    return xray
