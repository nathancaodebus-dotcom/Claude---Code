"""Dictate a note straight into an Obsidian vault as a markdown file — no
API involved, Obsidian just reads the filesystem, so this is a pure local
file write into whatever folder is configured as the vault."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from core.config import config
from tools.base import Tool


def _vault_path() -> Path:
    if not config.obsidian_vault_path:
        raise RuntimeError("OBSIDIAN_VAULT_PATH is not set in .env.")
    path = Path(config.obsidian_vault_path)
    if not path.is_dir():
        raise RuntimeError(f"OBSIDIAN_VAULT_PATH '{path}' is not a directory.")
    return path


def _safe_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title).strip() or "note"


class CreateObsidianNoteTool(Tool):
    name = "create_obsidian_note"
    description = "Create a new note (markdown file) in the user's Obsidian vault."
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "content"],
    }

    def run(self, title: str, content: str, tags: list[str] | None = None) -> str:
        vault = _vault_path()
        filename = f"{_safe_filename(title)}.md"
        path = vault / filename

        frontmatter = f"---\ncreated: {datetime.now().isoformat()}\n"
        if tags:
            frontmatter += "tags: [" + ", ".join(tags) + "]\n"
        frontmatter += "---\n\n"

        path.write_text(frontmatter + f"# {title}\n\n{content}\n", encoding="utf-8")
        return f"Created note '{filename}' in the Obsidian vault."


class AppendObsidianNoteTool(Tool):
    name = "append_obsidian_note"
    description = "Append text to an existing Obsidian note by its title."
    input_schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
        "required": ["title", "content"],
    }

    def run(self, title: str, content: str) -> str:
        vault = _vault_path()
        path = vault / f"{_safe_filename(title)}.md"
        if not path.exists():
            return f"No note named '{title}'. Use create_obsidian_note first."

        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n{content}\n")
        return f"Appended to '{title}'."


class ListObsidianNotesTool(Tool):
    name = "list_obsidian_notes"
    description = "List the note titles in the Obsidian vault, optionally filtered by a search term in the title."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Optional substring to filter titles by."},
        },
    }

    def run(self, query: str | None = None) -> str:
        vault = _vault_path()
        titles = sorted(p.stem for p in vault.glob("*.md"))
        if query:
            titles = [t for t in titles if query.lower() in t.lower()]
        if not titles:
            return "No matching notes." if query else "The vault has no notes yet."
        return "\n".join(f"- {t}" for t in titles)
