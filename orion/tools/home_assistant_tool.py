"""Control smart-home devices (lights, switches, thermostats...) via Home Assistant.

Home Assistant is the de-facto self-hosted domotique hub — it runs happily
on the same Raspberry Pi as Orion (or on a separate one) and exposes a
simple REST API that already understands whatever brand of light/plug/
sensor you own, so Orion never needs brand-specific integrations.
"""
from __future__ import annotations

import httpx

from core.config import config
from core.http import client
from tools.base import Tool


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.home_assistant_token}",
        "Content-Type": "application/json",
    }


class ListDevicesTool(Tool):
    name = "list_smart_home_devices"
    description = (
        "List smart home devices (lights, switches, sensors, thermostats...) known to "
        "Home Assistant, with their current state. Optionally filter by domain "
        "(e.g. 'light', 'switch', 'climate')."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Restrict results to one domain, e.g. 'light' or 'switch'. Omit for everything.",
            }
        },
    }

    def run(self, domain: str | None = None) -> str:
        url = f"{config.home_assistant_url}/api/states"
        response = client.get(url, headers=_headers(), timeout=10)
        response.raise_for_status()
        states = response.json()

        if domain:
            states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]

        if not states:
            return "No matching devices found."

        lines = [f"- {s['entity_id']}: {s['state']}" for s in states]
        return "\n".join(lines)


# Home Assistant domains that control physical access/security -- unlike
# most services here (lights, switches, thermostats), calling one of these
# has a real-world consequence that's hard to walk back quickly (a door
# left unlocked, a disarmed alarm, an open garage). Found during a full-
# codebase audit: this tool was a raw passthrough to *any* domain.service
# with no allowlist and no confirmation step, so a misheard voice command
# or a jailbroken request could unlock a door or disarm an alarm in one
# shot. Everything else still executes immediately, same as before.
_DANGEROUS_DOMAINS = frozenset({"lock", "alarm_control_panel", "cover"})


class CallServiceTool(Tool):
    name = "control_smart_home_device"
    description = (
        "Control a smart home device by calling a Home Assistant service, e.g. turn "
        "a light on/off, set brightness, adjust a thermostat. Use list_smart_home_devices "
        "first to find the exact entity_id. Common services: light.turn_on, light.turn_off, "
        "switch.turn_on, switch.turn_off, climate.set_temperature. "
        "Locks, alarms, and covers (garage doors) don't execute immediately -- this returns a "
        "pending action id instead; only call confirm_smart_home_action if the user has "
        "explicitly agreed to that specific action, never on your own initiative."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "Service domain, e.g. 'light', 'switch', 'climate'."},
            "service": {"type": "string", "description": "Service name, e.g. 'turn_on', 'turn_off', 'set_temperature'."},
            "entity_id": {"type": "string", "description": "Target entity id, e.g. 'light.living_room'."},
            "extra_params": {
                "type": "object",
                "description": "Extra service parameters, e.g. {'brightness_pct': 50} or {'temperature': 21}.",
            },
        },
        "required": ["domain", "service", "entity_id"],
    }

    def __init__(self) -> None:
        self._pending: dict[int, tuple[str, str, str, dict]] = {}
        self._next_id = 1

    def run(self, domain: str, service: str, entity_id: str, extra_params: dict | None = None) -> str:
        if domain in _DANGEROUS_DOMAINS:
            action_id = self._next_id
            self._next_id += 1
            self._pending[action_id] = (domain, service, entity_id, extra_params or {})
            return (
                f"Proposal #{action_id}: {domain}.{service} on {entity_id} — PENDING, not yet applied. "
                "This controls a lock, alarm, or cover, so it needs explicit confirmation first. Ask the "
                "user to confirm, then call confirm_smart_home_action(action_id) — never call it "
                "speculatively or because it seems like what the user probably wants."
            )
        return self._execute(domain, service, entity_id, extra_params or {})

    def _execute(self, domain: str, service: str, entity_id: str, extra_params: dict) -> str:
        url = f"{config.home_assistant_url}/api/services/{domain}/{service}"
        payload = {"entity_id": entity_id, **extra_params}
        response = client.post(url, headers=_headers(), json=payload, timeout=10)
        response.raise_for_status()
        return f"Called {domain}.{service} on {entity_id}."


class ConfirmSmartHomeActionTool(Tool):
    name = "confirm_smart_home_action"
    description = (
        "Execute a pending lock/alarm/cover action proposed by control_smart_home_device. Only "
        "call this after the user has explicitly agreed to that specific action_id."
    )
    input_schema = {
        "type": "object",
        "properties": {"action_id": {"type": "integer"}},
        "required": ["action_id"],
    }

    def __init__(self, call_service_tool: CallServiceTool) -> None:
        self._call_service_tool = call_service_tool

    def run(self, action_id: int) -> str:
        pending = self._call_service_tool._pending.pop(action_id, None)
        if pending is None:
            return f"No pending action #{action_id} — it may already be confirmed, or never existed."
        domain, service, entity_id, extra_params = pending
        return self._call_service_tool._execute(domain, service, entity_id, extra_params)
