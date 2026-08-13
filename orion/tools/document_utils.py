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
    """name only gets slugify()'d by callers when document_name is omitted
    from the tool call — when the model/user supplies one explicitly, it
    used to be used raw. A name like '../../../../tmp/evil' (a real
    document_name string, directly triggerable through these tools' own
    input_schema, not a hypothetical) would resolve outside OUTPUT_DIR
    entirely. Stripping path separators here closes that off for every
    caller — resolve_path() is the one chokepoint every docx/pptx/xlsx
    create/save call already goes through — while still accepting anything
    else a legitimate title-derived or user-typed name might contain."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    # Strips anything that could ever act as a path separator (including a
    # bare ':', which Windows treats specially in a drive-relative path like
    # 'C:foo' even without a following backslash) — with none of those left,
    # what's returned is always exactly one path component under
    # OUTPUT_DIR, never able to resolve outside it regardless of '..'
    # segments in the original name.
    safe_name = name.replace("/", "-").replace("\\", "-").replace(":", "-")
    return OUTPUT_DIR / f"{safe_name}.{extension}"


def kind_collision_warning(previous: Document | None, new_kind: str) -> str:
    """Document names are a single shared namespace across pptx/docx/xlsx, so
    creating one can silently replace a same-named document of a different
    kind. Surface that instead of letting it happen invisibly."""
    if previous and previous.kind != new_kind:
        return f" (replaced an existing {previous.kind} document with the same name)"
    return ""
