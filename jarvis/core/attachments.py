"""Lets a tool hand a generated file (QR code image, etc.) back to whichever
interface is running, without the agent loop's text-only return path having
to know about files. A tool calls `attachments.push(path)`; the interface
drains the queue after each `agent.respond()` call and does the right thing
(send as a Telegram photo/document, print the path in the CLI, ...).

Process-global and not thread-safe beyond what `queue.Queue` gives for free —
fine for the single-user, single-session-at-a-time interfaces this project has.
"""
from __future__ import annotations

import queue

_queue: queue.Queue[str] = queue.Queue()


def push(path: str) -> None:
    _queue.put(path)


def drain() -> list[str]:
    paths = []
    while not _queue.empty():
        paths.append(_queue.get_nowait())
    return paths
