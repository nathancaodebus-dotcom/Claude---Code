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
