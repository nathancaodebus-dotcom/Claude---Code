"""Watches for tools failing repeatedly and produces a proactive alert —
complements the existing pull-only list_failed_commands tool (§ system
tools), which only surfaces problems if the user thinks to ask.

pending_alerts() is the shared logic (also used directly by
interfaces/telegram_bot.py's own JobQueue, which needs an async send
rather than this module's synchronous Notifier). It only *computes* what
needs alerting — the caller marks a tool alerted via
store.mark_health_alerted() once delivery actually succeeds, the same
deliver-then-mark ordering core/scheduler.py's ReminderScheduler uses, so
a transient delivery failure (network blip, TTS error) gets retried on
the next poll instead of being silently dropped until the cooldown lifts.

HealthMonitor wraps pending_alerts() in the same background-thread-plus-
callback shape as ReminderScheduler, so it plugs into the CLI and voice
loop the same way.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from core.store import Store

Notifier = Callable[[str], None]

# A handful of one-off errors (a flaky network blip) shouldn't interrupt the
# user — only a sustained problem (an expired token, a dead service) should.
FAILURE_THRESHOLD = 3
WINDOW_S = 60 * 60  # look at failures from the last hour
COOLDOWN_S = 6 * 60 * 60  # don't re-alert on the same tool more than once per 6h


def pending_alerts(
    store: Store,
    failure_threshold: int = FAILURE_THRESHOLD,
    window_s: float = WINDOW_S,
    cooldown_s: float = COOLDOWN_S,
) -> list[tuple[str, str]]:
    """Return (tool_name, message) pairs for tools that have failed at
    least `failure_threshold` times within `window_s` and haven't already
    been alerted on within `cooldown_s`. Does not mark anything as
    alerted — call store.mark_health_alerted(tool_name) after a
    successful delivery."""
    now = time.time()
    results = []
    for tool_name, count in sorted(store.recent_failure_counts(window_s).items()):
        if count < failure_threshold:
            continue
        last_alert = store.last_health_alert(tool_name)
        if last_alert is not None and now - last_alert < cooldown_s:
            continue
        message = (
            f"⚠️ {tool_name} has failed {count} times in the last hour — might be an "
            "expired key or a dead service. Ask me to list failed commands for details."
        )
        results.append((tool_name, message))
    return results


class HealthMonitor:
    def __init__(self, store: Store, notify: Notifier, poll_interval_s: float = 300.0):
        self._store = store
        self._notify = notify
        self._poll_interval_s = poll_interval_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            for tool_name, message in pending_alerts(self._store):
                try:
                    self._notify(message)
                except Exception:
                    continue  # transient delivery failure — retry next poll, don't mark alerted
                self._store.mark_health_alerted(tool_name)
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
