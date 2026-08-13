import pytest
from fastapi.testclient import TestClient

import app as app_module
from agent import AgentReply, SessionState
from shopify_storefront import Cart, CartLine, Product, ShopifyStorefrontError


class _FakeAgent:
    def __init__(self, reply=None, error=None):
        self._reply = reply
        self._error = error
        self.calls = []

    def respond(self, session, message):
        self.calls.append((session, message))
        if self._error:
            raise self._error
        return self._reply


class _FakeStorefront:
    def __init__(self, cart=None, error=None):
        self._cart = cart
        self._error = error
        self.create_calls = []
        self.add_calls = []

    def create_cart(self, variant_id, quantity):
        self.create_calls.append((variant_id, quantity))
        if self._error:
            raise self._error
        return self._cart

    def add_to_cart(self, cart_id, variant_id, quantity):
        self.add_calls.append((cart_id, variant_id, quantity))
        if self._error:
            raise self._error
        return self._cart

    def get_cart(self, cart_id):
        if self._error:
            raise self._error
        return self._cart


@pytest.fixture(autouse=True)
def reset_sessions():
    app_module._sessions.clear()
    yield
    app_module._sessions.clear()


@pytest.fixture
def client():
    return TestClient(app_module.app)


def _cart():
    return Cart(
        id="gid://shopify/Cart/1",
        checkout_url="https://store.example.com/cart/c/1",
        lines=[CartLine("l1", "v1", "T-Shirt", "Small", 1)],
        total_amount="20.00",
        currency="CHF",
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_new_session_returns_uuid(client):
    resp = client.post("/session")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    assert len(session_id) > 10
    assert session_id in app_module._sessions


def test_chat_rejects_empty_message(client):
    resp = client.post("/chat", json={"session_id": "s1", "message": "   "})
    assert resp.status_code == 400


def test_chat_returns_reply_products_and_cart(client, monkeypatch):
    product = Product(
        id="p1", handle="tee", title="T-Shirt", description="Comfy",
        image_url="https://example.com/tee.png", price="20.00", currency="CHF",
        variants=[{"id": "v1", "title": "Small", "available": True, "price": "20.00", "options": {}}],
    )
    fake_agent = _FakeAgent(reply=AgentReply(text="Here's a shirt!", products=[product], cart=_cart()))
    monkeypatch.setattr(app_module, "_agent", fake_agent)

    resp = client.post("/chat", json={"session_id": "s1", "message": "got any shirts?"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == "Here's a shirt!"
    assert data["products"][0]["title"] == "T-Shirt"
    assert data["cart"]["total_amount"] == "20.00"
    assert fake_agent.calls[0][1] == "got any shirts?"


def test_chat_reuses_session_state_across_calls(client, monkeypatch):
    fake_agent = _FakeAgent(reply=AgentReply(text="ok", products=[], cart=None))
    monkeypatch.setattr(app_module, "_agent", fake_agent)

    client.post("/chat", json={"session_id": "s1", "message": "hi"})
    client.post("/chat", json={"session_id": "s1", "message": "again"})

    assert fake_agent.calls[0][0] is fake_agent.calls[1][0]  # same SessionState object


def test_chat_storefront_error_returns_502(client, monkeypatch):
    fake_agent = _FakeAgent(error=ShopifyStorefrontError("down"))
    monkeypatch.setattr(app_module, "_agent", fake_agent)

    resp = client.post("/chat", json={"session_id": "s1", "message": "hi"})

    assert resp.status_code == 502
    assert "down" in resp.json()["detail"]


def test_add_to_cart_creates_cart_when_none_exists(client, monkeypatch):
    fake_storefront = _FakeStorefront(cart=_cart())
    monkeypatch.setattr(app_module, "_storefront", fake_storefront)

    resp = client.post("/cart/add", json={"session_id": "s1", "variant_id": "v1", "quantity": 1})

    assert resp.status_code == 200
    assert resp.json()["cart"]["id"] == "gid://shopify/Cart/1"
    assert fake_storefront.create_calls == [("v1", 1)]
    assert app_module._sessions["s1"].cart_id == "gid://shopify/Cart/1"


def test_add_to_cart_reuses_existing_cart(client, monkeypatch):
    fake_storefront = _FakeStorefront(cart=_cart())
    monkeypatch.setattr(app_module, "_storefront", fake_storefront)
    app_module._sessions["s1"] = SessionState(cart_id="gid://shopify/Cart/1")

    client.post("/cart/add", json={"session_id": "s1", "variant_id": "v2", "quantity": 3})

    assert fake_storefront.add_calls == [("gid://shopify/Cart/1", "v2", 3)]


def test_get_cart_for_unknown_session_returns_none(client):
    resp = client.get("/cart/unknown-session")
    assert resp.json() == {"cart": None}


def test_get_cart_for_session_with_cart(client, monkeypatch):
    fake_storefront = _FakeStorefront(cart=_cart())
    monkeypatch.setattr(app_module, "_storefront", fake_storefront)
    app_module._sessions["s1"] = SessionState(cart_id="gid://shopify/Cart/1")

    resp = client.get("/cart/s1")

    assert resp.json()["cart"]["total_amount"] == "20.00"


def test_cors_configured_from_allowed_origins():
    from starlette.middleware.cors import CORSMiddleware

    assert any(m.cls is CORSMiddleware for m in app_module.app.user_middleware)
