"""Voice-triggered build/test/deploy — deliberately NOT arbitrary shell
execution. DEPLOY_COMMANDS in .env maps a name to a fixed shell command, so
'run the production deploy' can only ever run the exact command the user
pre-approved, never something improvised from a misheard voice command."""
from __future__ import annotations

import json
import subprocess

from core.config import config
from tools.base import Tool


class RunDeployCommandTool(Tool):
    name = "run_deploy_command"
    description = (
        "Run a pre-approved named command (build/test/deploy/etc.) from DEPLOY_COMMANDS. "
        "Use list_deploy_commands first if unsure what's available — this cannot run arbitrary "
        "commands, only ones the user has explicitly configured."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "timeout_seconds": {"type": "integer", "description": "Default 300."},
        },
        "required": ["name"],
    }

    def run(self, name: str, timeout_seconds: int = 300) -> str:
        commands = json.loads(config.deploy_commands or "{}")
        if name not in commands:
            return f"No command named '{name}'. Configured: {list(commands.keys())}"

        try:
            result = subprocess.run(
                commands[name], shell=True, capture_output=True, text=True, timeout=timeout_seconds
            )
        except subprocess.TimeoutExpired:
            return f"'{name}' timed out after {timeout_seconds}s."

        output = result.stdout[-3000:]
        if result.returncode != 0:
            output += f"\n[exit code {result.returncode}]\n{result.stderr[-1000:]}"
        return output or "(no output)"


class ListDeployCommandsTool(Tool):
    name = "list_deploy_commands"
    description = "List the names of pre-approved deploy/build/test commands available to run_deploy_command."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        commands = json.loads(config.deploy_commands or "{}")
        return "\n".join(f"- {name}" for name in commands) if commands else "No deploy commands configured."
