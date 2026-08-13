"""To-dos, notes, a shopping list, and reminders/timers — the 'keeps my life
organized' half of a second self."""
from __future__ import annotations

import re
import time
from datetime import datetime

from core.store import Store
from tools.base import Tool

# 'w'/'week'/'weeks' added because tools/project_tools.py's AddMilestoneTool
# documents its own in_duration parameter with exactly that example
# ("e.g. '3 days', '2 weeks'") — without it, following that tool's own
# documented example raised a ValueError before add_milestone ever ran,
# aborting the call instead of creating the milestone.
_DURATION_RE = re.compile(
    r"(\d+)\s*(w|week|weeks|d|day|days|h|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)"
)

_UNIT_SECONDS = {
    "w": 604800, "week": 604800, "weeks": 604800,
    "d": 86400, "day": 86400, "days": 86400,
    "h": 3600, "hour": 3600, "hours": 3600,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
}


def parse_duration(text: str) -> int:
    """Parse a free-form duration like '10m', '1h30m', '2 days', '3 weeks' into seconds."""
    matches = _DURATION_RE.findall(text.lower())
    if not matches:
        raise ValueError(f"Could not parse a duration from '{text}'. Try e.g. '10m', '1h30m', '2 days', '3 weeks'.")
    return sum(int(amount) * _UNIT_SECONDS[unit] for amount, unit in matches)


# --- Todos ---

class AddTodoTool(Tool):
    requires_network = False
    name = "add_todo"
    description = "Add an item to the user's to-do list."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, text: str) -> str:
        todo_id = self._store.add_todo(text)
        return f"Added to-do #{todo_id}: {text}"


class ListTodosTool(Tool):
    requires_network = False
    name = "list_todos"
    description = "List the user's to-do items. By default only shows items not yet done."
    input_schema = {
        "type": "object",
        "properties": {"include_done": {"type": "boolean", "description": "Include completed items too."}},
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, include_done: bool = False) -> str:
        todos = self._store.list_todos(include_done=include_done)
        if not todos:
            return "The to-do list is empty."
        return "\n".join(f"- [{t.id}] {'x' if t.done else ' '} {t.text}" for t in todos)


class CompleteTodoTool(Tool):
    requires_network = False
    name = "complete_todo"
    description = "Mark a to-do item as done, by its id (from list_todos)."
    input_schema = {
        "type": "object",
        "properties": {"todo_id": {"type": "integer"}},
        "required": ["todo_id"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, todo_id: int) -> str:
        ok = self._store.complete_todo(todo_id)
        return f"Marked to-do #{todo_id} as done." if ok else f"No to-do with id {todo_id}."


# --- Notes ---

class AddNoteTool(Tool):
    requires_network = False
    name = "add_note"
    description = "Save a free-form note for later (an idea, something to remember, a snippet)."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, text: str) -> str:
        note_id = self._store.add_note(text)
        return f"Saved note #{note_id}."


class ListNotesTool(Tool):
    requires_network = False
    name = "list_notes"
    description = "List saved notes, optionally filtered by a search substring."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Optional substring to search for."}},
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, query: str | None = None) -> str:
        notes = self._store.list_notes(query=query)
        if not notes:
            return "No matching notes."
        return "\n".join(
            f"- [{n.id}] {datetime.fromtimestamp(n.created_at):%Y-%m-%d %H:%M} — {n.text}" for n in notes
        )


# --- Shopping list ---

class AddShoppingItemTool(Tool):
    requires_network = False
    name = "add_shopping_item"
    description = "Add an item to the shopping list."
    input_schema = {
        "type": "object",
        "properties": {"item": {"type": "string"}},
        "required": ["item"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, item: str) -> str:
        self._store.add_shopping_item(item)
        return f"Added '{item}' to the shopping list."


class ListShoppingListTool(Tool):
    requires_network = False
    name = "list_shopping_list"
    description = "List everything currently on the shopping list."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, store: Store):
        self._store = store

    def run(self) -> str:
        items = self._store.list_shopping_items()
        if not items:
            return "The shopping list is empty."
        return "\n".join(f"- {item}" for item in items)


class ClearShoppingListTool(Tool):
    requires_network = False
    name = "clear_shopping_list"
    description = "Clear the entire shopping list, e.g. after the user has gone shopping."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, store: Store):
        self._store = store

    def run(self) -> str:
        self._store.clear_shopping_list()
        return "Shopping list cleared."


# --- Reminders / timers ---

class SetReminderTool(Tool):
    requires_network = False
    name = "set_reminder"
    description = (
        "Set a reminder or timer that will notify the user later. Provide either 'in' "
        "(a relative duration like '10m', '1h30m', '2 days') or 'at_iso' (an absolute "
        "ISO 8601 datetime). Delivery depends on the running interface — on Telegram, "
        "the user gets a message when it's due."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "What to remind the user about."},
            "in_duration": {"type": "string", "description": "Relative duration, e.g. '10m', '1h30m'."},
            "at_iso": {"type": "string", "description": "Absolute ISO 8601 datetime, e.g. '2026-08-12T09:00:00'."},
        },
        "required": ["text"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, text: str, in_duration: str | None = None, at_iso: str | None = None) -> str:
        if at_iso:
            due_at = datetime.fromisoformat(at_iso).timestamp()
        elif in_duration:
            due_at = time.time() + parse_duration(in_duration)
        else:
            raise ValueError("Provide either in_duration or at_iso.")

        reminder_id = self._store.add_reminder(text, due_at)
        when = datetime.fromtimestamp(due_at).strftime("%Y-%m-%d %H:%M:%S")
        return f"Reminder #{reminder_id} set for {when}: {text}"


class ListRemindersTool(Tool):
    requires_network = False
    name = "list_reminders"
    description = "List all pending (not yet delivered) reminders and timers."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, store: Store):
        self._store = store

    def run(self) -> str:
        reminders = self._store.list_pending_reminders()
        if not reminders:
            return "No pending reminders."
        return "\n".join(
            f"- [{r.id}] {datetime.fromtimestamp(r.due_at):%Y-%m-%d %H:%M} — {r.text}" for r in reminders
        )


class CancelReminderTool(Tool):
    requires_network = False
    name = "cancel_reminder"
    description = "Cancel a pending reminder or timer by its id (from list_reminders)."
    input_schema = {
        "type": "object",
        "properties": {"reminder_id": {"type": "integer"}},
        "required": ["reminder_id"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, reminder_id: int) -> str:
        ok = self._store.cancel_reminder(reminder_id)
        return f"Cancelled reminder #{reminder_id}." if ok else f"No reminder with id {reminder_id}."
