"""Read an arbitrary local text/code file — enables things like 'document
this project' by combining this with the existing document-creation tools
(Orion reads the source, then writes the docs)."""
from __future__ import annotations

from pathlib import Path

from tools.base import Tool


class ReadTextFileTool(Tool):
    name = "read_text_file"
    description = "Read a local text or code file by path (source code, config, logs, plain text, markdown, etc.)."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "description": "Default 10000."},
        },
        "required": ["path"],
    }

    def run(self, path: str, max_chars: int = 10000) -> str:
        file_path = Path(path)
        if not file_path.is_file():
            return f"'{path}' is not a file."
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except (UnicodeDecodeError, OSError) as exc:
            return f"Could not read '{path}': {exc}"
        return text[:max_chars]
