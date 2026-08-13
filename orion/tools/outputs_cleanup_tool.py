"""Manual/on-demand counterpart to core/outputs_cleanup.py's automatic
(opt-in only) startup sweep — lets the user ask for a cleanup directly
('efface les vieux fichiers générés de plus de 30 jours') without needing
ORION_OUTPUTS_RETENTION_DAYS configured at all."""
from __future__ import annotations

from pathlib import Path

from core.config import config
from core.outputs_cleanup import purge_old_outputs
from tools.base import Tool

OUTPUTS_DIR = Path("outputs")


class CleanOldOutputsTool(Tool):
    requires_network = False
    name = "clean_old_outputs"
    description = (
        "Permanently delete generated files (images, documents, videos, QR codes, ...) under outputs/ "
        "that are older than a given number of days. Never touches outputs/websites/ (live, "
        "redeployable site projects). Falls back to ORION_OUTPUTS_RETENTION_DAYS if 'days' isn't given, "
        "and does nothing if neither is set. This is a permanent deletion — always confirm with the "
        "user which files/how far back before calling this, don't call it on your own initiative."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Delete files last modified more than this many days ago.",
            },
        },
    }

    def run(self, days: int | None = None) -> str:
        retention = days if days is not None else config.outputs_retention_days
        if retention <= 0:
            return (
                "No retention period given, and ORION_OUTPUTS_RETENTION_DAYS isn't set — nothing deleted. "
                "Pass 'days' explicitly to clean up now."
            )
        deleted = purge_old_outputs(OUTPUTS_DIR, retention)
        if not deleted:
            return f"No files older than {retention} day(s) found under outputs/."
        return f"Deleted {len(deleted)} file(s) older than {retention} day(s)."
