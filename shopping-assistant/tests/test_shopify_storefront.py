import pytest

from shopify_storefront import ShopifyStorefrontClient, ShopifyStorefrontError


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def client():
    return ShopifyStorefrontClient("test-store.myshopify.com", "fake-token", "2024-10")


def _product_node(handle="tee", title="T-Shirt"):
    return {
        "id": "gid://shopify/Product/1",
        "handle": handle,
        "title": title,
        "description": "A comfortable shirt.",
        "featuredImage": {"url": "https://example.com/tee.png", "altText": "tee"},
        "priceRange": {"minVariantPrice": {"amount": "20.00", "currencyCode": "CHF"}},
        "variants": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/ProductVariant/1",
                        "title": "Small",
                        "availableForSale": True,
                        "price": {"amount": "20.00", "currencyCode": "CHF"},
                        "selectedOptions": [{"name": "Size", "value": "Small"}],
                    }
                }
            ]
        },
    }


def _cart_node(cart_id="gid://shopify/Cart/1"):
    return {
        "id": cart_id,
        "checkoutUrl": "https://test-store.myshopify.com/cart/c/1",
        "cost": {"totalAmount": {"amount": "20.00", "currencyCode": "CHF"}},
        "lines": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/CartLine/1",
                        "quantity": 1,
                        "merchandise": {
                            "id": "gid://shopify/ProductVariant/1",
                            "title": "Small",
                            "product": {"title": "T-Shirt"},
                        },
                    }
                }
            ]
        },
    }


def test_search_products_parses_results(monkeypatch, client):
    monkeypatch.setattr(
        "shopify_storefront.httpx.post",
        lambda *a, **kw: _FakeResponse({"data": {"products": {"edges": [{"node": _product_node()}]}}}),
    )

    products = client.search_products("shirt")

    assert len(products) == 1
    assert products[0].title == "T-Shirt"
    assert products[0].price == "20.00"
    assert products[0].variants[0]["available"] is True


def test_search_products_sends_query_and_limit(monkeypatch, client):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["variables"] = json["variables"]
        return _FakeResponse({"data": {"products": {"edges": []}}})

    monkeypatch.setattr("shopify_storefront.httpx.post", fake_post)
    client.search_products("shoes", limit=5)

    assert captured["variables"] == {"query": "shoes", "first": 5}


def test_get_product_found(monkeypatch, client):
    monkeypatch.setattr(
        "shopify_storefront.httpx.post",
        lambda *a, **kw: _FakeResponse({"data": {"productByHandle": _product_node()}}),
    )
    product = client.get_product("tee")
    assert product is not None
    assert product.handle == "tee"


def test_get_product_not_found(monkeypatch, client):
    monkeypatch.setattr(
        "shopify_storefront.httpx.post", lambda *a, **kw: _FakeResponse({"data": {"productByHandle": None}})
    )
    assert client.get_product("ghost") is None


def test_graphql_errors_raise(monkeypatch, client):
    monkeypatch.setattr(
        "shopify_storefront.httpx.post",
        lambda *a, **kw: _FakeResponse({"errors": [{"message": "Invalid token"}]}),
    )
    with pytest.raises(ShopifyStorefrontError, match="Invalid token"):
        client.search_products("shirt")


def test_create_cart_success(monkeypatch, client):
    monkeypatch.setattr(
        "shopify_storefront.httpx.post",
        lambda *a, **kw: _FakeResponse({"data": {"cartCreate": {"cart": _cart_node(), "userErrors": []}}}),
    )
    cart = client.create_cart("gid://shopify/ProductVariant/1", 1)
    assert cart.id == "gid://shopify/Cart/1"
    assert cart.total_amount == "20.00"
    assert len(cart.lines) == 1
    assert cart.lines[0].product_title == "T-Shirt"


def test_create_cart_user_errors_raise(monkeypatch, client):
    monkeypatch.setattr(
        "shopify_storefront.httpx.post",
        lambda *a, **kw: _FakeResponse(
            {"data": {"cartCreate": {"cart": None, "userErrors": [{"field": "quantity", "message": "Out of stock"}]}}}
        ),
    )
    with pytest.raises(ShopifyStorefrontError, match="Out of stock"):
        client.create_cart("gid://shopify/ProductVariant/1", 100)


def test_add_to_cart_success(monkeypatch, client):
    monkeypatch.setattr(
        "shopify_storefront.httpx.post",
        lambda *a, **kw: _FakeResponse({"data": {"cartLinesAdd": {"cart": _cart_node(), "userErrors": []}}}),
    )
    cart = client.add_to_cart("gid://shopify/Cart/1", "gid://shopify/ProductVariant/1", 2)
    assert cart.id == "gid://shopify/Cart/1"


def test_get_cart_success(monkeypatch, client):
    monkeypatch.setattr(
        "shopify_storefront.httpx.post", lambda *a, **kw: _FakeResponse({"data": {"cart": _cart_node()}})
    )
    cart = client.get_cart("gid://shopify/Cart/1")
    assert cart is not None
    assert cart.checkout_url.endswith("/cart/c/1")


def test_get_cart_missing_returns_none(monkeypatch, client):
    monkeypatch.setattr("shopify_storefront.httpx.post", lambda *a, **kw: _FakeResponse({"data": {"cart": None}}))
    assert client.get_cart("gid://shopify/Cart/999") is None
