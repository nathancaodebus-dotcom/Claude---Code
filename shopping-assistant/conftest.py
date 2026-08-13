import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

# config.py's module-level `config = Config()` singleton reads these at
# import time, and several test modules import `app` (which imports
# `config`) — set defaults here, before any test module is collected, so
# tests don't depend on a real .env existing. setdefault so a real .env
# loaded some other way still wins.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("SHOPIFY_STORE_DOMAIN", "test-store.myshopify.com")
os.environ.setdefault("SHOPIFY_STOREFRONT_ACCESS_TOKEN", "test-token")
os.environ.setdefault("SHOPPING_ASSISTANT_ALLOWED_ORIGINS", "https://test-store.myshopify.com")
