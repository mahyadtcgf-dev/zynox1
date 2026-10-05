"""System monitoring — read-only resource metrics.

Uses the `psutil` library. There is deliberately no shell execution anywhere in
this module; only library calls that read kernel counters.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.schemas.service import SystemMetricsOut

logger = get_logger(__name__)

_prev_net: tuple[float, int, int] | None = None


def _try_psutil() -> Any | None:
    try:
        import psutil

        return psutil
    except ImportError:  # pragma: no cover — optional dependency
        logger.error("psutil is not installed; metrics unavailable")
        return None


def sample_metrics() -> SystemMetricsOut:
    """Sample local host metrics."""
    global _prev_net

    psutil = _try_psutil()
    now = time.monotonic()

    if psutil is None:
        return SystemMetricsOut(
            cpu_percent=0.0,
            memory_percent=0.0,
            memory_total_bytes=0,
            memory_used_bytes=0,
            disk_percent=0.0,
            disk_total_bytes=0,
            disk_used_bytes=0,
            network_rx_bps=0,
            network_tx_bps=0,
            uptime_seconds=0,
            timestamp=datetime.now(UTC),
            extra={"available": False},
        )

    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    counters = psutil.net_io_counters()

    rx_bps = 0
    tx_bps = 0
    if _prev_net is not None:
        prev_time, prev_rx, prev_tx = _prev_net
        elapsed = max(now - prev_time, 1e-6)
        rx_bps = int(max(0, counters.bytes_recv - prev_rx) / elapsed)
        tx_bps = int(max(0, counters.bytes_sent - prev_tx) / elapsed)
    _prev_net = (now, counters.bytes_recv, counters.bytes_sent)

    load: list[float] | None = None
    try:
        raw = psutil.getloadavg()
        load = [float(v) for v in raw]
    except AttributeError:
        load = None

    boot = psutil.boot_time()

    return SystemMetricsOut(
        cpu_percent=round(float(psutil.cpu_percent(interval=None)), 2),
        memory_percent=round(float(memory.percent), 2),
        memory_total_bytes=int(memory.total),
        memory_used_bytes=int(memory.used),
        disk_percent=round(float(disk.percent), 2),
        disk_total_bytes=int(disk.total),
        disk_used_bytes=int(disk.used),
        network_rx_bps=rx_bps,
        network_tx_bps=tx_bps,
        uptime_seconds=int(time.time() - boot),
        load_average=load,
        timestamp=datetime.now(UTC),
    )


def to_summary(metrics: SystemMetricsOut) -> dict[str, Any]:
    return {
        "cpu_percent": metrics.cpu_percent,
        "memory_percent": metrics.memory_percent,
        "disk_percent": metrics.disk_percent,
        "network_rx_bps": metrics.network_rx_bps,
        "network_tx_bps": metrics.network_tx_bps,
        "uptime_seconds": metrics.uptime_seconds,
    }
