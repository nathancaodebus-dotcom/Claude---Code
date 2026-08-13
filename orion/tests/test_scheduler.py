import time

from core.scheduler import ReminderScheduler
from core.store import Store


def test_notifier_failure_does_not_mark_delivered_and_thread_survives(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store.add_reminder("will fail once", time.time() - 1)

    calls = {"count": 0}

    def flaky_notify(text: str) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient TTS failure")

    scheduler = ReminderScheduler(store, notify=flaky_notify, poll_interval_s=0.05)
    scheduler.start()
    try:
        deadline = time.time() + 2
        while calls["count"] < 2 and time.time() < deadline:
            time.sleep(0.02)
    finally:
        scheduler.stop()

    assert calls["count"] >= 2  # first call failed, thread kept polling and retried
    assert store.due_reminders() == []  # eventually delivered successfully


def test_due_reminders_failure_does_not_kill_the_loop(tmp_path):
    """Regression test: due_reminders() itself used to be uncaught, so a
    single transient error (DB lock, disk hiccup) would crash _loop's thread
    permanently — reminders would silently stop firing for the rest of the
    process's life. The fetch itself must be as retry-safe as delivery
    already was."""
    store = Store(db_path=str(tmp_path / "test.db"))
    store.add_reminder("survives a flaky fetch", time.time() - 1)

    real_due_reminders = store.due_reminders
    state = {"failures_left": 2}

    def flaky_due_reminders():
        if state["failures_left"] > 0:
            state["failures_left"] -= 1
            raise RuntimeError("simulated transient DB error")
        return real_due_reminders()

    store.due_reminders = flaky_due_reminders

    delivered = []
    scheduler = ReminderScheduler(store, notify=delivered.append, poll_interval_s=0.05)
    scheduler.start()
    try:
        deadline = time.time() + 2
        while not delivered and time.time() < deadline:
            time.sleep(0.02)
    finally:
        scheduler.stop()

    assert delivered, "loop never recovered from the flaky fetch — thread likely died"
