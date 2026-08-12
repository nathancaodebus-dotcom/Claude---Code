"""The shopping assistant's Claude tool-use loop — same shape as Orion's
own core/agent.py (Anthropic Messages API, tool-use loop) but scoped down:
no memory/consolidation, no dozens of tools, just enough to search this
one store's catalog and manage a cart. Session state (conversation history
+ cart id) is passed in by the caller (backend/app.py) rather than owned
here, so this class stays a stateless dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import anthropic

from shopify_storefront import Cart, Product, ShopifyStorefrontClient, ShopifyStorefrontError

MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """You are the shopping assistant for this online store, embedded as a chat widget on \
its website. Help visitors find products, answer questions about them, and add items to their cart.

Rules:
- Only discuss this store and its products. If asked about anything unrelated (general chit-chat is \
fine briefly, but not other topics like coding help, world events, etc.), politely redirect to shopping.
- Never invent products, prices, or availability — always use search_products or get_product_details \
to look up real data before describing an item. If nothing matches, say so plainly rather than guessing.
- When you add something to the cart, confirm what you added and the new cart total.
- Keep replies short and conversational — this is a chat widget, not an email.
- You cannot complete a purchase yourself; when the visitor is ready to buy, tell them to use the \
checkout link view_cart provides."""

_TOOL_SCHEMAS = [
    {
        "name": "search_products",
        "description": "Search the store's product catalog by keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Default 8, max 20."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product_details",
        "description": "Get full details (variants, options, availability) for one product by its handle.",
        "input_schema": {
            "type": "object",
            "properties": {"handle": {"type": "string", "description": "The product's handle, from search_products."}},
            "required": ["handle"],
        },
    },
    {
        "name": "add_to_cart",
        "description": "Add a specific product variant to the visitor's cart.",
        "input_schema": {
            "type": "object",
            "properties": {
                "variant_id": {"type": "string", "description": "A variant id from get_product_details."},
                "quantity": {"type": "integer", "description": "Default 1."},
            },
            "required": ["variant_id"],
        },
    },
    {
        "name": "view_cart",
        "description": "See what's currently in the visitor's cart, the total, and the checkout link.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


@dataclass
class SessionState:
    history: list[dict[str, Any]] = field(default_factory=list)
    cart_id: str | None = None


@dataclass
class AgentReply:
    text: str
    products: list[Product]
    cart: Cart | None


def _product_summary(p: Product) -> str:
    variants = ", ".join(f"{v['id']} ({v['title']}, {v['price']} {p.currency}, available={v['available']})" for v in p.variants)
    return (
        f"{p.title} (handle={p.handle}): {p.description[:200]}\n"
        f"Price from {p.price} {p.currency}. Variants: {variants or 'none'}"
    )


def _cart_summary(cart: Cart) -> str:
    if not cart.lines:
        return f"Cart is empty. Checkout URL: {cart.checkout_url}"
    lines = "\n".join(f"- {l.quantity}x {l.product_title} ({l.variant_title})" for l in cart.lines)
    return f"{lines}\nTotal: {cart.total_amount} {cart.currency}\nCheckout URL: {cart.checkout_url}"


class ShoppingAgent:
    def __init__(self, storefront: ShopifyStorefrontClient, anthropic_api_key: str, model: str):
        self._storefront = storefront
        self._client = anthropic.Anthropic(api_key=anthropic_api_key)
        self._model = model

    def _dispatch_tool(self, name: str, tool_input: dict, session: SessionState, collected: list[Product]) -> str:
        try:
            if name == "search_products":
                limit = min(tool_input.get("limit", 8), 20)
                products = self._storefront.search_products(tool_input["query"], limit)
                collected.extend(products)
                if not products:
                    return "No products matched that search."
                return "\n\n".join(_product_summary(p) for p in products)

            if name == "get_product_details":
                product = self._storefront.get_product(tool_input["handle"])
                if product is None:
                    return f"No product found with handle '{tool_input['handle']}'."
                collected.append(product)
                return _product_summary(product)

            if name == "add_to_cart":
                variant_id = tool_input["variant_id"]
                quantity = tool_input.get("quantity", 1)
                if session.cart_id is None:
                    cart = self._storefront.create_cart(variant_id, quantity)
                else:
                    cart = self._storefront.add_to_cart(session.cart_id, variant_id, quantity)
                session.cart_id = cart.id
                return f"Added to cart.\n{_cart_summary(cart)}"

            if name == "view_cart":
                if session.cart_id is None:
                    return "Cart is empty."
                cart = self._storefront.get_cart(session.cart_id)
                if cart is None:
                    return "Cart is empty."
                return _cart_summary(cart)

            return f"Unknown tool '{name}'."
        except ShopifyStorefrontError as exc:
            return f"Store error: {exc}"

    def respond(self, session: SessionState, user_message: str) -> AgentReply:
        session.history.append({"role": "user", "content": user_message})
        collected_products: list[Product] = []
        final_text = ""

        for _ in range(MAX_TOOL_ITERATIONS):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=_TOOL_SCHEMAS,
                messages=session.history,
            )
            session.history.append({"role": "assistant", "content": response.content})

            text_blocks = [b.text for b in response.content if b.type == "text"]
            final_text = "\n".join(text_blocks).strip()

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = self._dispatch_tool(block.name, block.input, session, collected_products)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            session.history.append({"role": "user", "content": tool_results})

        cart = self._storefront.get_cart(session.cart_id) if session.cart_id else None
        return AgentReply(text=final_text, products=collected_products, cart=cart)
