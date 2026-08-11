"""Analyze/critique a supplied image file using Claude's vision — works for
design/UI mockup critique, describing a photo, reading a whiteboard, etc.
Needs an image *file* (screenshot, photo taken and sent via Telegram), not
a live camera — no camera hardware required."""
from __future__ import annotations

import base64
from pathlib import Path

import anthropic

from core.config import config
from tools.base import Tool

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class AnalyzeImageTool(Tool):
    name = "analyze_image"
    description = (
        "Analyze or critique an image file by its local path — a design mockup, screenshot, "
        "photo, diagram, whiteboard, etc. Give a specific instruction for what to look for "
        "(e.g. 'critique the layout and contrast' or 'what does this diagram show')."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "instruction": {"type": "string", "description": "What to analyze or answer about the image."},
        },
        "required": ["path", "instruction"],
    }

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def run(self, path: str, instruction: str) -> str:
        file_path = Path(path)
        media_type = _MEDIA_TYPES.get(file_path.suffix.lower())
        if not media_type:
            return f"Unsupported image type '{file_path.suffix}'. Supported: {', '.join(_MEDIA_TYPES)}"
        if not file_path.is_file():
            return f"'{path}' is not a file."

        image_b64 = base64.standard_b64encode(file_path.read_bytes()).decode()
        response = self._client.messages.create(
            model=config.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                        },
                        {"type": "text", "text": instruction},
                    ],
                }
            ],
        )
        return "\n".join(b.text for b in response.content if b.type == "text").strip()
