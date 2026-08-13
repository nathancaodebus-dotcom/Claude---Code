"""Environment configuration for the shopping assistant backend — a
standalone service, deliberately separate from Orion's own core/config.py.
It reuses ANTHROPIC_API_KEY (same model provider, no reason to fragment)
but everything Shopify-related is its own set of variables: this talks to
the Storefront API (public-facing, safe to expose via a proxied backend)
never the Admin API token Orion's tools/shopify_tools.py uses — mixing
those up would expose store-management credentials to every visitor.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def _get_list(key: str) -> list[str]:
    raw = os.environ.get(key, "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str = field(default_factory=lambda: _get("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: _get("SHOPPING_ASSISTANT_MODEL", "claude-sonnet-5"))

    shopify_store_domain: str = field(default_factory=lambda: _get("SHOPIFY_STORE_DOMAIN", ""))
    storefront_access_token: str = field(default_factory=lambda: _get("SHOPIFY_STOREFRONT_ACCESS_TOKEN", ""))
    storefront_api_version: str = field(default_factory=lambda: _get("SHOPIFY_STOREFRONT_API_VERSION", "2024-10"))

    # Comma-separated list of origins allowed to call this backend, e.g.
    # "https://your-store.myshopify.com,https://your-custom-domain.com".
    allowed_origins: list[str] = field(default_factory=lambda: _get_list("SHOPPING_ASSISTANT_ALLOWED_ORIGINS"))

    def validate(self) -> list[str]:
        problems = []
        if not self.anthropic_api_key:
            problems.append("ANTHROPIC_API_KEY is not set.")
        if not self.shopify_store_domain:
            problems.append("SHOPIFY_STORE_DOMAIN is not set.")
        if not self.storefront_access_token:
            problems.append("SHOPIFY_STOREFRONT_ACCESS_TOKEN is not set.")
        if not self.allowed_origins:
            problems.append(
                "SHOPPING_ASSISTANT_ALLOWED_ORIGINS is not set — the widget won't be able to call this "
                "backend from the browser without CORS allowing its origin."
            )
        return problems


config = Config()
