"""Run a short Python snippet on demand — for one-off automation ('write and
run a script that renames these files') and for testing new commands before
trusting them.

Honesty about what this is: it's a *resource-limited subprocess*, not a
hard security boundary. It runs as the same OS user as Jarvis, with a
timeout and output cap, in a throwaway working directory — enough to catch
runaway loops or accidental huge output, not enough to stop deliberately
malicious code. Don't expose this to anyone but the trusted owner of the
assistant (which the Telegram/voice interfaces already restrict to).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from tools.base import Tool

DEFAULT_TIMEOUT_S = 10
MAX_OUTPUT_CHARS = 4000


class RunPythonSnippetTool(Tool):
    name = "run_python_snippet"
    description = (
        "Write and run a short Python script for a one-off task (e.g. renaming files, "
        "quick data munging) and return its stdout/stderr. Runs in a resource-limited "
        "subprocess with a timeout — not a hard security sandbox, so only use it for "
        "things the user themselves asked to automate, not for handling untrusted input."
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

            return output[:MAX_OUTPUT_CHARS] or "(no output)"
