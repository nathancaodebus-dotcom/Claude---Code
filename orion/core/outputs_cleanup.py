"""Optional retention sweep for outputs/ — every tool that generates a file
(images, documents, videos, ...) writes there (see tools/document_utils.py,
tools/image_gen_tools.py, tools/video_edit_tools.py, ...) and nothing ever
removed an old one on its own, so a long-lived install just accumulates
files forever.

Off by default (ORION_OUTPUTS_RETENTION_DAYS unset or 0, see core/config.py):
auto-deleting a user's generated files is exactly the kind of surprising,
hard-to-reverse action this project avoids taking without explicit opt-in.
Set the env var to enable an automatic sweep at each interface's startup
(see e.g. interfaces/cli.py), or use the clean_old_outputs tool
(tools/outputs_cleanup_tool.py) for an explicit one-off/on-demand cleanup.

outputs/websites/ is deliberately never touched, opt-in or not: those are
live, redeployable site projects (tools/website_publish_tools.py), not
disposable generated one-offs — deleting one out from under a published
site would break republishing it.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger("orion.outputs_cleanup")

EXCLUDED_DIRS = {"websites"}


def purge_old_outputs(outputs_dir: Path, retention_days: int, now: float | None = None) -> list[Path]:
    """Deletes files under outputs_dir last modified more than retention_days
    ago, skipping outputs/websites/ entirely. retention_days <= 0 means
    disabled — returns immediately without touching anything. Returns the
    list of paths actually deleted."""
    if retention_days <= 0 or not outputs_dir.exists():
        return []

    cutoff = (now if now is not None else time.time()) - retention_days * 86400
    deleted = []
    for path in outputs_dir.rglob("*"):
        if not path.is_file():
            continue
        if EXCLUDED_DIRS & set(path.relative_to(outputs_dir).parts[:-1]):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted.append(path)
        except OSError:
            continue  # removed/renamed between listing and unlink — nothing to do

    if deleted:
        logger.info("Purged %d output file(s) older than %d day(s).", len(deleted), retention_days)
    return deleted
