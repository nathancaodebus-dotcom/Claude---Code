"""Check for leaked credentials via Have I Been Pwned. The password-range
check uses k-anonymity (only the first 5 hash chars are ever sent, so the
actual password never leaves the device) and needs no API key. The
email-breach check needs a paid HIBP API key (their policy since 2024)."""
from __future__ import annotations

import hashlib

import httpx

from core.config import config
from tools.base import Tool


class CheckPasswordLeakedTool(Tool):
    name = "check_password_leaked"
    description = (
        "Check whether a password has appeared in known data breaches, without ever sending the "
        "full password anywhere (k-anonymity: only a partial hash prefix is sent). No API key needed."
    )
    input_schema = {
        "type": "object",
        "properties": {"password": {"type": "string"}},
        "required": ["password"],
    }

    def run(self, password: str) -> str:
        sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]

        response = httpx.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=10)
        response.raise_for_status()

        for line in response.text.splitlines():
            hash_suffix, count = line.split(":")
            if hash_suffix == suffix:
                return f"This password has appeared in {count} known breaches. Change it."
        return "This password was not found in known breaches (doesn't guarantee it's a good password)."


class CheckEmailBreachedTool(Tool):
    name = "check_email_breached"
    description = "Check whether an email address has appeared in known data breaches (requires HIBP_API_KEY)."
    input_schema = {
        "type": "object",
        "properties": {"email": {"type": "string"}},
        "required": ["email"],
    }

    def run(self, email: str) -> str:
        if not config.hibp_api_key:
            return "Email breach checking needs a paid HIBP_API_KEY (haveibeenpwned.com/API/Key)."

        response = httpx.get(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
            headers={"hibp-api-key": config.hibp_api_key, "User-Agent": "JarvisAssistant"},
            timeout=10,
        )
        if response.status_code == 404:
            return f"No known breaches found for {email}."
        response.raise_for_status()

        breaches = response.json()
        return "\n".join(f"- {b['Name']} ({b['BreachDate']})" for b in breaches)
