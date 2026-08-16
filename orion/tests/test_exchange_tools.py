import ccxt
import pytest

from tools.exchange_tools import CompareCryptoPriceAcrossExchangesTool, GetCryptoOrderBookTool


class _FakeExchange:
    def __init__(self, order_book=None, ticker=None, raises=None):
        self._order_book = order_book
        self._ticker = ticker
        self._raises = raises

    def fetch_order_book(self, pair, limit=None):
        if self._raises:
            raise self._raises
        return self._order_book

    def fetch_ticker(self, pair):
        if self._raises:
            raise self._raises
        return self._ticker


def _patch_exchange(monkeypatch, fake):
    monkeypatch.setattr("tools.exchange_tools._make_exchange", lambda exchange_id: fake)


# --- order book depth ---


def test_order_book_reports_best_bid_ask_and_spread(monkeypatch):
    fake = _FakeExchange(
        order_book={
            "bids": [[100.0, 1.0], [99.5, 2.0]],
            "asks": [[100.5, 1.5], [101.0, 2.5]],
            "symbol": "BTC/USDT",
            "timestamp": None,
            "datetime": None,
            "nonce": None,
        }
    )
    _patch_exchange(monkeypatch, fake)

    result = GetCryptoOrderBookTool().run(symbol="BTC", quote_currency="USDT", exchange="binance", depth=10)

    assert "best bid 100" in result
    assert "best ask 100.5" in result
    assert "spread" in result


def test_order_book_rejects_unknown_exchange():
    result = GetCryptoOrderBookTool().run(symbol="BTC", exchange="not-a-real-exchange")
    assert "must be one of" in result


def test_order_book_handles_exchange_error(monkeypatch):
    _patch_exchange(monkeypatch, _FakeExchange(raises=ccxt.ExchangeError("boom")))
    result = GetCryptoOrderBookTool().run(symbol="BTC", exchange="binance")
    assert "Couldn't fetch the order book" in result


def test_order_book_handles_empty_book(monkeypatch):
    _patch_exchange(
        monkeypatch,
        _FakeExchange(order_book={"bids": [], "asks": [], "symbol": "X", "timestamp": None, "datetime": None, "nonce": None}),
    )
    result = GetCryptoOrderBookTool().run(symbol="BTC", exchange="binance")
    assert "No order book data" in result


# --- multi-exchange price comparison ---


def test_compare_price_across_exchanges_reports_each_and_spread(monkeypatch):
    fakes = {
        "binance": _FakeExchange(ticker={"last": 100.0}),
        "kraken": _FakeExchange(ticker={"last": 102.0}),
    }
    monkeypatch.setattr("tools.exchange_tools._make_exchange", lambda exchange_id: fakes[exchange_id])

    result = CompareCryptoPriceAcrossExchangesTool().run(
        symbol="BTC", quote_currency="USDT", exchanges=["binance", "kraken"]
    )

    assert "binance: 100" in result
    assert "kraken: 102" in result
    assert "Spread across exchanges: 2.000%" in result


def test_compare_price_skips_an_unavailable_exchange(monkeypatch):
    fakes = {
        "binance": _FakeExchange(ticker={"last": 100.0}),
        "kraken": _FakeExchange(raises=ccxt.ExchangeError("down")),
    }
    monkeypatch.setattr("tools.exchange_tools._make_exchange", lambda exchange_id: fakes[exchange_id])

    result = CompareCryptoPriceAcrossExchangesTool().run(
        symbol="BTC", exchanges=["binance", "kraken"]
    )

    assert "binance: 100" in result
    assert "kraken: unavailable" in result
    assert "Not enough exchanges" in result


def test_compare_price_rejects_unknown_exchange():
    result = CompareCryptoPriceAcrossExchangesTool().run(symbol="BTC", exchanges=["not-real"])
    assert "Unknown exchange" in result


def test_compare_price_defaults_to_all_supported_exchanges(monkeypatch):
    calls = []

    def fake_make_exchange(exchange_id):
        calls.append(exchange_id)
        return _FakeExchange(ticker={"last": 100.0})

    monkeypatch.setattr("tools.exchange_tools._make_exchange", fake_make_exchange)

    CompareCryptoPriceAcrossExchangesTool().run(symbol="BTC")

    from tools.exchange_tools import _SUPPORTED_EXCHANGES

    assert calls == list(_SUPPORTED_EXCHANGES)
