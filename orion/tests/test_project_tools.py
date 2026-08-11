from core.store import Store
from tools.project_tools import (
    AddMilestoneTool,
    CompleteMilestoneTool,
    CreateProjectTool,
    ListProjectMilestonesTool,
    ListProjectsTool,
)


def test_create_project_tool(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    result = CreateProjectTool(store).run(name="Website Redesign")
    assert "Website Redesign" in result


def test_add_milestone_creates_project_if_missing(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    result = AddMilestoneTool(store).run(project_name="New Project", text="Kickoff")
    assert "Kickoff" in result
    assert store.get_project("New Project") is not None


def test_add_milestone_with_relative_due_date_schedules_reminder(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    AddMilestoneTool(store).run(project_name="Website Redesign", text="Launch beta", in_duration="3 days")

    assert len(store.list_pending_reminders()) == 1


def test_list_and_complete_milestones(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    AddMilestoneTool(store).run(project_name="Website Redesign", text="Launch beta")

    listing = ListProjectMilestonesTool(store).run(project_name="Website Redesign")
    assert "Launch beta" in listing

    milestone_id = store.list_milestones(store.get_project("Website Redesign").id)[0].id
    result = CompleteMilestoneTool(store).run(milestone_id=milestone_id)
    assert "done" in result.lower()

    listing_after = ListProjectMilestonesTool(store).run(project_name="Website Redesign")
    assert "No milestones" in listing_after


def test_list_projects_tool(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    CreateProjectTool(store).run(name="Alpha")
    CreateProjectTool(store).run(name="Beta")

    result = ListProjectsTool(store).run()
    assert "Alpha" in result
    assert "Beta" in result


def test_list_milestones_unknown_project(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    result = ListProjectMilestonesTool(store).run(project_name="Ghost")
    assert "No project" in result
