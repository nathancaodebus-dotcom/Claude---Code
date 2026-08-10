import time

from core.store import Store


def test_todo_crud(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    todo_id = store.add_todo("buy milk")

    assert [t.text for t in store.list_todos()] == ["buy milk"]

    store.complete_todo(todo_id)
    assert store.list_todos() == []
    assert [t.text for t in store.list_todos(include_done=True)] == ["buy milk"]


def test_notes_search(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store.add_note("remember the milk")
    store.add_note("call the dentist")

    assert len(store.list_notes()) == 2
    assert [n.text for n in store.list_notes(query="milk")] == ["remember the milk"]


def test_shopping_list(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store.add_shopping_item("eggs")
    store.add_shopping_item("bread")

    assert store.list_shopping_items() == ["eggs", "bread"]

    store.clear_shopping_list()
    assert store.list_shopping_items() == []


def test_reminders_due_and_delivery(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    past_id = store.add_reminder("past reminder", time.time() - 10)
    future_id = store.add_reminder("future reminder", time.time() + 3600)

    due = store.due_reminders()
    assert [r.id for r in due] == [past_id]

    store.mark_reminder_delivered(past_id)
    assert store.due_reminders() == []
    assert [r.id for r in store.list_pending_reminders()] == [future_id]


def test_cancel_reminder(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    reminder_id = store.add_reminder("something", time.time() + 3600)

    assert store.cancel_reminder(reminder_id) is True
    assert store.cancel_reminder(reminder_id) is False
    assert store.list_pending_reminders() == []
