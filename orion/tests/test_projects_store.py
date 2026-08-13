import time

from core.store import Store


def test_create_project_is_idempotent_by_name(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    id1 = store.create_project("Website Redesign")
    id2 = store.create_project("Website Redesign")
    assert id1 == id2


def test_add_and_list_milestones(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    project_id = store.create_project("Website Redesign")
    store.add_milestone(project_id, "Launch beta", time.time() + 3600)
    store.add_milestone(project_id, "No due date", None)

    milestones = store.list_milestones(project_id)
    assert len(milestones) == 2
    assert {m.text for m in milestones} == {"Launch beta", "No due date"}


def test_complete_milestone_hides_it_by_default(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    project_id = store.create_project("Website Redesign")
    milestone_id = store.add_milestone(project_id, "Launch beta", None)

    store.complete_milestone(milestone_id)
    assert store.list_milestones(project_id) == []
    assert len(store.list_milestones(project_id, include_done=True)) == 1


def test_upcoming_milestones_within_window(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    project_id = store.create_project("Website Redesign")
    store.add_milestone(project_id, "Soon", time.time() + 10)
    store.add_milestone(project_id, "Far", time.time() + 100000)

    upcoming = store.upcoming_milestones(within_seconds=60)
    assert [m.text for m in upcoming] == ["Soon"]


def test_get_project_missing_returns_none(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    assert store.get_project("nope") is None


def test_get_project_matches_case_insensitively(tmp_path):
    """Regression test: exact-match-only lookup used to let 'add a
    milestone to website redesign' silently fork a second, differently-
    cased project rather than attaching to the 'Website Redesign' one
    created earlier — two 'projects' that look identical to a human but
    are separate rows with milestones split invisibly across them."""
    store = Store(db_path=str(tmp_path / "test.db"))
    store.create_project("Website Redesign")

    found = store.get_project("website redesign")

    assert found is not None
    assert found.name == "Website Redesign"


def test_create_project_is_idempotent_across_case(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    id1 = store.create_project("Website Redesign")
    id2 = store.create_project("website redesign")
    assert id1 == id2
    assert len(store.list_projects()) == 1


def test_failed_command_log_roundtrip(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store.log_failed_command("get_weather", "connection timed out")
    store.log_failed_command("search_spotify", "401 unauthorized")

    rows = store.recent_failed_commands()
    assert len(rows) == 2
    assert rows[0][0] == "search_spotify"  # most recent first
