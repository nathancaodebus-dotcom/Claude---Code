"""Background poller that fires due reminders/timers.

Runs in its own thread so it works the same way regardless of which
interface started it (Telegram, voice loop, or even the CLI). Whoever
starts it decides what "notify" means — send a Telegram message, speak it
out loud, just print it.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from core.store import Store

Notifier = Callable[[str], None]


class ReminderScheduler:
    def __init__(self, store: Store, notify: Notifier, poll_interval_s: float = 15.0):
        self._store = store
        self._notify = notify
        self._poll_interval_s = poll_interval_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            for reminder in self._store.due_reminders():
                try:
                    self._notify(f"⏰ Reminder: {reminder.text}")
                finally:
                    self._store.mark_reminder_delivered(reminder.id)
            self._stop_event.wait(self._poll_interval_s)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
