"""Find large files and duplicates, and get an overview of a folder like
Downloads — pure filesystem operations, no external dependency."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from tools.base import Tool

_HASH_CHUNK_SIZE = 1024 * 1024


def _file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


class FindLargeFilesTool(Tool):
    requires_network = False
    name = "find_large_files"
    description = "Find the largest files under a directory (recursively)."
    input_schema = {
        "type": "object",
        "properties": {
            "directory": {"type": "string"},
            "min_size_mb": {"type": "number", "description": "Default 100."},
            "max_results": {"type": "integer", "description": "Default 20."},
        },
        "required": ["directory"],
    }

    def run(self, directory: str, min_size_mb: float = 100, max_results: int = 20) -> str:
        root = Path(directory)
        if not root.is_dir():
            return f"'{directory}' is not a directory."

        min_bytes = min_size_mb * 1024 * 1024
        matches = [
            (p, p.stat().st_size)
            for p in root.rglob("*")
            if p.is_file() and p.stat().st_size >= min_bytes
        ]
        matches.sort(key=lambda item: item[1], reverse=True)

        if not matches:
            return f"No files >= {min_size_mb} MB found under '{directory}'."
        return "\n".join(f"- {p} ({size / (1024**2):.1f} MB)" for p, size in matches[:max_results])


class FindDuplicateFilesTool(Tool):
    requires_network = False
    name = "find_duplicate_files"
    description = "Find duplicate files (by content) under a directory, grouped together."
    input_schema = {
        "type": "object",
        "properties": {"directory": {"type": "string"}},
        "required": ["directory"],
    }

    def run(self, directory: str) -> str:
        root = Path(directory)
        if not root.is_dir():
            return f"'{directory}' is not a directory."

        by_size: dict[int, list[Path]] = defaultdict(list)
        for p in root.rglob("*"):
            if p.is_file():
                by_size[p.stat().st_size].append(p)

        by_hash: dict[str, list[Path]] = defaultdict(list)
        for candidates in by_size.values():
            if len(candidates) < 2:
                continue
            for p in candidates:
                by_hash[_file_hash(p)].append(p)

        duplicate_groups = [paths for paths in by_hash.values() if len(paths) > 1]
        if not duplicate_groups:
            return f"No duplicate files found under '{directory}'."

        lines = []
        for i, group in enumerate(duplicate_groups, start=1):
            lines.append(f"Group {i}:")
            lines.extend(f"  - {p}" for p in group)
        return "\n".join(lines)


class SummarizeDirectoryTool(Tool):
    requires_network = False
    name = "summarize_directory"
    description = "Get an overview of a folder (e.g. Downloads): file count, total size, breakdown by extension."
    input_schema = {
        "type": "object",
        "properties": {"directory": {"type": "string"}},
        "required": ["directory"],
    }

    def run(self, directory: str) -> str:
        root = Path(directory)
        if not root.is_dir():
            return f"'{directory}' is not a directory."

        by_ext: dict[str, list[int]] = defaultdict(list)
        for p in root.rglob("*"):
            if p.is_file():
                by_ext[p.suffix.lower() or "(no extension)"].append(p.stat().st_size)

        total_files = sum(len(sizes) for sizes in by_ext.values())
        total_bytes = sum(sum(sizes) for sizes in by_ext.values())

        lines = [f"{total_files} files, {total_bytes / (1024**2):.1f} MB total", "By extension:"]
        for ext, sizes in sorted(by_ext.items(), key=lambda item: -sum(item[1])):
            lines.append(f"- {ext}: {len(sizes)} files, {sum(sizes) / (1024**2):.1f} MB")
        return "\n".join(lines)
