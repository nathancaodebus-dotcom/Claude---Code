"""Trigger a local backup on demand or set BACKUP_SOURCE_PATH/BACKUP_DEST_PATH
in .env for a default pair. Uses plain recursive copy — for anything fancier
(incremental, cloud sync), point BACKUP_DEST_PATH at an rclone/Syncthing
mount and let that tool handle the smarts."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from core.config import config
from tools.base import Tool


class RunBackupTool(Tool):
    name = "run_backup"
    description = "Back up a directory to a destination (defaults to BACKUP_SOURCE_PATH/BACKUP_DEST_PATH from .env)."
    input_schema = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Defaults to BACKUP_SOURCE_PATH."},
            "destination": {"type": "string", "description": "Defaults to BACKUP_DEST_PATH."},
        },
    }

    def run(self, source: str | None = None, destination: str | None = None) -> str:
        source = source or config.backup_source_path
        destination = destination or config.backup_dest_path
        if not (source and destination):
            return "No source/destination configured. Set BACKUP_SOURCE_PATH/BACKUP_DEST_PATH or pass them explicitly."

        source_path = Path(source)
        if not source_path.exists():
            return f"Source '{source}' does not exist."

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest_path = Path(destination) / f"{source_path.name}-{timestamp}"
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if source_path.is_dir():
            shutil.copytree(source_path, dest_path)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)

        return f"Backed up '{source}' to '{dest_path}'."
