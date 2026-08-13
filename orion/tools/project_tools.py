"""Track projects and their milestones/deadlines, with alerts riding on the
existing reminder scheduler rather than a separate notification path."""
from __future__ import annotations

import time
from datetime import datetime

from core.store import Store
from tools.base import Tool
from tools.productivity_tools import parse_duration


class CreateProjectTool(Tool):
    name = "create_project"
    description = "Create a new project to track milestones/deadlines under."
    input_schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, name: str) -> str:
        # create_project is now itself a get-or-create (see core/store.py),
        # so it always "succeeds" — checking first means the response
        # accurately says which one happened instead of always claiming
        # "Created" even when nothing changed.
        existing = self._store.get_project(name)
        self._store.create_project(name)
        if existing:
            return f"Project '{existing.name}' already exists — nothing changed."
        return f"Created project '{name}'."


class AddMilestoneTool(Tool):
    name = "add_project_milestone"
    description = (
        "Add a milestone/deadline to a project. A reminder is automatically scheduled for it "
        "if a due date is given (in_duration or due_iso)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "project_name": {"type": "string"},
            "text": {"type": "string"},
            "in_duration": {"type": "string", "description": "Relative deadline, e.g. '3 days', '2 weeks'."},
            "due_iso": {"type": "string", "description": "Absolute ISO 8601 datetime deadline."},
        },
        "required": ["project_name", "text"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, project_name: str, text: str, in_duration: str | None = None, due_iso: str | None = None) -> str:
        project = self._store.get_project(project_name)
        if not project:
            project_id = self._store.create_project(project_name)
        else:
            project_id = project.id

        due_at = None
        if due_iso:
            due_at = datetime.fromisoformat(due_iso).timestamp()
        elif in_duration:
            due_at = time.time() + parse_duration(in_duration)

        milestone_id = self._store.add_milestone(project_id, text, due_at)
        if due_at:
            self._store.add_reminder(f"Milestone due for '{project_name}': {text}", due_at)

        when = f" (due {datetime.fromtimestamp(due_at):%Y-%m-%d %H:%M})" if due_at else ""
        return f"Added milestone #{milestone_id} to '{project_name}': {text}{when}"


class ListProjectMilestonesTool(Tool):
    name = "list_project_milestones"
    description = "List milestones for a project (open ones by default)."
    input_schema = {
        "type": "object",
        "properties": {
            "project_name": {"type": "string"},
            "include_done": {"type": "boolean"},
        },
        "required": ["project_name"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, project_name: str, include_done: bool = False) -> str:
        project = self._store.get_project(project_name)
        if not project:
            return f"No project named '{project_name}'."

        milestones = self._store.list_milestones(project.id, include_done=include_done)
        if not milestones:
            return f"No milestones for '{project_name}'."

        lines = []
        for m in milestones:
            due = f" (due {datetime.fromtimestamp(m.due_at):%Y-%m-%d})" if m.due_at else ""
            lines.append(f"- [{m.id}] {'x' if m.done else ' '} {m.text}{due}")
        return "\n".join(lines)


class CompleteMilestoneTool(Tool):
    name = "complete_project_milestone"
    description = "Mark a project milestone as done, by its id (from list_project_milestones)."
    input_schema = {
        "type": "object",
        "properties": {"milestone_id": {"type": "integer"}},
        "required": ["milestone_id"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, milestone_id: int) -> str:
        ok = self._store.complete_milestone(milestone_id)
        return f"Marked milestone #{milestone_id} as done." if ok else f"No milestone with id {milestone_id}."


class ListProjectsTool(Tool):
    name = "list_projects"
    description = "List all tracked projects."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, store: Store):
        self._store = store

    def run(self) -> str:
        projects = self._store.list_projects()
        return "\n".join(f"- {p.name}" for p in projects) if projects else "No projects yet."
