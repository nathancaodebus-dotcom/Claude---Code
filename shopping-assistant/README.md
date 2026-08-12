# Orion Shopping Assistant

A customer-facing chat widget for a Shopify store: visitors ask about
products in plain language, get real answers grounded in the actual
catalog, and can add items to their cart without leaving the chat.

This is a **separate service from Orion** (the `../orion` personal
assistant elsewhere in this repo) — Orion is a private assistant for the
store *owner*; this is a public widget for the store's *customers*. They
share nothing except reusing the same `ANTHROPIC_API_KEY`, since there's
no reason to run two different model providers for the same kind of
conversational tool-use.

Built as a proportionate alternative to NVIDIA's Retail Shopping
Assistant blueprint: same idea (LLM-driven product search, cart
management, chat), without its LangGraph + Milvus + NVIDIA NIM stack —
this is one FastAPI process and one dependency-free JS widget, sized for
a single small store rather than an enterprise deployment.

## What it does

- Natural-language product search over the real catalog (Shopify
  Storefront API — never invents a product, price, or availability)
- Product detail lookups (variants, options, availability)
- Add-to-cart, from either the chat or a product card's button
- A persistent cart per visitor (Shopify hosts the cart itself; the
  backend just remembers which cart id belongs to which visitor)

## What it deliberately doesn't do (yet)

- **No visual/image search** — text queries only. (The NVIDIA blueprint's
  image search also doesn't actually work in its cloud-only mode as of
  this writing — its `nvclip` hosted endpoint is deprecated.)
- **No streaming replies** — v1 waits for the full response before
  showing it. Straightforward to add later (Anthropic's SDK supports
  streaming the same way `../orion/core/agent.py` already uses it) but
  left out here to ship a working v1 first.
- **In-memory session/cart state** — `backend/app.py` keeps a plain
  Python dict of `session_id -> SessionState`. That means state is lost
  on a backend restart and doesn't work across multiple backend
  instances behind a load balancer. Fine for a single small store on a
  single process; swap it for Redis (or similar) if that stops being
  true — the session store is already isolated behind `_get_session()`
  for exactly that reason.
- **No purchase completion** — the assistant builds a cart and hands the
  visitor a real Shopify checkout URL; it never touches payment.

## Setup

### 1. Shopify Storefront API access

This uses the **Storefront API**, not the Admin API Orion's own
`tools/shopify_tools.py` integration uses — a different, public-facing
token type, safe to route through a customer-facing backend. Don't reuse
the Admin token here.

In your Shopify admin: **Settings → Apps and sales channels → Develop
apps → Create an app → Configure → Storefront API scopes**, grant at
least `unauthenticated_read_product_listings`,
`unauthenticated_read_product_inventory`, `unauthenticated_write_checkouts`,
`unauthenticated_read_checkouts` → **Install app** → reveal the
**Storefront API access token**.

### 2. Backend

```bash
cd shopping-assistant/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in the values
export $(cat ../.env | xargs)  # or use a process manager that loads it
uvicorn app:app --host 0.0.0.0 --port 8000
```

Deploy it anywhere that runs a Python process reachable from the
internet (a small VM, Fly.io, Render, Railway, etc.) — it's a plain
ASGI app, nothing Shopify-specific about the hosting.

### 3. Embed the widget

Host `widget/orion-shop-widget.js` and `widget/orion-shop-widget.css`
somewhere public (same backend host, a CDN, a static bucket — the JS
file loads the CSS file from its own directory automatically). Then add
one script tag to your Shopify theme (**Online Store → Themes → Edit
code → `layout/theme.liquid`**, just before `</body>`):

```html
<script src="https://your-widget-host.example.com/orion-shop-widget.js"
        data-backend-url="https://your-backend.example.com"
        data-store-name="Your Store Name"></script>
```

That's it — a chat bubble appears in the bottom-right corner of every
page.

## Running the tests

```bash
cd shopping-assistant
pip install -r backend/requirements.txt pytest
pytest
```

`conftest.py` puts `backend/` on the path and sets safe fake defaults for
required env vars so the suite runs standalone, without a real `.env` or
live Shopify/Anthropic credentials — every test mocks the Storefront API
and Anthropic calls.
