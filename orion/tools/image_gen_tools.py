"""Generate images from a text prompt using Google's Imagen models via the
Gemini API — a separate, usage-billed API key (GEMINI_API_KEY) from
ANTHROPIC_API_KEY. No free tier: each image costs real money (a few cents
as of 2026), which is why this tool is only registered when a key is
actually configured (see tools/registry_builder.py) rather than failing at
call time — if it's missing, Claude simply doesn't see this tool at all.
"""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from core.attachments import push as push_attachment
from core.config import config
from tools.base import Tool
from tools.document_utils import slugify

OUTPUT_DIR = Path("outputs") / "images"


class GenerateImageTool(Tool):
    name = "generate_image"
    description = (
        "Generate an image from a text description using Google Imagen. This is a paid API "
        "call (a few cents per image) — mention that if the user seems unaware, don't generate "
        "several images in a row without checking they actually want that."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Description of the image to generate."},
            "aspect_ratio": {
                "type": "string",
                "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                "description": "Default '1:1'.",
            },
            "count": {
                "type": "integer",
                "description": "How many variations to generate (default 1, max 4). Each one costs "
                "separately — confirm with the user before requesting more than 1.",
            },
            "file_name": {
                "type": "string",
                "description": "Optional stable name for the output file. Derived from the prompt if omitted.",
            },
        },
        "required": ["prompt"],
    }

    def run(
        self, prompt: str, aspect_ratio: str = "1:1", count: int = 1, file_name: str | None = None
    ) -> str:
        count = max(1, min(count, 4))
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.gemini_image_model}:predict",
            params={"key": config.gemini_api_key},
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {"sampleCount": count, "aspectRatio": aspect_ratio},
            },
            timeout=60,
        )
        if response.status_code != 200:
            return f"Image generation failed ({response.status_code}): {response.text[:300]}"

        data = response.json()
        predictions = data.get("predictions") or []
        if not predictions or "bytesBase64Encoded" not in predictions[0]:
            return f"Image generation returned no image: {str(data)[:300]}"

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        base_name = slugify(file_name or prompt)
        paths = []
        for i, prediction in enumerate(predictions):
            if "bytesBase64Encoded" not in prediction:
                continue
            image_bytes = base64.b64decode(prediction["bytesBase64Encoded"])
            suffix = "" if len(predictions) == 1 else f"-{i + 1}"
            path = OUTPUT_DIR / f"{base_name}{suffix}.png"
            path.write_bytes(image_bytes)
            push_attachment(str(path))
            paths.append(str(path))

        if len(paths) == 1:
            return f"Generated image saved to {paths[0]}."
        return f"Generated {len(paths)} images: {', '.join(paths)}."
