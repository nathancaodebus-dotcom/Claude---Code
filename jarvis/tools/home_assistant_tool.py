"""Control smart-home devices (lights, switches, thermostats...) via Home Assistant.

Home Assistant is the de-facto self-hosted domotique hub — it runs happily
on the same Raspberry Pi as Jarvis (or on a separate one) and exposes a
simple REST API that already understands whatever brand of light/plug/
sensor you own, so Jarvis never needs brand-specific integrations.
"""
from __future__ import annotations

import httpx

from core.config import config
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
        response = httpx.get(url, headers=_headers(), timeout=10)
        response.raise_for_status()
        states = response.json()

        if domain:
            states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]

        if not states:
            return "No matching devices found."

        lines = [f"- {s['entity_id']}: {s['state']}" for s in states]
        return "\n".join(lines)


class CallServiceTool(Tool):
    name = "control_smart_home_device"
    description = (
        "Control a smart home device by calling a Home Assistant service, e.g. turn "
        "a light on/off, set brightness, adjust a thermostat. Use list_smart_home_devices "
        "first to find the exact entity_id. Common services: light.turn_on, light.turn_off, "
        "switch.turn_on, switch.turn_off, climate.set_temperature."
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

    def run(self, domain: str, service: str, entity_id: str, extra_params: dict | None = None) -> str:
        url = f"{config.home_assistant_url}/api/services/{domain}/{service}"
        payload = {"entity_id": entity_id, **(extra_params or {})}
        response = httpx.post(url, headers=_headers(), json=payload, timeout=10)
        response.raise_for_status()
        return f"Called {domain}.{service} on {entity_id}."
