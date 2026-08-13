"""Run a Shopify store — orders, products/inventory, customers, and
discount codes — via the Shopify Admin REST API. Auth is a per-store
custom app access token (not OAuth): create a custom app in the Shopify
admin (Settings -> Apps and sales channels -> Develop apps), grant it the
scopes this module needs (read/write orders, products, customers,
price_rules), install it, and copy the Admin API access token into
SHOPIFY_ACCESS_TOKEN. See README for the full walkthrough.

Deliberately does not implement refunds or order cancellation — those
move money back out and deserve the same "never do this unsupervised"
treatment as autonomous crypto trade execution (see tools/crypto_tools.py)
and auto-sending email (see tools/gmail_tool.py). Everything here either
reads data or takes a normal, expected, reversible forward action
(fulfilling a paid order, updating a product, restocking inventory,
creating a discount).
"""
from __future__ import annotations

import datetime as dt

import httpx

from core.config import config
from core.http import client
from tools.base import Tool


def _base_url() -> str:
    return f"https://{config.shopify_store_domain}/admin/api/{config.shopify_api_version}"


def _headers() -> dict[str, str]:
    return {"X-Shopify-Access-Token": config.shopify_access_token, "Content-Type": "application/json"}


def _first_variant(product: dict) -> dict | None:
    variants = product.get("variants") or []
    return variants[0] if variants else None


def _first_location_id() -> int:
    response = client.get(f"{_base_url()}/locations.json", headers=_headers(), timeout=15)
    response.raise_for_status()
    locations = response.json().get("locations", [])
    if not locations:
        raise RuntimeError("This Shopify store has no locations configured.")
    return locations[0]["id"]


class ListShopifyOrdersTool(Tool):
    name = "list_shopify_orders"
    description = "List recent Shopify orders, optionally filtered by fulfillment or payment status."
    input_schema = {
        "type": "object",
        "properties": {
            "fulfillment_status": {
                "type": "string",
                "enum": ["unfulfilled", "partial", "fulfilled"],
                "description": "Omit to include all fulfillment statuses.",
            },
            "financial_status": {
                "type": "string",
                "enum": ["pending", "paid", "refunded", "voided"],
                "description": "Omit to include all payment statuses.",
            },
            "limit": {"type": "integer", "description": "Default 20, max 250."},
        },
    }

    def run(self, fulfillment_status: str | None = None, financial_status: str | None = None, limit: int = 20) -> str:
        params: dict[str, object] = {"status": "any", "limit": min(limit, 250)}
        if fulfillment_status:
            params["fulfillment_status"] = fulfillment_status
        if financial_status:
            params["financial_status"] = financial_status

        response = client.get(f"{_base_url()}/orders.json", headers=_headers(), params=params, timeout=20)
        response.raise_for_status()
        orders = response.json().get("orders", [])
        if not orders:
            return "No matching orders."

        lines = []
        for order in orders:
            lines.append(
                f"- #{order['order_number']} (id={order['id']}) | {order.get('name', '')} | "
                f"{order.get('customer', {}).get('email', 'no email')} | "
                f"{order['total_price']} {order['currency']} | "
                f"payment: {order.get('financial_status')} | fulfillment: {order.get('fulfillment_status') or 'unfulfilled'}"
            )
        return "\n".join(lines)


class GetShopifyOrderTool(Tool):
    name = "get_shopify_order"
    description = "Get the full details of a Shopify order by its id (from list_shopify_orders)."
    input_schema = {
        "type": "object",
        "properties": {"order_id": {"type": "integer"}},
        "required": ["order_id"],
    }

    def run(self, order_id: int) -> str:
        response = client.get(f"{_base_url()}/orders/{order_id}.json", headers=_headers(), timeout=15)
        response.raise_for_status()
        order = response.json()["order"]

        items = "\n".join(
            f"  - {li['quantity']}x {li['title']} ({li.get('sku', 'no sku')}) @ {li['price']}"
            for li in order.get("line_items", [])
        )
        address = order.get("shipping_address") or {}
        return (
            f"Order #{order['order_number']} (id={order['id']})\n"
            f"Customer: {order.get('customer', {}).get('email', 'no email')}\n"
            f"Total: {order['total_price']} {order['currency']}\n"
            f"Payment: {order.get('financial_status')} | Fulfillment: {order.get('fulfillment_status') or 'unfulfilled'}\n"
            f"Shipping to: {address.get('address1', '?')}, {address.get('city', '?')}, {address.get('country', '?')}\n"
            f"Items:\n{items}"
        )


class FulfillShopifyOrderTool(Tool):
    name = "fulfill_shopify_order"
    description = "Mark a paid Shopify order as fulfilled (shipped), optionally with tracking info."
    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {"type": "integer"},
            "tracking_number": {"type": "string"},
            "tracking_company": {"type": "string", "description": "e.g. 'La Poste', 'DHL', 'UPS'."},
            "notify_customer": {"type": "boolean", "description": "Default true."},
        },
        "required": ["order_id"],
    }

    def run(
        self,
        order_id: int,
        tracking_number: str | None = None,
        tracking_company: str | None = None,
        notify_customer: bool = True,
    ) -> str:
        fo_response = client.get(
            f"{_base_url()}/orders/{order_id}/fulfillment_orders.json", headers=_headers(), timeout=15
        )
        fo_response.raise_for_status()
        fulfillment_orders = fo_response.json().get("fulfillment_orders", [])
        open_fo = next((fo for fo in fulfillment_orders if fo.get("status") in ("open", "in_progress")), None)
        if open_fo is None:
            return f"Order {order_id} has no open fulfillment orders left to fulfill."

        payload: dict[str, object] = {
            "fulfillment": {
                "line_items_by_fulfillment_order": [{"fulfillment_order_id": open_fo["id"]}],
                "notify_customer": notify_customer,
            }
        }
        if tracking_number:
            payload["fulfillment"]["tracking_info"] = {
                "number": tracking_number,
                "company": tracking_company or "",
            }

        response = client.post(f"{_base_url()}/fulfillments.json", headers=_headers(), json=payload, timeout=20)
        response.raise_for_status()
        return f"Fulfilled order {order_id}" + (f" with tracking {tracking_number}." if tracking_number else ".")


class GetShopifySalesSummaryTool(Tool):
    name = "get_shopify_sales_summary"
    description = "Summarize Shopify sales over the last N days: order count, total revenue, average order value."
    input_schema = {
        "type": "object",
        "properties": {"days": {"type": "integer", "description": "Default 7."}},
    }

    def run(self, days: int = 7) -> str:
        since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
        response = client.get(
            f"{_base_url()}/orders.json",
            headers=_headers(),
            params={"status": "any", "created_at_min": since, "limit": 250},
            timeout=20,
        )
        response.raise_for_status()
        orders = response.json().get("orders", [])
        if not orders:
            return f"No orders in the last {days} day(s)."

        currency = orders[0]["currency"]
        total = sum(float(o["total_price"]) for o in orders)
        return (
            f"Last {days} day(s): {len(orders)} order(s), "
            f"{total:.2f} {currency} total revenue, "
            f"{total / len(orders):.2f} {currency} average order value."
        )


class ListShopifyProductsTool(Tool):
    name = "list_shopify_products"
    description = "List products in the Shopify catalog."
    input_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["active", "draft", "archived"]},
            "limit": {"type": "integer", "description": "Default 20, max 250."},
        },
    }

    def run(self, status: str | None = None, limit: int = 20) -> str:
        params: dict[str, object] = {"limit": min(limit, 250)}
        if status:
            params["status"] = status

        response = client.get(f"{_base_url()}/products.json", headers=_headers(), params=params, timeout=20)
        response.raise_for_status()
        products = response.json().get("products", [])
        if not products:
            return "No matching products."

        lines = []
        for p in products:
            variant = _first_variant(p) or {}
            lines.append(
                f"- {p['title']} (id={p['id']}) | {variant.get('price', '?')} | "
                f"stock: {variant.get('inventory_quantity', '?')} | status: {p['status']}"
            )
        return "\n".join(lines)


class GetShopifyProductTool(Tool):
    name = "get_shopify_product"
    description = "Get the full details of a Shopify product by its id (from list_shopify_products)."
    input_schema = {
        "type": "object",
        "properties": {"product_id": {"type": "integer"}},
        "required": ["product_id"],
    }

    def run(self, product_id: int) -> str:
        response = client.get(f"{_base_url()}/products/{product_id}.json", headers=_headers(), timeout=15)
        response.raise_for_status()
        p = response.json()["product"]

        variants = "\n".join(
            f"  - variant_id={v['id']} | {v.get('title', 'Default')} | {v['price']} | "
            f"sku: {v.get('sku', '?')} | stock: {v.get('inventory_quantity', '?')}"
            for v in p.get("variants", [])
        )
        return (
            f"{p['title']} (id={p['id']}) | status: {p['status']}\n"
            f"Description: {p.get('body_html', '(none)')}\n"
            f"Variants:\n{variants}"
        )


class CreateShopifyProductTool(Tool):
    name = "create_shopify_product"
    description = "Create a new product in the Shopify catalog."
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description_html": {"type": "string", "description": "Product description, as HTML."},
            "price": {"type": "string", "description": "e.g. '29.90'."},
            "sku": {"type": "string"},
            "inventory_quantity": {"type": "integer", "description": "Default 0."},
            "status": {"type": "string", "enum": ["active", "draft"], "description": "Default 'draft'."},
        },
        "required": ["title", "price"],
    }

    def run(
        self,
        title: str,
        price: str,
        description_html: str = "",
        sku: str = "",
        inventory_quantity: int = 0,
        status: str = "draft",
    ) -> str:
        payload = {
            "product": {
                "title": title,
                "body_html": description_html,
                "status": status,
                "variants": [{"price": price, "sku": sku, "inventory_quantity": inventory_quantity}],
            }
        }
        response = client.post(f"{_base_url()}/products.json", headers=_headers(), json=payload, timeout=20)
        response.raise_for_status()
        product = response.json()["product"]
        return f"Created product '{title}' (id={product['id']}, status={status})."


class UpdateShopifyProductTool(Tool):
    name = "update_shopify_product"
    description = "Update a product's title, description, status, and/or price. Omit a field to leave it unchanged."
    input_schema = {
        "type": "object",
        "properties": {
            "product_id": {"type": "integer"},
            "title": {"type": "string"},
            "description_html": {"type": "string"},
            "status": {"type": "string", "enum": ["active", "draft", "archived"]},
            "price": {"type": "string", "description": "Updates the default variant's price."},
        },
        "required": ["product_id"],
    }

    def run(
        self,
        product_id: int,
        title: str | None = None,
        description_html: str | None = None,
        status: str | None = None,
        price: str | None = None,
    ) -> str:
        changed = []
        product_fields: dict[str, object] = {}
        if title is not None:
            product_fields["title"] = title
            changed.append("title")
        if description_html is not None:
            product_fields["body_html"] = description_html
            changed.append("description")
        if status is not None:
            product_fields["status"] = status
            changed.append("status")

        if product_fields:
            response = client.put(
                f"{_base_url()}/products/{product_id}.json",
                headers=_headers(),
                json={"product": {"id": product_id, **product_fields}},
                timeout=20,
            )
            response.raise_for_status()

        if price is not None:
            get_response = client.get(f"{_base_url()}/products/{product_id}.json", headers=_headers(), timeout=15)
            get_response.raise_for_status()
            variant = _first_variant(get_response.json()["product"])
            if variant is None:
                return f"Product {product_id} has no variants to price."
            variant_response = client.put(
                f"{_base_url()}/variants/{variant['id']}.json",
                headers=_headers(),
                json={"variant": {"id": variant["id"], "price": price}},
                timeout=20,
            )
            variant_response.raise_for_status()
            changed.append("price")

        if not changed:
            return "Nothing to update — pass at least one field."
        return f"Updated {', '.join(changed)} for product {product_id}."


class UpdateShopifyInventoryTool(Tool):
    name = "update_shopify_inventory"
    description = "Set the stock quantity for a product (or a specific variant of a multi-variant product)."
    input_schema = {
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "Used to find the variant if variant_id is omitted."},
            "variant_id": {"type": "integer", "description": "Optional — targets a specific variant directly."},
            "quantity": {"type": "integer"},
        },
        "required": ["quantity"],
    }

    def run(self, quantity: int, product_id: int | None = None, variant_id: int | None = None) -> str:
        if variant_id is None:
            if product_id is None:
                return "Pass either product_id or variant_id."
            get_response = client.get(f"{_base_url()}/products/{product_id}.json", headers=_headers(), timeout=15)
            get_response.raise_for_status()
            variant = _first_variant(get_response.json()["product"])
            if variant is None:
                return f"Product {product_id} has no variants."
            variant_id = variant["id"]
            inventory_item_id = variant["inventory_item_id"]
        else:
            variant_response = client.get(f"{_base_url()}/variants/{variant_id}.json", headers=_headers(), timeout=15)
            variant_response.raise_for_status()
            inventory_item_id = variant_response.json()["variant"]["inventory_item_id"]

        location_id = _first_location_id()
        response = client.post(
            f"{_base_url()}/inventory_levels/set.json",
            headers=_headers(),
            json={"location_id": location_id, "inventory_item_id": inventory_item_id, "available": quantity},
            timeout=20,
        )
        response.raise_for_status()
        return f"Set stock to {quantity} for variant {variant_id}."


class SearchShopifyCustomersTool(Tool):
    name = "search_shopify_customers"
    description = "Search Shopify customers by name or email."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    def run(self, query: str) -> str:
        response = client.get(
            f"{_base_url()}/customers/search.json", headers=_headers(), params={"query": query}, timeout=15
        )
        response.raise_for_status()
        customers = response.json().get("customers", [])
        if not customers:
            return f"No customers found matching '{query}'."

        lines = []
        for c in customers:
            lines.append(
                f"- {c.get('first_name', '')} {c.get('last_name', '')} (id={c['id']}) | "
                f"{c.get('email', 'no email')} | {c.get('orders_count', 0)} order(s), "
                f"{c.get('total_spent', '0')} total spent"
            )
        return "\n".join(lines)


class GetShopifyCustomerOrdersTool(Tool):
    name = "get_shopify_customer_orders"
    description = "List a customer's past orders, by their id (from search_shopify_customers)."
    input_schema = {
        "type": "object",
        "properties": {"customer_id": {"type": "integer"}},
        "required": ["customer_id"],
    }

    def run(self, customer_id: int) -> str:
        response = client.get(
            f"{_base_url()}/customers/{customer_id}/orders.json",
            headers=_headers(),
            params={"status": "any"},
            timeout=15,
        )
        response.raise_for_status()
        orders = response.json().get("orders", [])
        if not orders:
            return "This customer has no orders."

        return "\n".join(
            f"- #{o['order_number']} | {o['total_price']} {o['currency']} | "
            f"payment: {o.get('financial_status')} | fulfillment: {o.get('fulfillment_status') or 'unfulfilled'}"
            for o in orders
        )


class CreateShopifyDiscountTool(Tool):
    name = "create_shopify_discount"
    description = "Create a store-wide discount code (percentage or fixed amount off)."
    input_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "The code customers enter, e.g. 'SUMMER10'."},
            "discount_type": {"type": "string", "enum": ["percentage", "fixed_amount"]},
            "value": {"type": "number", "description": "e.g. 10 for 10% off or 10.00 currency units off."},
            "usage_limit": {"type": "integer", "description": "Optional cap on total redemptions."},
            "expires_in_days": {"type": "integer", "description": "Optional; omit for no expiry."},
        },
        "required": ["code", "discount_type", "value"],
    }

    def run(
        self,
        code: str,
        discount_type: str,
        value: float,
        usage_limit: int | None = None,
        expires_in_days: int | None = None,
    ) -> str:
        now = dt.datetime.utcnow()
        price_rule: dict[str, object] = {
            "title": code,
            "target_type": "line_item",
            "target_selection": "all",
            "allocation_method": "across",
            "value_type": discount_type,
            "value": f"-{value}",
            "customer_selection": "all",
            "starts_at": now.isoformat() + "Z",
        }
        if usage_limit is not None:
            price_rule["usage_limit"] = usage_limit
        if expires_in_days is not None:
            price_rule["ends_at"] = (now + dt.timedelta(days=expires_in_days)).isoformat() + "Z"

        rule_response = client.post(
            f"{_base_url()}/price_rules.json", headers=_headers(), json={"price_rule": price_rule}, timeout=20
        )
        rule_response.raise_for_status()
        rule_id = rule_response.json()["price_rule"]["id"]

        code_response = client.post(
            f"{_base_url()}/price_rules/{rule_id}/discount_codes.json",
            headers=_headers(),
            json={"discount_code": {"code": code}},
            timeout=20,
        )
        code_response.raise_for_status()

        value_desc = f"{value}%" if discount_type == "percentage" else f"{value}"
        return f"Created discount code '{code}' ({value_desc} off)."
