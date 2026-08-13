"""Lets Orion report on the health of the machine it's running on — CPU,
memory, disk, uptime, and (on a Raspberry Pi) core temperature. The closest
thing here to ORION reporting suit diagnostics."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from core.store import Store
from tools.base import Tool

try:
    import psutil
except ImportError:
    # psutil hard-refuses to install on Android/Termux ("platform android is
    # not supported") — degrade the psutil-dependent tools below to a clear
    # error instead of taking the whole module (and everything imported
    # alongside it in registry_builder.py) down with it.
    psutil = None

_PI_THERMAL_PATH = Path("/sys/class/thermal/thermal_zone0/temp")
_PSUTIL_MISSING_MSG = (
    "psutil is not installed on this system (it refuses to install on Android/Termux) — "
    "this feature isn't available here."
)


def _cpu_temperature_c() -> float | None:
    if _PI_THERMAL_PATH.exists():
        return int(_PI_THERMAL_PATH.read_text().strip()) / 1000.0
    return None


class SystemStatusTool(Tool):
    requires_network = False
    name = "get_system_status"
    description = (
        "Get the health status of the machine Orion is running on: CPU usage/temperature, "
        "memory usage, disk usage, and uptime. Useful for checking on the Raspberry Pi it lives on."
    )
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        if psutil is None:
            return _PSUTIL_MISSING_MSG
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
    requires_network = False
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


class ListProcessesTool(Tool):
    requires_network = False
    name = "list_top_processes"
    description = "List the top processes by CPU or memory usage, for spotting what's slowing the machine down."
    input_schema = {
        "type": "object",
        "properties": {
            "sort_by": {"type": "string", "enum": ["cpu", "memory"], "description": "Default 'cpu'."},
            "max_results": {"type": "integer", "description": "Default 10."},
        },
    }

    def run(self, sort_by: str = "cpu", max_results: int = 10) -> str:
        if psutil is None:
            return _PSUTIL_MISSING_MSG
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
        processes.sort(key=lambda p: p.get(key) or 0, reverse=True)

        lines = [
            f"- [{p['pid']}] {p['name']}: CPU {p.get('cpu_percent', 0):.1f}%, Mem {p.get('memory_percent', 0):.1f}%"
            for p in processes[:max_results]
        ]
        return "\n".join(lines) if lines else "No process data available."


class SetProcessPriorityTool(Tool):
    requires_network = False
    name = "set_process_priority"
    description = "Lower or raise a process's scheduling priority (nice level) by its PID, to free up resources without killing it."
    input_schema = {
        "type": "object",
        "properties": {
            "pid": {"type": "integer"},
            "nice_level": {
                "type": "integer",
                "description": "-20 (highest priority) to 19 (lowest). Positive values (lower priority) don't need elevated permissions.",
            },
        },
        "required": ["pid", "nice_level"],
    }

    def run(self, pid: int, nice_level: int) -> str:
        if psutil is None:
            return _PSUTIL_MISSING_MSG
        try:
            proc = psutil.Process(pid)
            proc.nice(max(-20, min(19, nice_level)))
        except psutil.NoSuchProcess:
            return f"No process with PID {pid}."
        except psutil.AccessDenied:
            return f"Permission denied changing priority of PID {pid} (try a positive nice_level, or run with more privileges)."
        return f"Set PID {pid} ({proc.name()}) to nice level {nice_level}."
