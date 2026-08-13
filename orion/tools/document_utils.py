"""Shared helpers for the Office-document tools (pptx/docx/xlsx): turning a
title into a stable document name, and resolving where generated files live.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.store import Document

OUTPUT_DIR = Path("outputs")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "document"


def resolve_path(name: str, extension: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR / f"{name}.{extension}"


def kind_collision_warning(previous: Document | None, new_kind: str) -> str:
    """Document names are a single shared namespace across pptx/docx/xlsx, so
    creating one can silently replace a same-named document of a different
    kind. Surface that instead of letting it happen invisibly."""
    if previous and previous.kind != new_kind:
        return f" (replaced an existing {previous.kind} document with the same name)"
    return ""
