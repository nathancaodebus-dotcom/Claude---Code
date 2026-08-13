"""FastAPI backend for the storefront shopping widget. Deliberately simple:
one process, in-memory session state (conversation history + cart id per
session_id). That means state doesn't survive a restart and doesn't scale
across multiple backend instances — a real limitation for a busy store,
fine for a single small deployment. If that stops being true, swap
_sessions for Redis (or similar) without changing the routes below; the
session store is already isolated behind get/create helpers for exactly
that reason.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import AgentReply, SessionState, ShoppingAgent
from config import config
from shopify_storefront import Product, ShopifyStorefrontClient, ShopifyStorefrontError

app = FastAPI(title="Orion Shopping Assistant")

if config.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

_storefront = ShopifyStorefrontClient(
    config.shopify_store_domain, config.storefront_access_token, config.storefront_api_version
)
_agent = ShoppingAgent(_storefront, config.anthropic_api_key, config.model)
_sessions: dict[str, SessionState] = {}


def _get_session(session_id: str) -> SessionState:
    if session_id not in _sessions:
        _sessions[session_id] = SessionState()
    return _sessions[session_id]


def _product_out(p: Product) -> dict:
    return {
        "id": p.id,
        "handle": p.handle,
        "title": p.title,
        "image_url": p.image_url,
        "price": p.price,
        "currency": p.currency,
        "variants": p.variants,
    }


def _cart_out(reply_cart) -> dict | None:
    if reply_cart is None:
        return None
    return {
        "id": reply_cart.id,
        "checkout_url": reply_cart.checkout_url,
        "total_amount": reply_cart.total_amount,
        "currency": reply_cart.currency,
        "lines": [asdict(l) for l in reply_cart.lines],
    }


class ChatRequest(BaseModel):
    session_id: str
    message: str


class AddToCartRequest(BaseModel):
    session_id: str
    variant_id: str
    quantity: int = 1


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    if not req.message.strip():
        raise HTTPException(400, "message is required")

    session = _get_session(req.session_id)
    try:
        reply: AgentReply = _agent.respond(session, req.message)
    except ShopifyStorefrontError as exc:
        raise HTTPException(502, f"Store error: {exc}") from exc

    return {
        "reply": reply.text,
        "products": [_product_out(p) for p in reply.products],
        "cart": _cart_out(reply.cart),
    }


@app.post("/cart/add")
def add_to_cart(req: AddToCartRequest) -> dict:
    session = _get_session(req.session_id)
    try:
        if session.cart_id is None:
            cart = _storefront.create_cart(req.variant_id, req.quantity)
        else:
            cart = _storefront.add_to_cart(session.cart_id, req.variant_id, req.quantity)
    except ShopifyStorefrontError as exc:
        raise HTTPException(502, f"Store error: {exc}") from exc

    session.cart_id = cart.id
    return {"cart": _cart_out(cart)}


@app.get("/cart/{session_id}")
def get_cart(session_id: str) -> dict:
    session = _sessions.get(session_id)
    if session is None or session.cart_id is None:
        return {"cart": None}
    try:
        cart = _storefront.get_cart(session.cart_id)
    except ShopifyStorefrontError as exc:
        raise HTTPException(502, f"Store error: {exc}") from exc
    return {"cart": _cart_out(cart)}


@app.post("/session")
def new_session() -> dict:
    session_id = str(uuid.uuid4())
    _sessions[session_id] = SessionState()
    return {"session_id": session_id}
