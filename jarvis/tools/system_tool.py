"""Lets Jarvis report on the health of the machine it's running on — CPU,
memory, disk, uptime, and (on a Raspberry Pi) core temperature. The closest
thing here to JARVIS reporting suit diagnostics."""
from __future__ import annotations

import time
from pathlib import Path

import psutil

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
