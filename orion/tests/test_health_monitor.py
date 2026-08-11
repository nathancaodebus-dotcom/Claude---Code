import time

from core.health_monitor import HealthMonitor, pending_alerts
from core.store import Store


def _fail(store: Store, tool_name: str, times: int) -> None:
    for _ in range(times):
        store.log_failed_command(tool_name, "boom")


def test_no_alert_below_threshold(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _fail(store, "search_emails", 2)

    assert pending_alerts(store, failure_threshold=3) == []


def test_alerts_when_threshold_reached(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _fail(store, "search_emails", 3)

    alerts = pending_alerts(store, failure_threshold=3)

    assert len(alerts) == 1
    tool_name, message = alerts[0]
    assert tool_name == "search_emails"
    assert "search_emails" in message
    assert "3 times" in message


def test_ignores_failures_outside_the_window(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store._conn.execute(
        "INSERT INTO failed_commands (tool_name, error, created_at) VALUES (?, ?, ?)",
        ("search_emails", "boom", time.time() - 1000),
    )
    store._conn.commit()

    assert pending_alerts(store, failure_threshold=1, window_s=500) == []


def test_does_not_recompute_after_marked_alerted_within_cooldown(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _fail(store, "search_emails", 3)

    first = pending_alerts(store, failure_threshold=3, cooldown_s=3600)
    assert len(first) == 1
    store.mark_health_alerted(first[0][0])

    second = pending_alerts(store, failure_threshold=3, cooldown_s=3600)
    assert second == []


def test_still_pending_until_marked_alerted(tmp_path):
    # Simulates a delivery failure: pending_alerts() itself never marks
    # anything, so an undelivered alert keeps showing up on every call.
    store = Store(db_path=str(tmp_path / "test.db"))
    _fail(store, "search_emails", 3)

    first = pending_alerts(store, failure_threshold=3, cooldown_s=3600)
    second = pending_alerts(store, failure_threshold=3, cooldown_s=3600)

    assert len(first) == 1
    assert len(second) == 1


def test_realerts_after_cooldown_expires(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _fail(store, "search_emails", 3)

    first = pending_alerts(store, failure_threshold=3, cooldown_s=0)
    store.mark_health_alerted(first[0][0])
    second = pending_alerts(store, failure_threshold=3, cooldown_s=0)

    assert len(first) == 1
    assert len(second) == 1


def test_multiple_failing_tools_each_get_a_message(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _fail(store, "search_emails", 3)
    _fail(store, "get_crypto_market_data", 5)

    alerts = pending_alerts(store, failure_threshold=3)

    assert len(alerts) == 2


def test_health_monitor_thread_delivers_alerts_and_marks_only_on_success(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    _fail(store, "search_emails", 3)

    calls = {"count": 0}

    def flaky_notify(text: str) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient delivery failure")

    monitor = HealthMonitor(store, notify=flaky_notify, poll_interval_s=0.05)
    monitor.start()
    try:
        deadline = time.time() + 2
        while calls["count"] < 2 and time.time() < deadline:
            time.sleep(0.02)
    finally:
        monitor.stop()

    assert calls["count"] >= 2  # first delivery failed, thread retried on next poll
    assert store.last_health_alert("search_emails") is not None  # eventually marked once it succeeded
