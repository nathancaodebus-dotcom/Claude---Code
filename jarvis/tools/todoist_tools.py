"""Todoist integration — for users who already live in Todoist rather than
Orion's own built-in to-do list (tools/productivity_tools.py). Both can be
enabled at once; they're independent, unrelated task stores."""
from __future__ import annotations

import httpx

from core.config import config
from tools.base import Tool

_BASE_URL = "https://api.todoist.com/rest/v2"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.todoist_api_token}"}


class AddTodoistTaskTool(Tool):
    name = "add_todoist_task"
    description = "Add a task to Todoist."
    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "due_string": {"type": "string", "description": "Natural language due date, e.g. 'tomorrow at 9am'."},
            "project_name": {"type": "string", "description": "Target project. Defaults to Inbox."},
        },
        "required": ["content"],
    }

    def run(self, content: str, due_string: str | None = None, project_name: str | None = None) -> str:
        payload = {"content": content}
        if due_string:
            payload["due_string"] = due_string

        if project_name:
            projects = httpx.get(f"{_BASE_URL}/projects", headers=_headers(), timeout=10).json()
            match = next((p for p in projects if p["name"].lower() == project_name.lower()), None)
            if not match:
                return f"No Todoist project named '{project_name}'."
            payload["project_id"] = match["id"]

        response = httpx.post(f"{_BASE_URL}/tasks", headers=_headers(), json=payload, timeout=10)
        response.raise_for_status()
        return f"Added Todoist task: {content}"


class ListTodoistTasksTool(Tool):
    name = "list_todoist_tasks"
    description = "List open Todoist tasks, optionally filtered by project."
    input_schema = {
        "type": "object",
        "properties": {"project_name": {"type": "string"}},
    }

    def run(self, project_name: str | None = None) -> str:
        tasks = httpx.get(f"{_BASE_URL}/tasks", headers=_headers(), timeout=10).json()

        if project_name:
            projects = httpx.get(f"{_BASE_URL}/projects", headers=_headers(), timeout=10).json()
            match = next((p for p in projects if p["name"].lower() == project_name.lower()), None)
            if not match:
                return f"No Todoist project named '{project_name}'."
            tasks = [t for t in tasks if t["project_id"] == match["id"]]

        if not tasks:
            return "No open Todoist tasks."
        return "\n".join(f"- [{t['id']}] {t['content']}" for t in tasks)


class CompleteTodoistTaskTool(Tool):
    name = "complete_todoist_task"
    description = "Mark a Todoist task as complete, by its id (from list_todoist_tasks)."
    input_schema = {
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    }

    def run(self, task_id: str) -> str:
        response = httpx.post(f"{_BASE_URL}/tasks/{task_id}/close", headers=_headers(), timeout=10)
        if response.status_code == 204:
            return f"Completed Todoist task {task_id}."
        return f"Could not complete task {task_id} (status {response.status_code})."
