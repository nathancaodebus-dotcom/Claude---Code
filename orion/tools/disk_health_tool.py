"""Predictive disk health via SMART data (smartmontools' smartctl) — catch
a failing drive before it fails. Requires smartctl installed and usually
root/sudo to read SMART attributes, depending on OS config."""
from __future__ import annotations

import json
import subprocess

from tools.base import Tool


class CheckDiskHealthTool(Tool):
    name = "check_disk_health"
    description = "Check SMART health status of a disk (e.g. '/dev/sda') for early failure warning signs."
    input_schema = {
        "type": "object",
        "properties": {"device": {"type": "string", "description": "e.g. '/dev/sda', '/dev/nvme0n1'."}},
        "required": ["device"],
    }

    def run(self, device: str) -> str:
        try:
            result = subprocess.run(
                ["smartctl", "-a", "-j", device], capture_output=True, text=True, timeout=15
            )
        except FileNotFoundError:
            return "smartctl is not installed. Install smartmontools (e.g. `apt install smartmontools`)."

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return f"Could not read SMART data for '{device}' (needs sudo/root on most systems)."

        health = data.get("smart_status", {}).get("passed")
        temp = data.get("temperature", {}).get("current")
        power_on_hours = data.get("power_on_time", {}).get("hours")

        # smartctl can return valid JSON with no smart_status.passed field
        # at all (SMART data partially unreadable, unsupported by the
        # device/USB bridge, a permission issue) — `health` being None is
        # falsy, so this used to report a hard "FAILED" for a drive whose
        # health is actually *unknown*, not failing. A false alarm is its
        # own kind of harm here (needlessly alarming the user / prompting
        # an unnecessary drive replacement), so unknown is reported as
        # unknown.
        if health is None:
            status = "UNKNOWN — smartctl didn't report a pass/fail status (unsupported device, or needs sudo/root)"
        else:
            status = "PASSED" if health else "FAILED — back this drive up now"
        lines = [f"SMART status: {status}"]
        if temp is not None:
            lines.append(f"Temperature: {temp}°C")
        if power_on_hours is not None:
            lines.append(f"Power-on time: {power_on_hours} hours")
        return "\n".join(lines)
