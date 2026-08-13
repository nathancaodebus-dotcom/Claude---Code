import pytest

from core.config import config
from tools import shopify_tools


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200, links=None):
        self._json_data = json_data or {}
        self.status_code = status_code
        self.links = links or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def shopify_config():
    object.__setattr__(config, "shopify_store_domain", "test-store.myshopify.com")
    object.__setattr__(config, "shopify_access_token", "fake-token")
    yield
    object.__setattr__(config, "shopify_store_domain", None)
    object.__setattr__(config, "shopify_access_token", None)


def test_base_url_uses_configured_store_and_version():
    assert shopify_tools._base_url() == "https://test-store.myshopify.com/admin/api/2024-10"


def test_headers_include_access_token():
    assert shopify_tools._headers()["X-Shopify-Access-Token"] == "fake-token"


def test_list_orders_no_matches(monkeypatch):
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse({"orders": []}))
    result = shopify_tools.ListShopifyOrdersTool().run()
    assert result == "No matching orders."


def test_list_orders_formats_results(monkeypatch):
    orders = {
        "orders": [
            {
                "id": 1,
                "order_number": 1001,
                "name": "#1001",
                "customer": {"email": "a@b.com"},
                "total_price": "49.90",
                "currency": "CHF",
                "financial_status": "paid",
                "fulfillment_status": None,
            }
        ]
    }
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse(orders))

    result = shopify_tools.ListShopifyOrdersTool().run()

    assert "#1001" in result
    assert "a@b.com" in result
    assert "unfulfilled" in result


def test_list_orders_passes_filters(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse({"orders": []})

    monkeypatch.setattr(shopify_tools.client, "get", fake_get)
    shopify_tools.ListShopifyOrdersTool().run(fulfillment_status="unfulfilled", financial_status="paid", limit=5)

    assert captured["params"]["fulfillment_status"] == "unfulfilled"
    assert captured["params"]["financial_status"] == "paid"
    assert captured["params"]["limit"] == 5


def test_get_order_formats_details(monkeypatch):
    order = {
        "order": {
            "order_number": 1001,
            "id": 1,
            "customer": {"email": "a@b.com"},
            "total_price": "49.90",
            "currency": "CHF",
            "financial_status": "paid",
            "fulfillment_status": None,
            "shipping_address": {"address1": "Rue de la Gare 1", "city": "Lausanne", "country": "Switzerland"},
            "line_items": [{"quantity": 2, "title": "T-Shirt", "sku": "TS-1", "price": "20.00"}],
        }
    }
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse(order))

    result = shopify_tools.GetShopifyOrderTool().run(order_id=1)

    assert "Order #1001" in result
    assert "T-Shirt" in result
    assert "Lausanne" in result


def test_fulfill_order_no_open_fulfillment_orders(monkeypatch):
    monkeypatch.setattr(
        shopify_tools.client, "get", lambda *a, **kw: _FakeResponse({"fulfillment_orders": []})
    )
    result = shopify_tools.FulfillShopifyOrderTool().run(order_id=1)
    assert "no open fulfillment orders" in result


def test_fulfill_order_success_with_tracking(monkeypatch):
    monkeypatch.setattr(
        shopify_tools.client,
        "get",
        lambda *a, **kw: _FakeResponse({"fulfillment_orders": [{"id": 55, "status": "open"}]}),
    )
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({"fulfillment": {"id": 99}})

    monkeypatch.setattr(shopify_tools.client, "post", fake_post)

    result = shopify_tools.FulfillShopifyOrderTool().run(
        order_id=1, tracking_number="ABC123", tracking_company="La Poste"
    )

    assert "Fulfilled order 1" in result
    assert "ABC123" in result
    fo_ref = captured["json"]["fulfillment"]["line_items_by_fulfillment_order"][0]
    assert fo_ref["fulfillment_order_id"] == 55
    assert captured["json"]["fulfillment"]["tracking_info"]["number"] == "ABC123"


def test_fulfill_order_with_multiple_open_fulfillment_orders_notes_the_rest_are_still_open(monkeypatch):
    """Regression test: an order split across locations/vendors can have
    more than one open fulfillment order. Fulfilling only the first one
    used to be reported as a plain 'Fulfilled order {id}' with no mention
    that other line items remain unfulfilled — Shopify's own
    fulfillment_status for the order would actually be 'partial'."""
    monkeypatch.setattr(
        shopify_tools.client,
        "get",
        lambda *a, **kw: _FakeResponse(
            {"fulfillment_orders": [{"id": 55, "status": "open"}, {"id": 56, "status": "open"}]}
        ),
    )
    monkeypatch.setattr(shopify_tools.client, "post", lambda *a, **kw: _FakeResponse({"fulfillment": {"id": 99}}))

    result = shopify_tools.FulfillShopifyOrderTool().run(order_id=1)

    assert "Fulfilled order 1" in result
    assert "1 more fulfillment order" in result
    assert "still open" in result


def test_sales_summary_no_orders(monkeypatch):
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse({"orders": []}))
    result = shopify_tools.GetShopifySalesSummaryTool().run(days=7)
    assert "No orders" in result


def test_sales_summary_computes_totals(monkeypatch):
    orders = {
        "orders": [
            {"total_price": "50.00", "currency": "CHF"},
            {"total_price": "30.00", "currency": "CHF"},
        ]
    }
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse(orders))

    result = shopify_tools.GetShopifySalesSummaryTool().run(days=7)

    assert "2 order(s)" in result
    assert "80.00 CHF" in result
    assert "40.00 CHF" in result


def test_sales_summary_follows_pagination_instead_of_truncating_at_one_page(monkeypatch):
    """Regression test: the sales summary used to fetch a single page
    (limit=250, no pagination) and silently report totals as if that were
    the whole window — any store with more orders than that in the period
    got a confidently-wrong, quietly incomplete number."""
    pages = [
        _FakeResponse(
            {"orders": [{"total_price": "10.00", "currency": "CHF"}]},
            links={"next": {"url": "https://test-store.myshopify.com/admin/api/2024-10/orders.json?page_info=abc"}},
        ),
        _FakeResponse({"orders": [{"total_price": "20.00", "currency": "CHF"}]}),  # no 'next' link — last page
    ]
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr(shopify_tools.client, "get", fake_get)

    result = shopify_tools.GetShopifySalesSummaryTool().run(days=7)

    assert len(calls) == 2
    assert "2 order(s)" in result
    assert "30.00 CHF" in result


def test_sales_summary_splits_totals_by_currency_instead_of_mixing_them(monkeypatch):
    """A store that's ever changed presentment currency (or takes
    multi-currency checkout) can have orders in different currencies in the
    same window — summing raw total_price across them as one number used
    to silently misreport the total."""
    orders = {
        "orders": [
            {"total_price": "50.00", "currency": "CHF"},
            {"total_price": "30.00", "currency": "USD"},
        ]
    }
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse(orders))

    result = shopify_tools.GetShopifySalesSummaryTool().run(days=7)

    assert "50.00 CHF" in result
    assert "30.00 USD" in result
    assert "80.00" not in result  # never summed across currencies


def test_list_products_formats_results(monkeypatch):
    products = {
        "products": [
            {
                "id": 1,
                "title": "T-Shirt",
                "status": "active",
                "variants": [{"price": "20.00", "inventory_quantity": 15}],
            }
        ]
    }
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse(products))

    result = shopify_tools.ListShopifyProductsTool().run()

    assert "T-Shirt" in result
    assert "20.00" in result
    assert "15" in result


def test_create_product_success(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({"product": {"id": 42}})

    monkeypatch.setattr(shopify_tools.client, "post", fake_post)

    result = shopify_tools.CreateShopifyProductTool().run(title="New Item", price="19.99", sku="NI-1")

    assert "Created product 'New Item'" in result
    assert "id=42" in result
    assert captured["json"]["product"]["variants"][0]["price"] == "19.99"


def test_update_product_title_and_status(monkeypatch):
    captured = {}

    def fake_put(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({"product": {"id": 1}})

    monkeypatch.setattr(shopify_tools.client, "put", fake_put)

    result = shopify_tools.UpdateShopifyProductTool().run(product_id=1, title="New Title", status="active")

    assert "title" in result
    assert "status" in result
    assert captured["json"]["product"]["title"] == "New Title"


def test_update_product_price_fetches_variant_first(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse({"product": {"variants": [{"id": 77, "price": "10.00"}]}})

    captured = {}

    def fake_put(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse({"variant": {"id": 77}})

    monkeypatch.setattr(shopify_tools.client, "get", fake_get)
    monkeypatch.setattr(shopify_tools.client, "put", fake_put)

    result = shopify_tools.UpdateShopifyProductTool().run(product_id=1, price="25.00")

    assert "price" in result
    assert "variants/77.json" in captured["url"]
    assert captured["json"]["variant"]["price"] == "25.00"


def test_update_product_nothing_to_update():
    result = shopify_tools.UpdateShopifyProductTool().run(product_id=1)
    assert "Nothing to update" in result


def test_update_inventory_by_product_id(monkeypatch):
    def fake_get(url, headers=None, timeout=None, params=None):
        if "locations" in url:
            return _FakeResponse({"locations": [{"id": 555}]})
        return _FakeResponse({"product": {"variants": [{"id": 77, "inventory_item_id": 888}]}})

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({})

    monkeypatch.setattr(shopify_tools.client, "get", fake_get)
    monkeypatch.setattr(shopify_tools.client, "post", fake_post)

    result = shopify_tools.UpdateShopifyInventoryTool().run(product_id=1, quantity=42)

    assert "Set stock to 42" in result
    assert captured["json"]["available"] == 42
    assert captured["json"]["location_id"] == 555
    assert captured["json"]["inventory_item_id"] == 888


def test_update_inventory_requires_product_or_variant_id():
    result = shopify_tools.UpdateShopifyInventoryTool().run(quantity=5)
    assert "Pass either" in result


def test_search_customers_no_matches(monkeypatch):
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse({"customers": []}))
    result = shopify_tools.SearchShopifyCustomersTool().run(query="ghost")
    assert "No customers found" in result


def test_search_customers_formats_results(monkeypatch):
    customers = {
        "customers": [
            {
                "id": 5,
                "first_name": "Nathan",
                "last_name": "Cao",
                "email": "nathan@example.com",
                "orders_count": 3,
                "total_spent": "150.00",
            }
        ]
    }
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse(customers))

    result = shopify_tools.SearchShopifyCustomersTool().run(query="Nathan")

    assert "Nathan Cao" in result
    assert "nathan@example.com" in result
    assert "3 order(s)" in result


def test_get_customer_orders_none(monkeypatch):
    monkeypatch.setattr(shopify_tools.client, "get", lambda *a, **kw: _FakeResponse({"orders": []}))
    result = shopify_tools.GetShopifyCustomerOrdersTool().run(customer_id=5)
    assert "no orders" in result


def test_create_discount_percentage(monkeypatch):
    captured = {"posts": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["posts"].append((url, json))
        if "price_rules.json" in url and "discount_codes" not in url:
            return _FakeResponse({"price_rule": {"id": 99}})
        return _FakeResponse({"discount_code": {"code": "SUMMER10"}})

    monkeypatch.setattr(shopify_tools.client, "post", fake_post)

    result = shopify_tools.CreateShopifyDiscountTool().run(code="SUMMER10", discount_type="percentage", value=10)

    assert "SUMMER10" in result
    assert "10%" in result
    rule_call = captured["posts"][0]
    assert rule_call[1]["price_rule"]["value"] == "-10"
    assert rule_call[1]["price_rule"]["value_type"] == "percentage"
    code_call = captured["posts"][1]
    assert "price_rules/99/discount_codes.json" in code_call[0]
