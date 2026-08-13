import pytest

from agent import ShoppingAgent, SessionState
from shopify_storefront import Cart, CartLine, Product, ShopifyStorefrontClient, ShopifyStorefrontError


class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, id, name, input):  # noqa: A002
        self.id = id
        self.name = name
        self.input = input


class _FakeMessage:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessagesAPI:
    def __init__(self, turns):
        self._turns = list(turns)
        self.create_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self._turns.pop(0)


class _FakeClient:
    def __init__(self, turns):
        self.messages = _FakeMessagesAPI(turns)


class _FakeStorefront:
    """Stand-in for ShopifyStorefrontClient — records calls, returns canned data."""

    def __init__(self):
        self.search_calls = []
        self.cart = Cart(
            id="gid://shopify/Cart/1",
            checkout_url="https://store.example.com/cart/c/1",
            lines=[CartLine("l1", "v1", "T-Shirt", "Small", 1)],
            total_amount="20.00",
            currency="CHF",
        )

    def search_products(self, query, limit=8):
        self.search_calls.append((query, limit))
        return [
            Product(
                id="p1", handle="tee", title="T-Shirt", description="Comfy",
                image_url="https://example.com/tee.png", price="20.00", currency="CHF",
                variants=[{"id": "v1", "title": "Small", "available": True, "price": "20.00", "options": {}}],
            )
        ]

    def get_product(self, handle):
        if handle != "tee":
            return None
        return Product(
            id="p1", handle="tee", title="T-Shirt", description="Comfy",
            image_url="https://example.com/tee.png", price="20.00", currency="CHF",
            variants=[{"id": "v1", "title": "Small", "available": True, "price": "20.00", "options": {}}],
        )

    def create_cart(self, variant_id, quantity):
        return self.cart

    def add_to_cart(self, cart_id, variant_id, quantity):
        return self.cart

    def get_cart(self, cart_id):
        return self.cart


def _make_agent(turns):
    agent = ShoppingAgent(_FakeStorefront(), anthropic_api_key="fake", model="claude-sonnet-5")
    agent._client = _FakeClient(turns)
    return agent


def test_simple_text_reply_no_tool_use():
    turns = [_FakeMessage([_TextBlock("Hi there!")], stop_reason="end_turn")]
    agent = _make_agent(turns)
    session = SessionState()

    reply = agent.respond(session, "hello")

    assert reply.text == "Hi there!"
    assert reply.products == []
    assert reply.cart is None


def test_search_products_tool_use_collects_products():
    turns = [
        _FakeMessage(
            [_ToolUseBlock("t1", "search_products", {"query": "shirt"})], stop_reason="tool_use"
        ),
        _FakeMessage([_TextBlock("Found a T-Shirt for you!")], stop_reason="end_turn"),
    ]
    agent = _make_agent(turns)
    session = SessionState()

    reply = agent.respond(session, "do you have shirts?")

    assert reply.text == "Found a T-Shirt for you!"
    assert len(reply.products) == 1
    assert reply.products[0].title == "T-Shirt"
    assert agent._storefront.search_calls == [("shirt", 8)]


def test_add_to_cart_creates_cart_and_sets_session_id():
    turns = [
        _FakeMessage(
            [_ToolUseBlock("t1", "add_to_cart", {"variant_id": "v1", "quantity": 1})], stop_reason="tool_use"
        ),
        _FakeMessage([_TextBlock("Added it!")], stop_reason="end_turn"),
    ]
    agent = _make_agent(turns)
    session = SessionState()

    reply = agent.respond(session, "add the small tee to my cart")

    assert session.cart_id == "gid://shopify/Cart/1"
    assert reply.cart is not None
    assert reply.cart.total_amount == "20.00"


def test_add_to_cart_reuses_existing_cart_id():
    turns = [
        _FakeMessage(
            [_ToolUseBlock("t1", "add_to_cart", {"variant_id": "v1", "quantity": 2})], stop_reason="tool_use"
        ),
        _FakeMessage([_TextBlock("Added another!")], stop_reason="end_turn"),
    ]
    agent = _make_agent(turns)
    session = SessionState(cart_id="gid://shopify/Cart/1")

    agent.respond(session, "add one more")

    assert session.cart_id == "gid://shopify/Cart/1"


def test_view_cart_with_no_cart_yet():
    turns = [
        _FakeMessage([_ToolUseBlock("t1", "view_cart", {})], stop_reason="tool_use"),
        _FakeMessage([_TextBlock("Your cart is empty.")], stop_reason="end_turn"),
    ]
    agent = _make_agent(turns)
    session = SessionState()

    reply = agent.respond(session, "what's in my cart?")

    assert reply.text == "Your cart is empty."
    assert reply.cart is None


def test_storefront_error_surfaces_as_tool_result_not_a_crash():
    class _ErroringStorefront(_FakeStorefront):
        def search_products(self, query, limit=8):
            raise ShopifyStorefrontError("rate limited")

    turns = [
        _FakeMessage([_ToolUseBlock("t1", "search_products", {"query": "shirt"})], stop_reason="tool_use"),
        _FakeMessage([_TextBlock("Sorry, I couldn't search right now.")], stop_reason="end_turn"),
    ]
    agent = ShoppingAgent(_ErroringStorefront(), anthropic_api_key="fake", model="claude-sonnet-5")
    agent._client = _FakeClient(turns)
    session = SessionState()

    reply = agent.respond(session, "shirts?")

    assert reply.text == "Sorry, I couldn't search right now."
    tool_result_content = session.history[-2]["content"][0]["content"]
    assert "Store error" in tool_result_content
    assert "rate limited" in tool_result_content


def test_get_product_details_unknown_handle():
    turns = [
        _FakeMessage(
            [_ToolUseBlock("t1", "get_product_details", {"handle": "ghost"})], stop_reason="tool_use"
        ),
        _FakeMessage([_TextBlock("I couldn't find that item.")], stop_reason="end_turn"),
    ]
    agent = _make_agent(turns)
    session = SessionState()

    reply = agent.respond(session, "tell me about the ghost product")

    assert reply.products == []
    assert reply.text == "I couldn't find that item."
