"""Lets Jarvis report on the health of the machine it's running on — CPU,
memory, disk, uptime, and (on a Raspberry Pi) core temperature. The closest
thing here to JARVIS reporting suit diagnostics."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import psutil

from core.store import Store
from tools.base import Tool

_PI_THERMAL_PATH = Path("/sys/class/thermal/thermal_zone0/temp")


def _cpu_temperature_c() -> float | None:
    if _PI_THERMAL_PATH.exists():
        return int(_PI_THERMAL_PATH.read_text().strip()) / 1000.0
    return None


class SystemStatusTool(Tool):
    name = "get_system_status"
    description = (
        "Get the health status of the machine Jarvis is running on: CPU usage/temperature, "
        "memory usage, disk usage, and uptime. Useful for checking on the Raspberry Pi it lives on."
    )
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        uptime_s = time.time() - psutil.boot_time()
        temp = _cpu_temperature_c()

        lines = [
            f"CPU: {cpu_percent}%" + (f" @ {temp:.1f}°C" if temp is not None else ""),
            f"Memory: {memory.percent}% used ({memory.used // (1024**2)} MB / {memory.total // (1024**2)} MB)",
            f"Disk: {disk.percent}% used ({disk.used // (1024**3)} GB / {disk.total // (1024**3)} GB)",
            f"Uptime: {uptime_s / 3600:.1f} hours",
        ]
        return "\n".join(lines)


class ListFailedCommandsTool(Tool):
    name = "list_failed_commands"
    description = (
        "List recent tool calls that failed (unknown tools, exceptions, expired API keys...). "
        "Useful for diagnosing what's broken or missing — e.g. after the user reports "
        "something didn't work, or when asked to check for problems."
    )
    input_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "Default 20."}},
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, limit: int = 20) -> str:
        rows = self._store.recent_failed_commands(limit=limit)
        if not rows:
            return "No failed commands logged."
        return "\n".join(
            f"- [{datetime.fromtimestamp(ts):%Y-%m-%d %H:%M}] {tool}: {error}"
            for tool, error, ts in rows
        )
