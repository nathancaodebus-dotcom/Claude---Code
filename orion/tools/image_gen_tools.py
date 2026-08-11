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
            "file_name": {
                "type": "string",
                "description": "Optional stable name for the output file. Derived from the prompt if omitted.",
            },
        },
        "required": ["prompt"],
    }

    def run(self, prompt: str, aspect_ratio: str = "1:1", file_name: str | None = None) -> str:
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.gemini_image_model}:predict",
            params={"key": config.gemini_api_key},
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {"sampleCount": 1, "aspectRatio": aspect_ratio},
            },
            timeout=60,
        )
        if response.status_code != 200:
            return f"Image generation failed ({response.status_code}): {response.text[:300]}"

        data = response.json()
        predictions = data.get("predictions") or []
        if not predictions or "bytesBase64Encoded" not in predictions[0]:
            return f"Image generation returned no image: {str(data)[:300]}"

        image_bytes = base64.b64decode(predictions[0]["bytesBase64Encoded"])
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"{slugify(file_name or prompt)}.png"
        path.write_bytes(image_bytes)
        push_attachment(str(path))
        return f"Generated image saved to {path}."
