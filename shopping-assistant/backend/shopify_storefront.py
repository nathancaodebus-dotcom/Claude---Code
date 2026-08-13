"""Thin client for Shopify's Storefront GraphQL API — product search,
product detail, and cart operations. Deliberately separate from Orion's
tools/shopify_tools.py, which uses the Admin REST API with a merchant-only
access token: the Storefront API uses a different, public-facing token
type designed to be used from a customer-facing surface, and the two
should never be mixed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass
class Product:
    id: str
    handle: str
    title: str
    description: str
    image_url: str | None
    price: str
    currency: str
    variants: list[dict] = field(default_factory=list)


@dataclass
class CartLine:
    line_id: str
    variant_id: str
    product_title: str
    variant_title: str
    quantity: int


@dataclass
class Cart:
    id: str
    checkout_url: str
    lines: list[CartLine]
    total_amount: str
    currency: str


class ShopifyStorefrontError(RuntimeError):
    pass


_PRODUCT_FIELDS = """
    id
    handle
    title
    description
    featuredImage { url altText }
    priceRange { minVariantPrice { amount currencyCode } }
    variants(first: 25) {
      edges {
        node {
          id
          title
          availableForSale
          price { amount currencyCode }
          selectedOptions { name value }
        }
      }
    }
"""

_CART_FIELDS = """
    id
    checkoutUrl
    cost { totalAmount { amount currencyCode } }
    lines(first: 50) {
      edges {
        node {
          id
          quantity
          merchandise {
            ... on ProductVariant {
              id
              title
              product { title }
            }
          }
        }
      }
    }
"""


def _parse_product(node: dict) -> Product:
    price_info = node["priceRange"]["minVariantPrice"]
    image = node.get("featuredImage") or {}
    variants = [
        {
            "id": edge["node"]["id"],
            "title": edge["node"]["title"],
            "available": edge["node"]["availableForSale"],
            "price": edge["node"]["price"]["amount"],
            "options": {o["name"]: o["value"] for o in edge["node"]["selectedOptions"]},
        }
        for edge in node["variants"]["edges"]
    ]
    return Product(
        id=node["id"],
        handle=node["handle"],
        title=node["title"],
        description=node.get("description", ""),
        image_url=image.get("url"),
        price=price_info["amount"],
        currency=price_info["currencyCode"],
        variants=variants,
    )


def _parse_cart(node: dict) -> Cart:
    lines = [
        CartLine(
            line_id=edge["node"]["id"],
            variant_id=edge["node"]["merchandise"]["id"],
            product_title=edge["node"]["merchandise"]["product"]["title"],
            variant_title=edge["node"]["merchandise"]["title"],
            quantity=edge["node"]["quantity"],
        )
        for edge in node["lines"]["edges"]
    ]
    cost = node["cost"]["totalAmount"]
    return Cart(
        id=node["id"],
        checkout_url=node["checkoutUrl"],
        lines=lines,
        total_amount=cost["amount"],
        currency=cost["currencyCode"],
    )


class ShopifyStorefrontClient:
    def __init__(self, store_domain: str, access_token: str, api_version: str):
        self._url = f"https://{store_domain}/api/{api_version}/graphql.json"
        self._headers = {
            "X-Shopify-Storefront-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    def _execute(self, query: str, variables: dict) -> dict:
        response = httpx.post(
            self._url, headers=self._headers, json={"query": query, "variables": variables}, timeout=15
        )
        response.raise_for_status()
        payload = response.json()
        if "errors" in payload:
            raise ShopifyStorefrontError("; ".join(e.get("message", str(e)) for e in payload["errors"]))
        return payload["data"]

    def search_products(self, query: str, limit: int = 8) -> list[Product]:
        graphql = f"""
        query SearchProducts($query: String!, $first: Int!) {{
          products(query: $query, first: $first) {{
            edges {{ node {{ {_PRODUCT_FIELDS} }} }}
          }}
        }}
        """
        data = self._execute(graphql, {"query": query, "first": limit})
        return [_parse_product(edge["node"]) for edge in data["products"]["edges"]]

    def get_product(self, handle: str) -> Product | None:
        graphql = f"""
        query GetProduct($handle: String!) {{
          productByHandle(handle: $handle) {{ {_PRODUCT_FIELDS} }}
        }}
        """
        data = self._execute(graphql, {"handle": handle})
        node = data.get("productByHandle")
        return _parse_product(node) if node else None

    def create_cart(self, variant_id: str, quantity: int) -> Cart:
        graphql = f"""
        mutation CartCreate($lines: [CartLineInput!]) {{
          cartCreate(input: {{ lines: $lines }}) {{
            cart {{ {_CART_FIELDS} }}
            userErrors {{ field message }}
          }}
        }}
        """
        data = self._execute(graphql, {"lines": [{"merchandiseId": variant_id, "quantity": quantity}]})
        result = data["cartCreate"]
        if result["userErrors"]:
            raise ShopifyStorefrontError("; ".join(e["message"] for e in result["userErrors"]))
        return _parse_cart(result["cart"])

    def add_to_cart(self, cart_id: str, variant_id: str, quantity: int) -> Cart:
        graphql = f"""
        mutation CartLinesAdd($cartId: ID!, $lines: [CartLineInput!]!) {{
          cartLinesAdd(cartId: $cartId, lines: $lines) {{
            cart {{ {_CART_FIELDS} }}
            userErrors {{ field message }}
          }}
        }}
        """
        data = self._execute(
            graphql, {"cartId": cart_id, "lines": [{"merchandiseId": variant_id, "quantity": quantity}]}
        )
        result = data["cartLinesAdd"]
        if result["userErrors"]:
            raise ShopifyStorefrontError("; ".join(e["message"] for e in result["userErrors"]))
        return _parse_cart(result["cart"])

    def get_cart(self, cart_id: str) -> Cart | None:
        graphql = f"""
        query GetCart($cartId: ID!) {{
          cart(id: $cartId) {{ {_CART_FIELDS} }}
        }}
        """
        data = self._execute(graphql, {"cartId": cart_id})
        node = data.get("cart")
        return _parse_cart(node) if node else None
