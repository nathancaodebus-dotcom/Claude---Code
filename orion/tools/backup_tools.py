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
    requires_network = False
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

        # Copies into a '.partial'-suffixed name first, only renaming to the
        # real dest_path once the copy fully succeeds. A copy that fails
        # partway (disk full, permission error, a source file vanishing
        # mid-copy) used to leave a partially-populated directory sitting
        # right at dest_path — indistinguishable from a complete backup to
        # a later "restore from latest backup" workflow. This way dest_path
        # only ever comes into existence once the copy is actually done;
        # anything left behind by a failed attempt is cleaned up instead.
        staging_path = dest_path.with_name(dest_path.name + ".partial")
        try:
            if source_path.is_dir():
                shutil.copytree(source_path, staging_path)
            else:
                shutil.copy2(source_path, staging_path)
        except Exception:
            if staging_path.is_dir():
                shutil.rmtree(staging_path, ignore_errors=True)
            else:
                staging_path.unlink(missing_ok=True)
            raise

        staging_path.rename(dest_path)
        return f"Backed up '{source}' to '{dest_path}'."
