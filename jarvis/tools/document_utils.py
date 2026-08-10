"""Shared helpers for the Office-document tools (pptx/docx/xlsx): turning a
title into a stable document name, and resolving where generated files live.
"""
from __future__ import annotations

import re
from pathlib import Path

OUTPUT_DIR = Path("outputs")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "document"


def resolve_path(name: str, extension: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR / f"{name}.{extension}"
