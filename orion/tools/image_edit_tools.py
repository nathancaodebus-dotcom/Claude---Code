"""Edit existing image files — resize, crop, rotate, filters, brightness/
contrast/saturation, and text overlays — using Pillow. No API key, no
network call, works entirely offline (unlike tools/image_gen_tools.py).

Guards its own import: Pillow can fail to build from source on some
platforms without system jpeg/zlib headers (the same situation as
qrcode[pil] — see tools/utility_tools.py) — degrade this whole module
instead of taking the registry down with it.
"""
from __future__ import annotations

from pathlib import Path

from core.attachments import push as push_attachment
from tools.base import Tool

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
except ImportError:
    Image = None

_PILLOW_MISSING_MSG = (
    "Pillow is not installed (it needs system jpeg/zlib headers to build from source on some "
    "platforms) — image editing isn't available here."
)

OUTPUT_DIR = Path("outputs") / "images"
_FONT_CANDIDATES = ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf")


def _output_path(source_path: str, suffix: str, output_path: str | None) -> Path:
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        return Path(output_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"{Path(source_path).stem}-{suffix}.png"


def _save(img, out_path: Path) -> None:
    # JPEG has no alpha channel — flatten to RGB only when that's actually
    # the target format, so PNG/other formats keep any transparency.
    to_save = img.convert("RGB") if out_path.suffix.lower() in (".jpg", ".jpeg") else img
    to_save.save(out_path)


def _load_font(size: int):
    """Tries a few common bold system fonts, in rough order of how likely
    they are to exist, and falls back to Pillow's built-in bitmap font
    (always available, just less polished) rather than failing — font
    availability varies a lot across Pi/desktop/server setups."""
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


class EditImageTool(Tool):
    name = "edit_image"
    description = (
        "Apply one edit operation to an image: resize, crop, rotate, grayscale, blur, sharpen, "
        "or adjust (brightness/contrast/saturation). Each call does one operation; chain calls "
        "for multiple edits."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the source image."},
            "operation": {
                "type": "string",
                "enum": ["resize", "crop", "rotate", "grayscale", "blur", "sharpen", "adjust"],
            },
            "width": {"type": "integer", "description": "For 'resize'."},
            "height": {"type": "integer", "description": "For 'resize'."},
            "box": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "For 'crop': [left, top, right, bottom] in pixels.",
            },
            "angle": {"type": "number", "description": "For 'rotate', degrees counterclockwise."},
            "brightness": {"type": "number", "description": "For 'adjust': factor, 1.0 = unchanged."},
            "contrast": {"type": "number", "description": "For 'adjust': factor, 1.0 = unchanged."},
            "saturation": {"type": "number", "description": "For 'adjust': factor, 1.0 = unchanged."},
            "output_path": {
                "type": "string",
                "description": "Optional. Derived from the source name + operation if omitted.",
            },
        },
        "required": ["path", "operation"],
    }

    def run(
        self,
        path: str,
        operation: str,
        width: int | None = None,
        height: int | None = None,
        box: list[int] | None = None,
        angle: float | None = None,
        brightness: float | None = None,
        contrast: float | None = None,
        saturation: float | None = None,
        output_path: str | None = None,
    ) -> str:
        if Image is None:
            return _PILLOW_MISSING_MSG

        source = Path(path)
        if not source.is_file():
            return f"'{path}' is not a file."
        img = Image.open(source)

        if operation == "resize":
            if not width or not height:
                return "'resize' needs both width and height."
            img = img.resize((width, height))
        elif operation == "crop":
            if not box or len(box) != 4:
                return "'crop' needs box=[left, top, right, bottom]."
            img = img.crop(tuple(box))
        elif operation == "rotate":
            img = img.rotate(angle or 0, expand=True)
        elif operation == "grayscale":
            img = img.convert("L")
        elif operation == "blur":
            img = img.filter(ImageFilter.GaussianBlur(radius=4))
        elif operation == "sharpen":
            img = img.filter(ImageFilter.SHARPEN)
        elif operation == "adjust":
            if brightness is not None:
                img = ImageEnhance.Brightness(img).enhance(brightness)
            if contrast is not None:
                img = ImageEnhance.Contrast(img).enhance(contrast)
            if saturation is not None:
                img = ImageEnhance.Color(img).enhance(saturation)
        else:
            return f"Unknown operation '{operation}'."

        out_path = _output_path(path, operation, output_path)
        _save(img, out_path)
        push_attachment(str(out_path))
        return f"Applied '{operation}' to '{path}', saved to {out_path}."


class AddTextToImageTool(Tool):
    name = "add_text_to_image"
    description = "Overlay text on an image — a caption, watermark, or meme-style label."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "text": {"type": "string"},
            "position": {"type": "string", "enum": ["top", "center", "bottom"], "description": "Default 'bottom'."},
            "font_size": {"type": "integer", "description": "Default 32."},
            "color": {"type": "string", "description": "Default 'white' — any Pillow color name or hex code."},
            "output_path": {"type": "string"},
        },
        "required": ["path", "text"],
    }

    def run(
        self,
        path: str,
        text: str,
        position: str = "bottom",
        font_size: int = 32,
        color: str = "white",
        output_path: str | None = None,
    ) -> str:
        if Image is None:
            return _PILLOW_MISSING_MSG

        source = Path(path)
        if not source.is_file():
            return f"'{path}' is not a file."
        img = Image.open(source).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = _load_font(font_size)

        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_width, text_height = right - left, bottom - top
        x = (img.width - text_width) / 2
        if position == "top":
            y = img.height * 0.05
        elif position == "center":
            y = (img.height - text_height) / 2
        else:
            y = img.height * 0.90 - text_height

        # A thin dark outline keeps the text legible over any background
        # color, since we don't know what's behind it.
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            draw.text((x + dx, y + dy), text, font=font, fill="black")
        draw.text((x, y), text, font=font, fill=color)

        out_path = _output_path(path, "text", output_path)
        _save(img, out_path)
        push_attachment(str(out_path))
        return f"Added text to '{path}', saved to {out_path}."
