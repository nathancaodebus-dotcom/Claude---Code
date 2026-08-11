"""Run a short Python snippet on demand — for one-off automation ('write and
run a script that renames these files') and for testing new commands before
trusting them.

Two backends, picked automatically:
- Docker (if the `docker` package is installed and a daemon is reachable):
  runs in a throwaway python:3-slim container with no network access and a
  memory cap — a real isolation boundary.
- Subprocess (fallback): resource-limited but NOT a hard security boundary —
  it runs as the same OS user as Orion. Fine for things the user themselves
  asked to automate; not a defense against untrusted/adversarial input.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from tools.base import Tool

DEFAULT_TIMEOUT_S = 10
MAX_OUTPUT_CHARS = 4000
DOCKER_IMAGE = "python:3-slim"
DOCKER_MEMORY_LIMIT = "256m"


def _docker_client():
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return client
    except Exception:
        return None


def _run_in_docker(client, code: str, timeout_seconds: int) -> str:
    try:
        output = client.containers.run(
            DOCKER_IMAGE,
            ["python3", "-c", code],
            network_disabled=True,
            mem_limit=DOCKER_MEMORY_LIMIT,
            remove=True,
            stdout=True,
            stderr=True,
            timeout=timeout_seconds,
        )
        return output.decode(errors="replace")
    except Exception as exc:  # container errors surface the real stdout/stderr via exc.stderr when available
        stderr = getattr(exc, "stderr", None)
        return f"[docker sandbox error] {stderr.decode(errors='replace') if stderr else exc}"


def _run_in_subprocess(code: str, timeout_seconds: int) -> str:
    with tempfile.TemporaryDirectory() as tmp_dir:
        script_path = Path(tmp_dir) / "snippet.py"
        script_path.write_text(code)

        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return f"Timed out after {timeout_seconds}s."

        output = result.stdout
        if result.returncode != 0:
            output += f"\n[exit code {result.returncode}]\n{result.stderr}"
        return output


class RunPythonSnippetTool(Tool):
    name = "run_python_snippet"
    description = (
        "Write and run a short Python script for a one-off task (e.g. renaming files, "
        "quick data munging) and return its stdout/stderr. Runs inside an isolated Docker "
        "container if available, otherwise a resource-limited subprocess (not a hard security "
        "boundary in that case) — only use it for things the user themselves asked to automate."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source to execute."},
            "timeout_seconds": {"type": "integer", "description": f"Default {DEFAULT_TIMEOUT_S}."},
        },
        "required": ["code"],
    }

    def run(self, code: str, timeout_seconds: int = DEFAULT_TIMEOUT_S) -> str:
        docker_client = _docker_client()
        if docker_client is not None:
            output = _run_in_docker(docker_client, code, timeout_seconds)
        else:
            output = _run_in_subprocess(code, timeout_seconds)

        return output[:MAX_OUTPUT_CHARS] or "(no output)"
