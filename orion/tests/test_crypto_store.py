import threading

import pytest

from core.store import Store


def test_propose_crypto_trade_starts_pending(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="risky", action="buy", coin="bitcoin", quantity=0.1, price_usd=50000, reasoning="test"
    )

    proposal = store.get_crypto_trade_proposal(proposal_id)
    assert proposal.status == "pending"
    assert proposal.portfolio == "risky"
    assert proposal.coin == "bitcoin"


def test_propose_crypto_trade_rejects_bad_action(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    with pytest.raises(ValueError, match="buy.*sell"):
        store.propose_crypto_trade(
            portfolio="risky", action="short", coin="bitcoin", quantity=1, price_usd=1, reasoning="x"
        )


def test_propose_crypto_trade_rejects_non_positive_quantity(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    with pytest.raises(ValueError, match="positive"):
        store.propose_crypto_trade(
            portfolio="risky", action="buy", coin="bitcoin", quantity=0, price_usd=1, reasoning="x"
        )


def test_confirm_buy_creates_a_new_holding(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=0.5, price_usd=40000, reasoning="test"
    )

    store.confirm_crypto_trade(proposal_id)

    holdings = store.list_crypto_holdings("stable")
    assert len(holdings) == 1
    assert holdings[0].quantity == 0.5
    assert holdings[0].avg_buy_price_usd == 40000
    assert store.get_crypto_trade_proposal(proposal_id).status == "confirmed"


def test_confirm_second_buy_averages_cost_basis(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    first = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )
    store.confirm_crypto_trade(first)
    second = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=200, reasoning="x"
    )
    store.confirm_crypto_trade(second)

    holdings = store.list_crypto_holdings("stable")
    assert holdings[0].quantity == 2
    assert holdings[0].avg_buy_price_usd == 150  # (1*100 + 1*200) / 2


def test_confirm_sell_reduces_quantity(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    buy = store.propose_crypto_trade(
        portfolio="risky", action="buy", coin="ethereum", quantity=2, price_usd=1000, reasoning="x"
    )
    store.confirm_crypto_trade(buy)
    sell = store.propose_crypto_trade(
        portfolio="risky", action="sell", coin="ethereum", quantity=0.5, price_usd=1200, reasoning="x"
    )
    store.confirm_crypto_trade(sell)

    holdings = store.list_crypto_holdings("risky")
    assert holdings[0].quantity == 1.5
    assert holdings[0].avg_buy_price_usd == 1000  # cost basis unaffected by selling


def test_confirm_sell_that_empties_a_holding_removes_it(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    buy = store.propose_crypto_trade(
        portfolio="risky", action="buy", coin="ethereum", quantity=1, price_usd=1000, reasoning="x"
    )
    store.confirm_crypto_trade(buy)
    sell = store.propose_crypto_trade(
        portfolio="risky", action="sell", coin="ethereum", quantity=1, price_usd=1200, reasoning="x"
    )
    store.confirm_crypto_trade(sell)

    assert store.list_crypto_holdings("risky") == []


def test_confirm_sell_without_enough_holdings_raises(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    sell = store.propose_crypto_trade(
        portfolio="risky", action="sell", coin="ethereum", quantity=1, price_usd=1200, reasoning="x"
    )
    with pytest.raises(ValueError, match="only 0"):
        store.confirm_crypto_trade(sell)

    # The proposal must stay pending — a failed confirmation isn't a resolution.
    assert store.get_crypto_trade_proposal(sell).status == "pending"


def test_confirm_buy_folds_fee_into_cost_basis(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100,
        reasoning="x", fee_pct=1.0,
    )

    result = store.confirm_crypto_trade(proposal_id)

    assert result["effective_price_usd"] == pytest.approx(101.0)  # 100 * 1.01
    assert result["fee_amount_usd"] == pytest.approx(1.0)  # 1 * 100 * 1%
    holdings = store.list_crypto_holdings("stable")
    assert holdings[0].avg_buy_price_usd == pytest.approx(101.0)


def test_confirm_sell_reports_fee_without_touching_cost_basis(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    buy = store.propose_crypto_trade(
        portfolio="risky", action="buy", coin="ethereum", quantity=2, price_usd=1000, reasoning="x"
    )
    store.confirm_crypto_trade(buy)
    sell = store.propose_crypto_trade(
        portfolio="risky", action="sell", coin="ethereum", quantity=1, price_usd=1200,
        reasoning="x", fee_pct=2.0,
    )

    result = store.confirm_crypto_trade(sell)

    assert result["effective_price_usd"] == pytest.approx(1176.0)  # 1200 * 0.98
    assert result["fee_amount_usd"] == pytest.approx(24.0)  # 1 * 1200 * 2%
    holdings = store.list_crypto_holdings("risky")
    assert holdings[0].avg_buy_price_usd == 1000  # cost basis unaffected by a sell's fee


def test_propose_crypto_trade_rejects_negative_fee(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    with pytest.raises(ValueError, match="fee_pct"):
        store.propose_crypto_trade(
            portfolio="risky", action="buy", coin="bitcoin", quantity=1, price_usd=1,
            reasoning="x", fee_pct=-1.0,
        )


def test_confirm_unknown_proposal_raises(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    with pytest.raises(ValueError, match="No trade proposal"):
        store.confirm_crypto_trade(999)


def test_confirm_already_resolved_proposal_raises(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    buy = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )
    store.confirm_crypto_trade(buy)

    with pytest.raises(ValueError, match="already confirmed"):
        store.confirm_crypto_trade(buy)


def test_concurrent_confirm_calls_apply_the_trade_at_most_once(tmp_path):
    """core/agent.py dispatches a turn's tool calls concurrently (a thread
    pool) — if confirm_crypto_trade were ever called twice for the same
    proposal id at once, a naive read-then-write (check status, then apply
    to holdings, then mark confirmed) lets both calls read 'pending' before
    either writes, silently doubling the position. Fires the same confirm
    from several threads at once and checks the holding reflects exactly
    one buy, never more, no matter how many callers raced for it."""
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )

    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def confirm() -> None:
        try:
            store.confirm_crypto_trade(proposal_id)
            outcome = "ok"
        except ValueError:
            outcome = "error"
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=confirm) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("ok") == 1, "the trade was applied more than once"
    assert outcomes.count("error") == 9

    holdings = store.list_crypto_holdings("stable")
    assert len(holdings) == 1
    assert holdings[0].quantity == 1


def test_concurrent_reject_calls_only_succeed_once(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )

    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def reject() -> None:
        try:
            store.reject_crypto_trade(proposal_id)
            outcome = "ok"
        except ValueError:
            outcome = "error"
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=reject) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("ok") == 1
    assert outcomes.count("error") == 9
    assert store.get_crypto_trade_proposal(proposal_id).status == "rejected"


def test_reject_crypto_trade_marks_rejected_and_does_not_touch_holdings(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    proposal_id = store.propose_crypto_trade(
        portfolio="risky", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )

    store.reject_crypto_trade(proposal_id)

    assert store.get_crypto_trade_proposal(proposal_id).status == "rejected"
    assert store.list_crypto_holdings("risky") == []


def test_list_pending_crypto_trades_excludes_resolved(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    still_pending = store.propose_crypto_trade(
        portfolio="risky", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )
    to_confirm = store.propose_crypto_trade(
        portfolio="risky", action="buy", coin="ethereum", quantity=1, price_usd=100, reasoning="x"
    )
    store.confirm_crypto_trade(to_confirm)

    pending = store.list_pending_crypto_trades("risky")
    assert [p.id for p in pending] == [still_pending]


def test_holdings_filtered_by_portfolio(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    stable_buy = store.propose_crypto_trade(
        portfolio="stable", action="buy", coin="bitcoin", quantity=1, price_usd=100, reasoning="x"
    )
    risky_buy = store.propose_crypto_trade(
        portfolio="risky", action="buy", coin="dogecoin", quantity=100, price_usd=0.1, reasoning="x"
    )
    store.confirm_crypto_trade(stable_buy)
    store.confirm_crypto_trade(risky_buy)

    assert [h.coin for h in store.list_crypto_holdings("stable")] == ["bitcoin"]
    assert [h.coin for h in store.list_crypto_holdings("risky")] == ["dogecoin"]
    assert len(store.list_crypto_holdings()) == 2
